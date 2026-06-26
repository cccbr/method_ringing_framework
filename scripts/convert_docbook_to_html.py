#!/usr/bin/env python3
"""Render DocBook XML back to HTML styled like the original site."""

from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from lxml import etree, html as lxml_html


NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class VersionOption:
    label: str
    button_label: str
    href: str
    active: bool = False


@dataclass(frozen=True)
class SidebarSubsection:
    title: str
    href: str


@dataclass(frozen=True)
class SidebarPage:
    label: str
    href: str
    active: bool = False
    appendices_header: bool = False
    subsections: tuple[SidebarSubsection, ...] = ()


@dataclass(frozen=True)
class SchemaVersionContext:
    edition_label: str
    status: str
    version_url: str
    approval_date: str | None = None
    superseded_by_label: str | None = None
    superseded_by_url: str | None = None


@dataclass(frozen=True)
class GlossaryTermLink:
    term: str
    page_href: str
    anchor_id: str


@dataclass(frozen=True)
class CrossReferenceLink:
    label: str
    href: str


def local_name(elem: etree._Element) -> str:
    return etree.QName(elem).localname


def collapse_ws(text: str | None, *, strip: bool = False) -> str:
    if text is None:
        return ""
    value = WHITESPACE_RE.sub(" ", text.replace("\xa0", " "))
    return value.strip() if strip else value


def join_href(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def qualify_href(href: str, asset_prefix: str) -> str:
    if not href or href.startswith(("http://", "https://", "mailto:", "#", "../", "./", "/")):
        return href
    return join_href(asset_prefix, href)


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return collapse_ws("".join(elem.itertext()), strip=True)


def schema_fragment(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return cleaned or "item"


def normalize_inline_spacing(text: str) -> str:
    text = re.sub(r"(?<=[A-Za-z0-9,.;:!?)])(<a\b)", r" \1", text)
    text = re.sub(r"(</a>)(?=[A-Za-z0-9(])", r"\1 ", text)
    return text


def render_mixed(node: etree._Element, asset_prefix: str) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(html.escape(collapse_ws(node.text)))

    for child in node:
        parts.append(render_inline(child, asset_prefix))
        if child.tail:
            parts.append(html.escape(collapse_ws(child.tail)))

    return normalize_inline_spacing("".join(parts)).strip()


def render_inline(node: etree._Element, asset_prefix: str) -> str:
    name = local_name(node)
    body = render_mixed(node, asset_prefix)

    if name == "emphasis":
        role = (node.get("role") or "").lower()
        if role == "bold":
            return f"<b>{body}</b>"
        if role == "italic":
            return f"<i>{body}</i>"
        if role == "underline":
            return f"<u>{body}</u>"
        return f"<span>{body}</span>"

    if name in {"link", "ulink"}:
        href = (
            node.get(f"{{{NS['xlink']}}}href")
            or node.get("url")
            or node.get("href")
            or "#"
        )
        href = qualify_href(href, asset_prefix)
        return f'<a class="text-success undrln" href="{html.escape(href, quote=True)}">{body or html.escape(href)}</a>'

    if name == "nolink":
        return f'<span class="mrf-nolink">{body}</span>'

    if name == "literal":
        return f"<code>{body}</code>"

    if name == "quote":
        return f"'{body}'"

    if name == "subscript":
        return f"<sub>{body}</sub>"

    if name == "superscript":
        return f"<sup>{body}</sup>"

    if name == "glossentry":
        return html.escape(read_text(node.find("db:glossterm", NS)))

    return body


def render_para(node: etree._Element, asset_prefix: str, css_class: str | None = None, prefix: str | None = None) -> str:
    body = render_mixed(node, asset_prefix)
    if prefix:
        body = f"<b>{html.escape(prefix)}</b>" if not body else f"<b>{html.escape(prefix)}</b> {body}"
    classes = ["mrf-para"]
    if css_class:
        classes.append(css_class)
    return f'<div class="{" ".join(classes)}">{body}</div>'


def render_body_block(content_html: str) -> str:
    return (
        '                    <div class="row">\n'
        '                        <div class="col-sm-1"></div>\n'
        '                        <div class="col-sm-11">\n'
        f"{indent_block(content_html, 28)}\n"
        "                        </div>\n"
        "                    </div>"
    )


def render_body_para(node: etree._Element, asset_prefix: str) -> str:
    return render_body_block(render_para(node, asset_prefix))


def render_glossary_detail_block(detail_html: str) -> str:
    return detail_html


def render_faq_body(node: etree._Element, asset_prefix: str, *, level: int = 1, collapse_seed: str = "faq") -> str:
    blocks: list[str] = []
    for index, child in enumerate(node, start=1):
        name = local_name(child)
        if name == "para":
            blocks.append(render_para(child, asset_prefix))
        elif name == "mediaobject":
            blocks.append(render_mediaobject(child, asset_prefix))
        elif name == "informaltable":
            blocks.append(render_informaltable(child, asset_prefix))
        elif name in {"itemizedlist", "orderedlist"}:
            blocks.append(render_list(child, asset_prefix, level=level, collapse_seed=f"{collapse_seed}-{index}"))
        elif name in {"example", "note"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                blocks.append(rendered)
    return "\n".join(blocks)


def render_faq_block(node: etree._Element, asset_prefix: str, label: str) -> str:
    body = render_faq_body(node, asset_prefix)
    if not body:
        return ""
    trailing_rule = (node.get(f"{{{NS['mrf']}}}separator") or "").lower() == "hr"
    rule_html = "\n                            <hr />" if trailing_rule else ""
    row_class = " mrf-faq-question" if label == "Q." else ""
    return (
        f'                    <div class="row{row_class}">\n'
        f'                        <div class="col-sm-1">{html.escape(label)}</div>\n'
        '                        <div class="col-sm-11">\n'
        f"{indent_block(body, 28)}{rule_html}\n"
        "                        </div>\n"
        "                    </div>"
    )


def render_mediaobject(node: etree._Element, asset_prefix: str) -> str:
    image = node.find(".//db:imagedata", NS)
    if image is None:
        return ""

    src = qualify_href(image.get("fileref", ""), asset_prefix)
    attrs = [
        f'src="{html.escape(src, quote=True)}"',
        f'alt="{html.escape(Path(image.get("fileref", "image")).stem)}"',
    ]
    width = image.get("width")
    depth = image.get("depth") or image.get("height")
    if width:
        attrs.append(f'width="{html.escape(width, quote=True)}"')
    if depth:
        attrs.append(f'height="{html.escape(depth, quote=True)}"')
    return f'<div class="mrf-mediaobject"><img {" ".join(attrs)} /></div>'


def render_table_cell(node: etree._Element, asset_prefix: str) -> str:
    parts: list[str] = []
    if node.text and collapse_ws(node.text, strip=True):
        parts.append(html.escape(collapse_ws(node.text, strip=True)))

    for child in node:
        name = local_name(child)
        if name == "para":
            parts.append(render_mixed(child, asset_prefix))
        elif name in {"itemizedlist", "orderedlist"}:
            parts.append(render_list(child, asset_prefix, level=1, collapse_seed="table"))
        elif name == "informaltable":
            parts.append(render_informaltable(child, asset_prefix))
        elif name == "mediaobject":
            parts.append(render_mediaobject(child, asset_prefix))
        else:
            parts.append(render_inline(child, asset_prefix))
        if child.tail and collapse_ws(child.tail, strip=True):
            parts.append(html.escape(collapse_ws(child.tail, strip=True)))

    return "<br />".join(part for part in parts if part).strip()


def list_start(node: etree._Element) -> int:
    value = node.get("startingnumber") or node.get("start")
    if not value:
        return 1
    try:
        return max(1, int(value))
    except ValueError:
        return 1


def render_informaltable(node: etree._Element, asset_prefix: str) -> str:
    role = (node.get("role") or "").strip()
    if role == "leadhead-code-pair":
        tgroup = node.find("db:tgroup", NS)
        table_root = tgroup if tgroup is not None else node
        rows = table_root.findall("db:tbody/db:row", NS)
        if not rows:
            rows = table_root.findall("db:row", NS)
        if rows:
            entries = rows[0].findall("db:entry", NS)
            if len(entries) == 2:
                left = render_table_cell(entries[0], asset_prefix)
                right = render_table_cell(entries[1], asset_prefix)
                rendered = (
                    '<div class="row no-gutters my-3">'
                    f'<div class="col-12 col-md-6">{left}</div>'
                    f'<div class="col-12 col-md-6">{right}</div>'
                    "</div>"
                )
                return rendered
    role_class = ""
    table_class = "table table-sm table-bordered mrf-table"
    colgroup_html = ""
    if role == "leadhead-codes":
        role_class = " mrf-code-table"
    elif role in {"amended-method-titles", "amended-method-titles-summary"}:
        table_class = "table table-sm table-borderless mrf-table"
        colgroup_html = '<colgroup><col style="width:10%"><col style="width:45%"><col style="width:45%"></colgroup>'
    tgroup = node.find("db:tgroup", NS)
    table_root = tgroup if tgroup is not None else node
    head_rows = table_root.findall("db:thead/db:row", NS)
    body_rows = table_root.findall("db:tbody/db:row", NS)
    if not head_rows and not body_rows:
        body_rows = table_root.findall("db:row", NS)

    def render_rows(rows: Sequence[etree._Element], cell_tag: str) -> str:
        rendered_rows: list[str] = []
        for row in rows:
            cells = [f"<{cell_tag}>{render_table_cell(entry, asset_prefix)}</{cell_tag}>" for entry in row.findall("db:entry", NS)]
            rendered_rows.append("<tr>" + "".join(cells) + "</tr>")
        return "\n".join(rendered_rows)

    thead_html = f"\n<thead>\n{render_rows(head_rows, 'th')}\n</thead>" if head_rows else ""
    tbody_html = f"\n<tbody>\n{render_rows(body_rows, 'td')}\n</tbody>" if body_rows else ""
    if role == "related-material":
        rendered_rows: list[str] = []
        for row_index, row in enumerate(body_rows, start=1):
            entries = row.findall("db:entry", NS)
            if len(entries) < 3:
                continue
            number = html.escape(read_text(entries[0]))
            title = html.escape(read_text(entries[1]))
            description = render_table_cell(entries[2], asset_prefix)
            row_id_attr = f' id="{html.escape(table_row_id(role or "table", row_index), quote=True)}"'
            rendered_rows.append(
                f"                    <div class=\"row\"{row_id_attr}>\n"
                "                        <div class=\"col-sm-1\">\n"
                f"                            {number}\n"
                "                        </div>\n"
                "                        <div class=\"col-xl-2 col-sm-3\">\n"
                f"                            {title}\n"
                "                        </div>\n"
                "                        <div class=\"col-xl-9 col-sm-8\">\n"
                f"                            {description}\n"
                "                        </div>\n"
                "                    </div>"
            )
        return "\n\n".join(rendered_rows)
    rendered = (
        f'<div class="table-responsive"><table class="{table_class}{role_class}">'
        f"{colgroup_html}{thead_html}{tbody_html}</table></div>"
    )
    if role == "leadhead-codes":
        return render_body_block(rendered)
    return rendered


def render_list_item_blocks(
    item: etree._Element,
    asset_prefix: str,
    *,
    level: int,
    collapse_seed: str,
) -> tuple[list[str], list[str]]:
    main_blocks: list[str] = []
    detail_groups: list[str] = []

    for index, child in enumerate(item, start=1):
        child_name = local_name(child)
        if child_name == "para":
            main_blocks.append(render_para(child, asset_prefix))
        elif child_name == "mediaobject":
            main_blocks.append(render_mediaobject(child, asset_prefix))
        elif child_name == "informaltable":
            main_blocks.append(render_informaltable(child, asset_prefix))
        elif child_name == "question":
            main_blocks.append(render_faq_block(child, asset_prefix, "Q."))
        elif child_name == "answer":
            main_blocks.append(render_faq_block(child, asset_prefix, "A."))
        elif child_name in {"itemizedlist", "orderedlist"}:
            main_blocks.append(render_list(child, asset_prefix, level=level + 1, collapse_seed=f"{collapse_seed}-{index}"))
        elif child_name in {"example", "note"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                detail_groups.append(rendered)

    return main_blocks, detail_groups


def render_numbered_list(
    node: etree._Element,
    asset_prefix: str,
    *,
    level: int,
    collapse_seed: str,
    top_level: bool,
) -> str:
    items: list[str] = []
    start = list_start(node)
    for offset, item in enumerate(node.findall("db:listitem", NS), start=0):
        index = start + offset
        custom_label = item.get(f"{{{NS['mrf']}}}label")
        main_blocks, detail_groups = render_list_item_blocks(
            item,
            asset_prefix,
            level=level,
            collapse_seed=f"{collapse_seed}-{index}",
        )
        toggle_html, detail_html = build_detail_collapse(
            f"{collapse_seed}-{index}",
            detail_groups,
            f"details for item {index}",
        )
        content = indent_block("\n".join(main_blocks), 28) if main_blocks else ""
        marker = html.escape(custom_label) if custom_label else f"{index}."
        row_id_attr = f' id="{html.escape(numbered_list_item_id(collapse_seed, index), quote=True)}"' if top_level else ""
        items.append(
            f"                    <div class=\"row mrf-numbered-item mrf-numbered-level-0\"{row_id_attr}>\n"
            "                        <div class=\"col-sm-1 mrf-numbered-marker\">\n"
            f"                            {marker}{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-sm-11 mrf-numbered-content\">\n"
            f"{content}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )
    return "\n\n".join(items)


def render_list(
    node: etree._Element,
    asset_prefix: str,
    level: int = 0,
    collapse_seed: str | None = None,
    *,
    top_level: bool = False,
) -> str:
    if collapse_seed is None:
        collapse_seed = f"list-{id(node)}"
    ordered = local_name(node) == "orderedlist"
    numeration = (node.get("numeration") or "").lower()
    role = (node.get("role") or "").lower()
    if ordered and numeration != "loweralpha" and level == 0 and top_level:
        return render_numbered_list(node, asset_prefix, level=level, collapse_seed=collapse_seed, top_level=top_level)

    classes = [f"mrf-list", f"mrf-list-level-{level}"]
    if ordered and numeration == "loweralpha":
        classes.append("mrf-loweralpha")
    if ordered and numeration == "lowerroman":
        classes.append("mrf-lowerroman")
    if role == "compact" or level > 0:
        classes.append("mrf-list-compact")
    tag_name = "ol" if ordered else "ul"
    start = list_start(node) if ordered else 1
    start_attr = f' start="{start}"' if ordered and start != 1 else ""
    open_tag = f'<{tag_name}{start_attr} class="{" ".join(classes)}">'
    close_tag = f"</{tag_name}>"

    items: list[str] = []
    for index, item in enumerate(node.findall("db:listitem", NS), start=1):
        main_blocks, detail_groups = render_list_item_blocks(
            item,
            asset_prefix,
            level=level,
            collapse_seed=f"{collapse_seed}-{index}",
        )
        toggle_html, detail_html = build_detail_collapse(
            f"{collapse_seed}-{index}",
            detail_groups,
            f"details for item {index}",
        )
        content = "".join(main_blocks).strip()
        items.append(f"<li>{toggle_html}{content}{detail_html}</li>")
    return f"{open_tag}{''.join(items)}{close_tag}"


def render_group(node: etree._Element, asset_prefix: str, css_class: str, label: str) -> str:
    blocks: list[str] = []
    first_para = True

    for child in node:
        child_name = local_name(child)
        if child_name == "para":
            blocks.append(render_para(child, asset_prefix, css_class, label if first_para else None))
            first_para = False
        elif child_name == "mediaobject":
            if first_para:
                blocks.append(f'<div class="{css_class} mrf-para"><b>{html.escape(label)}</b></div>')
                first_para = False
            blocks.append(render_mediaobject(child, asset_prefix))
        elif child_name in {"itemizedlist", "orderedlist"}:
            if first_para:
                blocks.append(f'<div class="{css_class} mrf-para"><b>{html.escape(label)}</b></div>')
                first_para = False
            rendered_list = render_list(child, asset_prefix, level=1, collapse_seed=label.lower().replace(" ", "-"))
            blocks.append(f'<div class="{css_class}">{rendered_list}</div>')

    if first_para:
        blocks.append(f'<div class="{css_class} mrf-para"><b>{html.escape(label)}</b></div>')

    group_slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f'<div class="mrf-detail-group mrf-detail-group-{group_slug}">{"".join(blocks)}</div>'


def build_detail_collapse(
    collapse_seed: str,
    detail_groups: Sequence[str],
    toggle_context: str,
    *,
    body_aligned: bool = False,
) -> tuple[str, str]:
    if not detail_groups:
        return "", ""

    collapse_id = "detail-" + re.sub(r"[^A-Za-z0-9]+", "-", collapse_seed).strip("-")
    detail_html = (
        f'\n                            <div class="collapse" id="{collapse_id}">\n'
        "                                <hr />\n"
        f"{indent_block(chr(10).join(detail_groups), 32)}\n"
        "                                <hr />\n"
        "                            </div>"
    )
    if body_aligned:
        detail_html = render_body_block(detail_html)
    toggle_title = f"Show or hide {toggle_context}"
    toggle_html = (
        '\n                            <span class="float-right">\n'
        f'                                <a class="text-success more collapsed" data-toggle="collapse" href="#{collapse_id}" aria-label="{html.escape(toggle_title, quote=True)}" title="{html.escape(toggle_title, quote=True)}"></a>\n'
        "                            </span>"
    )
    return toggle_html, detail_html


def render_detail_group(node: etree._Element, asset_prefix: str, *, glossary_context: bool = False) -> str:
    name = local_name(node)
    if name == "example":
        rendered = render_group(node, asset_prefix, "text-danger", "Example:")
        return rendered
    if name == "note":
        role = (node.get("role") or "").lower()
        if role == "technical-comment":
            rendered = render_group(node, asset_prefix, "text-muted", "Technical comment:")
            return rendered
        rendered = render_group(node, asset_prefix, "text-primary", "Further explanation:")
        return rendered
    if name == "mediaobject":
        rendered = render_mediaobject(node, asset_prefix)
        return rendered if glossary_context else render_body_block(rendered)
    if name in {"itemizedlist", "orderedlist"}:
        rendered = render_list(node, asset_prefix)
        return rendered if glossary_context else (render_body_block(rendered) if name == "itemizedlist" else rendered)
    if name == "informaltable":
        rendered = render_informaltable(node, asset_prefix)
        return rendered if glossary_context else render_body_block(rendered)
    return ""


def split_section_title(title: str) -> tuple[str, str]:
    match = re.match(r"^(\d+\.)\s+(.*)$", title)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r"^([A-Z]\.)\s+(.*)$", title)
    if match:
        return match.group(1), match.group(2)
    match = re.match(r"^([a-z]\d*\))\s+(.*)$", title)
    if match:
        return match.group(1), match.group(2)
    return "", title


def context_seed(node: etree._Element, fallback: str) -> str:
    xml_id = node.get("{http://www.w3.org/XML/1998/namespace}id", "").strip()
    if xml_id:
        return xml_id
    title = read_text(node.find("db:title", NS))
    if title:
        return title
    return fallback


def numbered_list_item_id(collapse_seed: str, index: int) -> str:
    return f"mrf-{schema_fragment(collapse_seed)}-{index}"


def table_row_id(collapse_seed: str, index: int) -> str:
    return f"mrf-{schema_fragment(collapse_seed)}-{index}"


def main_heading(title: str, subtitle: str) -> str:
    section_match = re.search(r"Section\s+(\d+)", subtitle)
    if section_match and not re.match(rf"^{section_match.group(1)}\.\s+", title):
        return f"{section_match.group(1)}. {title}"
    appendix_match = re.search(r"Appendix\s+([A-Z])", subtitle)
    if appendix_match and not re.match(rf"^Appendix\s+{appendix_match.group(1)}\.\s+", title):
        return f"Appendix {appendix_match.group(1)}. {title}"
    return title


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def entry_number_text(entry: etree._Element) -> str:
    number = entry.get(f"{{{NS['mrf']}}}number", "")
    if not number:
        return ""
    local_number = re.sub(r"^[A-Z]\.", "", number)
    return local_number if local_number.endswith(".") else local_number + "."


def entry_term(entry: etree._Element) -> str:
    return read_text(entry.find("db:glossterm", NS))


def render_glossdef(glossdef: etree._Element, asset_prefix: str) -> tuple[list[str], list[str]]:
    main_blocks: list[str] = []
    detail_groups: list[str] = []
    glossdef_seed = context_seed(glossdef.getparent() if glossdef.getparent() is not None else glossdef, "glossdef")
    saw_detail_group = False
    saw_direct_list = False

    for index, child in enumerate(glossdef, start=1):
        name = local_name(child)
        if name == "para":
            main_blocks.append(render_para(child, asset_prefix))
        elif name == "informaltable":
            main_blocks.append(render_informaltable(child, asset_prefix))
        elif name in {"itemizedlist", "orderedlist"}:
            target = detail_groups if saw_detail_group else main_blocks
            list_level = 0 if not saw_direct_list else 1
            target.append(
                render_list(child, asset_prefix, level=list_level, collapse_seed=f"{glossdef_seed}-{name}-{index}")
            )
            saw_direct_list = True
        elif name in {"example", "note", "mediaobject"}:
            saw_detail_group = True
            rendered = render_detail_group(child, asset_prefix, glossary_context=True)
            if rendered:
                detail_groups.append(rendered)

    return main_blocks, detail_groups


def render_term_label(term: str) -> str:
    return html.escape(term)


def render_block_children(node: etree._Element, asset_prefix: str, *, skip_titles: bool = True, skip_entries: bool = True) -> list[str]:
    blocks: list[str] = []
    node_seed = context_seed(node, local_name(node))
    for index, child in enumerate(node, start=1):
        name = local_name(child)
        if skip_titles and name == "title":
            continue
        if skip_entries and name == "glossentry":
            continue
        if name == "para":
            blocks.append(render_body_para(child, asset_prefix))
        elif name in {"itemizedlist", "orderedlist"}:
            rendered = render_list(child, asset_prefix, collapse_seed=f"{node_seed}-{name}-{index}")
            blocks.append(render_body_block(rendered) if name == "itemizedlist" else rendered)
        elif name in {"example", "note", "mediaobject"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                blocks.append(rendered)
        elif name == "informaltable":
            blocks.append(render_informaltable(child, asset_prefix))
        elif name == "section":
            blocks.append(render_section(child, asset_prefix))
    return [block for block in blocks if block]


def render_entry(entry: etree._Element, asset_prefix: str) -> str:
    term = entry_term(entry)
    number = entry_number_text(entry)
    glossdef = entry.find("db:glossdef", NS)
    if glossdef is None:
        return ""

    main_blocks, detail_groups = render_glossdef(glossdef, asset_prefix)
    toggle_html, detail_html = build_detail_collapse(
        entry.get("{http://www.w3.org/XML/1998/namespace}id", "entry"),
        detail_groups,
        f"details for {term or number or 'this entry'}",
    )

    content = indent_block("\n".join(main_blocks), 28) if main_blocks else ""
    entry_id = entry.get("{http://www.w3.org/XML/1998/namespace}id", "")
    row_id_attr = f' id="{html.escape(entry_id, quote=True)}"' if entry_id else ""
    row_term_attr = f' data-glossterm="{html.escape(term, quote=True)}"' if term else ""
    rendered_term = render_term_label(term)

    if term and number:
        return (
            f"                    <div class=\"row mrf-glossary-row\"{row_id_attr}{row_term_attr}>\n"
            "                        <div class=\"col-sm-1\">\n"
            f"                            {html.escape(number)}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-2 col-sm-3\">\n"
            f"                            {rendered_term}{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-9 col-sm-8\">\n"
            f"{content}\n"
            f"{indent_block(render_glossary_detail_block(detail_html), 28) if detail_html else ''}\n"
            "                        </div>\n"
            "                    </div>"
        )

    if term and not number:
        return (
            f"                    <div class=\"row mrf-glossary-row\"{row_id_attr}{row_term_attr}>\n"
            "                        <div class=\"col-xl-2 col-sm-3\">\n"
            f"                            {rendered_term}{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-10 col-sm-9\">\n"
            f"{content}\n"
            f"{indent_block(render_glossary_detail_block(detail_html), 28) if detail_html else ''}\n"
            "                        </div>\n"
            "                    </div>"
        )

    if not term and number:
        return (
            f"                    <div class=\"row mrf-glossary-row\"{row_id_attr}>\n"
            "                        <div class=\"col-sm-1\">\n"
            f"                            {html.escape(number)}\n"
            "                        </div>\n"
            "                        <div class=\"col-sm-11\">\n"
            f"{indent_block(content, 28) if content else ''}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )

    return "\n".join(main_blocks + detail_groups)


def blank_unheaded_entry(entry: etree._Element) -> bool:
    return not entry_term(entry) and not entry_number_text(entry)


def render_glossdiv(glossdiv: etree._Element, asset_prefix: str, show_header: bool) -> str:
    title = read_text(glossdiv.find("db:title", NS))
    marker, name = split_section_title(title)
    section_id = glossdiv.get("{http://www.w3.org/XML/1998/namespace}id", "")
    entries = glossdiv.findall("db:glossentry", NS)

    if len(entries) == 1 and blank_unheaded_entry(entries[0]) and show_header:
        glossdef = entries[0].find("db:glossdef", NS)
        main_blocks, detail_groups = render_glossdef(glossdef, asset_prefix) if glossdef is not None else ([], [])
        toggle_html, detail_html = build_detail_collapse(
            section_id or title or "section",
            detail_groups,
            f"details for section {marker or name or title}",
        )
        combined_content = "\n".join(part for part in main_blocks if part).strip()
        return (
            f'                    <div class="row mrf-heading-row" id="{html.escape(section_id, quote=True)}">\n'
            '                        <div class="col-sm-1">\n'
            f"                            <h5>{html.escape(marker)}{toggle_html}</h5>\n"
            "                        </div>\n"
            '                        <div class="col-sm-11">\n'
            f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
            "                        </div>\n"
            "                    </div>\n\n"
            f"{indent_block(combined_content, 28) if combined_content else ''}{detail_html}"
        )

    header_html = ""
    if show_header:
        header_html = (
            f'                    <div class="row mrf-heading-row" id="{html.escape(section_id, quote=True)}">\n'
            '                        <div class="col-sm-1">\n'
            f"                            <h5>{html.escape(marker)}</h5>\n"
            "                        </div>\n"
            '                        <div class="col-sm-11">\n'
            f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
            "                        </div>\n"
            "                    </div>\n\n"
        )

    body_parts: list[str] = []
    glossentry_count = 0
    orderedlist_started = False
    for index, child in enumerate(glossdiv, start=1):
        child_name = local_name(child)
        if child_name == "title":
            continue
        if child_name == "glossentry":
            glossentry_count += 1
            rendered = render_entry(child, asset_prefix)
        elif child_name == "para":
            rendered = render_body_para(child, asset_prefix)
        elif child_name == "informaltable":
            rendered = render_body_block(render_informaltable(child, asset_prefix))
        elif child_name in {"itemizedlist", "orderedlist"}:
            if child_name == "orderedlist" and not orderedlist_started and glossentry_count > 0 and not child.get("startingnumber"):
                child.set("startingnumber", str(glossentry_count + 1))
                orderedlist_started = True
            rendered = render_list(
                child,
                asset_prefix,
                collapse_seed=f"{context_seed(glossdiv, title or 'glossdiv')}-{child_name}-{index}",
                top_level=True,
            )
            if child_name == "itemizedlist":
                rendered = render_body_block(rendered)
        elif child_name in {"example", "note", "mediaobject"}:
            rendered = render_detail_group(child, asset_prefix)
        else:
            rendered = ""
        if rendered:
            body_parts.append(rendered)
    return header_html + "\n\n".join(body_parts)


def render_section(section: etree._Element, asset_prefix: str) -> str:
    title = read_text(section.find("db:title", NS))
    main_blocks: list[str] = []
    detail_groups: list[str] = []
    section_seed = context_seed(section, title or "section")
    for index, child in enumerate(section, start=1):
        child_name = local_name(child)
        if child_name == "title":
            continue
        if child_name == "para":
            main_blocks.append(render_body_para(child, asset_prefix))
        elif child_name == "informaltable":
            rendered = render_informaltable(child, asset_prefix)
            if (child.get("role") or "").strip() in {"amended-method-titles", "amended-method-titles-summary"}:
                rendered = render_body_block(rendered)
            main_blocks.append(rendered)
        elif child_name in {"itemizedlist", "orderedlist"}:
            rendered = render_list(
                child,
                asset_prefix,
                collapse_seed=f"{section_seed}-{child_name}-{index}",
                top_level=True,
            )
            main_blocks.append(render_body_block(rendered) if child_name == "itemizedlist" else rendered)
        elif child_name == "mediaobject":
            main_blocks.append(render_body_block(render_mediaobject(child, asset_prefix)))
        elif child_name in {"example", "note"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                detail_groups.append(rendered)
        elif child_name == "section":
            main_blocks.append(render_section(child, asset_prefix))
        else:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                main_blocks.append(rendered)
    content_html = "\n".join(main_blocks)
    if not title:
        return content_html

    marker, name = split_section_title(title)
    section_id = section.get("{http://www.w3.org/XML/1998/namespace}id", "")
    toggle_html, detail_html = build_detail_collapse(
        section_id or title,
        detail_groups,
        f"details for section {marker or name or title}",
        body_aligned=True,
    )
    return (
        f'                    <div class="row mrf-heading-row" id="{html.escape(section_id, quote=True)}">\n'
        '                        <div class="col-sm-1">\n'
        f"                            <h5>{html.escape(marker)}{toggle_html}</h5>\n"
        "                        </div>\n"
        '                        <div class="col-sm-11">\n'
        f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
        "                        </div>\n"
        "                    </div>\n\n"
        f"{content_html}{detail_html}"
    )


def render_sidebar(sidebar_pages: Sequence[SidebarPage]) -> str:
    items: list[str] = []
    for page in sidebar_pages:
        entry_parts: list[str] = []
        if page.appendices_header:
            entry_parts.append("                        <br />&nbsp;&nbsp;&nbsp;&nbsp;<u>Appendices</u><br />")

        active_class = " active" if page.active else ""
        entry_parts.append(
            f'                        <a class="nav-link{active_class}" href="{html.escape(page.href, quote=True)}">{html.escape(page.label)}</a>'
        )

        if page.active and page.subsections:
            subsection_items = []
            for subsection in page.subsections:
                subsection_items.append(
                    "                            <li class=\"nav-item\">\n"
                    f'                                <a class="nav-link" href="{html.escape(subsection.href, quote=True)}">{html.escape(subsection.title)}</a>\n'
                    "                            </li>"
                )
            entry_parts.append(
                '                        <ul class="nav nav-pills flex-column nav-subsection">\n'
                + "\n".join(subsection_items)
                + "\n                        </ul>"
            )

        items.append(
            "                    <li class=\"nav-item\">\n"
            + "\n".join(entry_parts)
            + "\n                    </li>"
        )

    return '                <ul class="nav nav-pills flex-column">\n' + "\n".join(items) + "\n                </ul>"


def render_version_switcher(version_options: Sequence[VersionOption] | None, switch_version_href: str) -> str:
    if not version_options:
        return f'<small><a id="switchv" href="{html.escape(switch_version_href, quote=True)}">[Switch version]</a></small>'

    active_option = next((option for option in version_options if option.active), version_options[0])
    menu_parts: list[str] = []
    for option in version_options:
        active_class = " active" if option.active else ""
        active_suffix = " <span class=\"sr-only\">(current)</span>" if option.active else ""
        menu_parts.append(
            f'                    <a class="dropdown-item{active_class}" href="{html.escape(option.href, quote=True)}">'
            f"{html.escape(option.label)}{active_suffix}</a>"
        )

    return (
        '            <div class="dropdown ml-2">\n'
        '                <button class="btn btn-sm btn-outline-light dropdown-toggle" type="button" id="versionSwitcher" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">\n'
        f"                    {html.escape(active_option.button_label)}\n"
        "                </button>\n"
        '                <div class="dropdown-menu dropdown-menu-right" aria-labelledby="versionSwitcher">\n'
        + "\n".join(menu_parts)
        + "\n                </div>\n"
        "            </div>"
    )


def build_schema_metadata(
    article: etree._Element,
    *,
    page_url: str,
    title: str,
    description: str,
    schema_version: SchemaVersionContext | None,
) -> str:
    if not page_url:
        return ""

    publisher_id = "https://cccbr.org.uk/#publisher"
    graph: list[dict[str, object]] = [
        {
            "@id": publisher_id,
            "@type": "Organization",
            "name": "CCCBR",
            "url": "https://cccbr.org.uk/",
        }
    ]

    version_label = schema_version.edition_label if schema_version else article.get(f"{{{NS['mrf']}}}edition-label", "")
    version_url = schema_version.version_url if schema_version else page_url
    term_set_id = f"{version_url}#defined-term-set-{schema_fragment(version_label or title)}"

    creative_work: dict[str, object] = {
        "@id": page_url,
        "@type": "CreativeWork",
        "name": title,
        "url": page_url,
        "description": description,
        "publisher": {"@id": publisher_id},
    }
    if version_label:
        creative_work["version"] = version_label
    if schema_version:
        creative_work["isBasedOn"] = {"@id": term_set_id}
        if schema_version.approval_date:
            creative_work["datePublished"] = schema_version.approval_date
        if schema_version.superseded_by_url:
            creative_work["supersededBy"] = {"@id": schema_version.superseded_by_url}
    graph.append(creative_work)

    term_set: dict[str, object] = {
        "@id": term_set_id,
        "@type": "DefinedTermSet",
        "name": f"Framework for Method Ringing {version_label}".strip(),
        "url": version_url,
        "publisher": {"@id": publisher_id},
        "isPartOf": {"@id": page_url},
    }
    if version_label:
        term_set["version"] = version_label
    if schema_version and schema_version.superseded_by_url:
        term_set["supersededBy"] = {"@id": schema_version.superseded_by_url}

    term_ids: list[dict[str, str]] = []
    for entry in article.findall(".//db:glossentry", NS):
        term = read_text(entry.find("db:glossterm", NS))
        if not term:
            continue

        entry_id = entry.get("{http://www.w3.org/XML/1998/namespace}id") or f"term-{schema_fragment(term)}"
        term_url = f"{page_url}#{entry_id}"
        term_object: dict[str, object] = {
            "@id": term_url,
            "@type": "DefinedTerm",
            "name": term,
            "url": term_url,
            "inDefinedTermSet": {"@id": term_set_id},
        }

        number = entry.get(f"{{{NS['mrf']}}}number", "").strip()
        if number:
            term_object["termCode"] = number

        glossdef = entry.find("db:glossdef", NS)
        description_node = glossdef.find("db:para", NS) if glossdef is not None else None
        term_description = read_text(description_node)
        if term_description:
            term_object["description"] = term_description

        graph.append(term_object)
        term_ids.append({"@id": term_url})

    if term_ids:
        term_set["hasDefinedTerm"] = term_ids
    graph.append(term_set)

    return json.dumps({"@context": "https://schema.org", "@graph": graph}, indent=4)


def build_glossary_autolink_data(
    glossary_terms: Sequence[GlossaryTermLink],
    current_page_href: str,
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    unique_terms: dict[str, GlossaryTermLink] = {}
    for glossary_term in glossary_terms:
        normalized = collapse_ws(glossary_term.term, strip=True)
        if not normalized:
            continue
        unique_terms.setdefault(normalized.casefold(), glossary_term)

    ordered_terms = sorted(
        unique_terms.values(),
        key=lambda item: (-len(item.term), item.term.casefold()),
    )
    if not ordered_terms:
        return None, {}

    pattern = re.compile(
        rf"(?<![A-Za-z0-9])(?:{'|'.join(re.escape(item.term) for item in ordered_terms)})(?![A-Za-z0-9])",
        re.IGNORECASE,
    )
    hrefs = {
        item.term.casefold(): (
            f"#{item.anchor_id}" if item.page_href == current_page_href else f"{item.page_href}#{item.anchor_id}"
        )
        for item in ordered_terms
    }
    return pattern, hrefs


def build_cross_reference_autolink_data(
    cross_reference_links: Sequence[CrossReferenceLink],
    current_page_href: str,
) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    unique_links: dict[str, CrossReferenceLink] = {}
    for link in cross_reference_links:
        normalized = collapse_ws(link.label, strip=True)
        if not normalized:
            continue
        unique_links.setdefault(normalized.casefold(), CrossReferenceLink(normalized, link.href))

    ordered_links = sorted(
        unique_links.values(),
        key=lambda item: (-len(item.label), item.label.casefold()),
    )
    if not ordered_links:
        return None, {}

    pattern = re.compile(
        rf"(?<![A-Za-z0-9])(?:{'|'.join(re.escape(item.label) for item in ordered_links)})(?![A-Za-z0-9]|\.[A-Za-z0-9])",
        re.IGNORECASE,
    )
    hrefs = {
        item.label.casefold(): (
            f"#{item.href.split('#', 1)[1]}"
            if item.href.startswith(f"{current_page_href}#")
            else item.href
        )
        for item in ordered_links
    }
    return pattern, hrefs


def article_reference_scope(subtitle: str) -> tuple[str, str] | tuple[None, None]:
    section_match = re.search(r"Section\s+(\d+)", subtitle)
    if section_match:
        return "Section", section_match.group(1)
    appendix_match = re.search(r"Appendix\s+([A-Z])", subtitle)
    if appendix_match:
        return "Appendix", appendix_match.group(1)
    return None, None


def add_cross_reference_link(
    links: dict[str, CrossReferenceLink],
    label: str,
    href: str,
) -> None:
    normalized = collapse_ws(label, strip=True)
    if not normalized:
        return
    links.setdefault(normalized.casefold(), CrossReferenceLink(normalized, href))


def add_prefixed_cross_reference_link(
    links: dict[str, CrossReferenceLink],
    page_kind: str,
    label: str,
    href: str,
) -> None:
    add_cross_reference_link(links, label, href)
    add_cross_reference_link(links, f"{page_kind} {label}", href)


def build_cross_reference_links(article: etree._Element, page_href: str) -> list[CrossReferenceLink]:
    info = article.find("db:info", NS)
    subtitle = read_text(info.find("db:subtitle", NS) if info is not None else None)
    page_kind, page_code = article_reference_scope(subtitle)
    if not page_kind or not page_code:
        return []

    links: dict[str, CrossReferenceLink] = {}
    add_cross_reference_link(links, f"{page_kind} {page_code}", page_href)

    glossary = article.find("db:glossary", NS)
    if glossary is not None:
        for glossdiv in glossary.findall("db:glossdiv", NS):
            div_title = read_text(glossdiv.find("db:title", NS))
            marker, _ = split_section_title(div_title)
            if marker:
                xml_id = glossdiv.get("{http://www.w3.org/XML/1998/namespace}id", "")
                href = f"{page_href}#{xml_id}" if xml_id else page_href
                add_prefixed_cross_reference_link(links, page_kind, f"{page_code}.{marker.rstrip('.')}", href)
            for entry in glossdiv.findall("db:glossentry", NS):
                number = (entry.get(f"{{{NS['mrf']}}}number") or "").strip()
                if not number:
                    continue
                entry_id = entry.get("{http://www.w3.org/XML/1998/namespace}id", "")
                href = f"{page_href}#{entry_id}" if entry_id else page_href
                add_prefixed_cross_reference_link(links, page_kind, f"{page_code}.{number}", href)
            for child_index, child in enumerate(glossdiv, start=1):
                if local_name(child) != "orderedlist":
                    continue

                item_prefix = f"{page_code}.{marker.rstrip('.')}" if marker else page_code
                collapse_seed = f"{context_seed(glossdiv, div_title or 'glossdiv')}-{local_name(child)}-{child_index}"
                for item_index, _item in enumerate(child.findall("db:listitem", NS), start=list_start(child)):
                    row_id = numbered_list_item_id(collapse_seed, item_index)
                    add_prefixed_cross_reference_link(links, page_kind, f"{item_prefix}.{item_index}", f"{page_href}#{row_id}")

    for section in article.findall("db:section", NS):
        section_title = read_text(section.find("db:title", NS))
        marker, _ = split_section_title(section_title)
        section_id = section.get("{http://www.w3.org/XML/1998/namespace}id", "")
        if marker and section_id:
            add_prefixed_cross_reference_link(links, page_kind, f"{page_code}.{marker.rstrip('.')}", f"{page_href}#{section_id}")

        section_seed = context_seed(section, section_title or "section")
        for child_index, child in enumerate(section, start=1):
            child_name = local_name(child)
            if child_name == "orderedlist":
                item_prefix = f"{page_code}.{marker.rstrip('.')}" if marker else page_code
                collapse_seed = f"{section_seed}-{child_name}-{child_index}"
                for item_index, _item in enumerate(child.findall("db:listitem", NS), start=list_start(child)):
                    row_id = numbered_list_item_id(collapse_seed, item_index)
                    add_prefixed_cross_reference_link(links, page_kind, f"{item_prefix}.{item_index}", f"{page_href}#{row_id}")
            elif child_name == "informaltable" and (child.get("role") or "").strip() == "related-material":
                row_prefix = page_code
                collapse_seed = f"{section_seed}-{child_name}-{child_index}"
                table_rows = child.findall("db:tgroup/db:tbody/db:row", NS)
                if not table_rows:
                    table_rows = child.findall("db:tbody/db:row", NS)
                if not table_rows:
                    table_rows = child.findall("db:row", NS)
                for row_index, _row in enumerate(table_rows, start=1):
                    row_id = table_row_id("related-material", row_index)
                    add_prefixed_cross_reference_link(links, page_kind, f"{row_prefix}.{row_index}", f"{page_href}#{row_id}")

    return list(links.values())


def build_site_cross_reference_links(source_dir: Path) -> list[CrossReferenceLink]:
    links: list[CrossReferenceLink] = []
    parser = etree.XMLParser(remove_blank_text=False)
    for xml_path in sorted(source_dir.glob("*.xml")):
        try:
            article = etree.parse(str(xml_path), parser).getroot()
        except OSError:
            continue
        page_href = xml_path.with_suffix(".html").name
        links.extend(build_cross_reference_links(article, page_href))
    return links


def linkify_text_segments(
    text: str,
    pattern: re.Pattern[str],
    hrefs_by_term: dict[str, str],
    excluded_terms: frozenset[str],
) -> list[tuple[str, str, str]] | None:
    segments: list[tuple[str, str, str]] = []
    cursor = 0
    replaced = False

    for match in pattern.finditer(text):
        matched_text = match.group(0)
        matched_key = matched_text.casefold()
        href = hrefs_by_term.get(matched_key)
        if href is None or matched_key in excluded_terms:
            continue

        if match.start() > cursor:
            segments.append(("text", text[cursor:match.start()], ""))
        segments.append(("link", matched_text, href))
        cursor = match.end()
        replaced = True

    if not replaced:
        return None

    if cursor < len(text):
        segments.append(("text", text[cursor:], ""))
    return segments


def replace_element_text(
    parent: etree._Element,
    text: str,
    pattern: re.Pattern[str],
    hrefs_by_term: dict[str, str],
    excluded_terms: frozenset[str],
) -> None:
    segments = linkify_text_segments(text, pattern, hrefs_by_term, excluded_terms)
    if not segments:
        return

    parent.text = None
    previous: etree._Element | None = None
    insert_index = 0
    for segment_type, value, href in segments:
        if segment_type == "text":
            if previous is None:
                parent.text = (parent.text or "") + value
            else:
                previous.tail = (previous.tail or "") + value
            continue

        anchor = etree.Element("a")
        anchor.set("class", "text-success undrln")
        anchor.set("href", href)
        anchor.text = value
        if previous is None:
            parent.insert(insert_index, anchor)
            insert_index += 1
        else:
            previous.addnext(anchor)
        previous = anchor


def replace_tail_text(
    node: etree._Element,
    text: str,
    pattern: re.Pattern[str],
    hrefs_by_term: dict[str, str],
    excluded_terms: frozenset[str],
) -> None:
    segments = linkify_text_segments(text, pattern, hrefs_by_term, excluded_terms)
    if not segments:
        return

    node.tail = None
    previous = node
    for segment_type, value, href in segments:
        if segment_type == "text":
            previous.tail = (previous.tail or "") + value
            continue

        anchor = etree.Element("a")
        anchor.set("class", "text-success undrln")
        anchor.set("href", href)
        anchor.text = value
        previous.addnext(anchor)
        previous = anchor


def autolink_html_element(
    element: etree._Element,
    pattern: re.Pattern[str],
    hrefs_by_term: dict[str, str],
    excluded_terms: frozenset[str] = frozenset(),
) -> None:
    tag_name = (element.tag or "").lower() if isinstance(element.tag, str) else ""
    if tag_name in {"a", "code", "script", "style", "h1", "h2", "h3", "h4", "h5", "h6"}:
        return
    element_classes = set((element.get("class") or "").split())
    if "mrf-faq-question" in element_classes or "mrf-nolink" in element_classes:
        return

    scoped_exclusions = excluded_terms
    definition_term = collapse_ws(element.get("data-glossterm"), strip=True)
    if definition_term:
        scoped_exclusions = excluded_terms | {definition_term.casefold()}

    original_children = list(element)
    if element.text:
        replace_element_text(element, element.text, pattern, hrefs_by_term, scoped_exclusions)

    for child in original_children:
        autolink_html_element(child, pattern, hrefs_by_term, scoped_exclusions)
        if child.tail:
            replace_tail_text(child, child.tail, pattern, hrefs_by_term, scoped_exclusions)


def autolink_glossary_terms(
    html_text: str,
    glossary_terms: Sequence[GlossaryTermLink],
    current_page_href: str,
) -> str:
    pattern, hrefs_by_term = build_glossary_autolink_data(glossary_terms, current_page_href)
    if pattern is None or not hrefs_by_term:
        return html_text

    document = lxml_html.document_fromstring(html_text)
    main = document.find(".//main")
    if main is None:
        return html_text

    autolink_html_element(main, pattern, hrefs_by_term)
    return lxml_html.tostring(document, encoding="unicode", method="html", doctype="<!DOCTYPE html>")


def autolink_cross_references(
    html_text: str,
    cross_reference_links: Sequence[CrossReferenceLink],
    current_page_href: str,
) -> str:
    pattern, hrefs_by_term = build_cross_reference_autolink_data(cross_reference_links, current_page_href)
    if pattern is None or not hrefs_by_term:
        return html_text

    document = lxml_html.document_fromstring(html_text)
    main = document.find(".//main")
    if main is None:
        return html_text

    autolink_html_element(main, pattern, hrefs_by_term)
    return lxml_html.tostring(document, encoding="unicode", method="html", doctype="<!DOCTYPE html>")


def build_html(
    article: etree._Element,
    asset_prefix: str,
    page_href: str,
    switch_version_href: str,
    *,
    sidebar_pages: Sequence[SidebarPage] | None = None,
    version_options: Sequence[VersionOption] | None = None,
    home_href: str | None = None,
    schema_version: SchemaVersionContext | None = None,
    glossary_terms: Sequence[GlossaryTermLink] = (),
    cross_reference_links: Sequence[CrossReferenceLink] = (),
) -> str:
    info = article.find("db:info", NS)
    title = read_text(info.find("db:title", NS) if info is not None else None)
    subtitle = read_text(info.find("db:subtitle", NS) if info is not None else None)
    canonical = read_text(info.find('db:uri[@type="canonical"]', NS) if info is not None else None)
    glossdivs = article.findall("db:glossary/db:glossdiv", NS)
    sections = article.findall("db:section", NS)
    heading = main_heading(title, subtitle)
    description = f"{title} ({article.get(f'{{{NS['mrf']}}}status', 'working')} edition {article.get(f'{{{NS['mrf']}}}framework-version', '')})".strip()

    if glossdivs:
        skip_redundant_header = len(glossdivs) == 1 and read_text(glossdivs[0].find("db:title", NS)) == heading
        section_html = "\n\n".join(render_glossdiv(glossdiv, asset_prefix, not skip_redundant_header) for glossdiv in glossdivs)
        sidebar_nodes = glossdivs
    else:
        section_html = "\n\n".join(render_section(section, asset_prefix) for section in sections)
    if sidebar_pages:
        sidebar = render_sidebar(sidebar_pages)
    else:
        fallback_subsections = []
        section_nodes = glossdivs if glossdivs else sections
        for section_node in section_nodes:
            section_title = read_text(section_node.find("db:title", NS))
            if not re.match(r"^[A-Z]\.\s+", section_title):
                continue
            section_id = section_node.get("{http://www.w3.org/XML/1998/namespace}id", "")
            fallback_subsections.append(SidebarSubsection(title=section_title, href=f"#{section_id}"))
        sidebar = render_sidebar(
            [SidebarPage(label=heading, href=page_href, active=True, subsections=tuple(fallback_subsections))]
        )
    version_switcher = render_version_switcher(version_options, switch_version_href)
    page_home_href = home_href or join_href(asset_prefix, "index.html")
    schema_json = build_schema_metadata(
        article,
        page_url=canonical or page_href,
        title=title,
        description=description,
        schema_version=schema_version,
    )
    schema_block = (
        f'    <script type="application/ld+json">\n{indent_block(schema_json, 8)}\n    </script>\n'
        if schema_json
        else ""
    )

    html_text = f"""<!DOCTYPE html>
<html lang="en">
<head prefix="og: http://ogp.me/ns/#">
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <meta name="description" content="{html.escape(description, quote=True)}">
    <meta name="author" content="CCCBR">
    <link rel="icon" href="https://cccbr.org.uk/wp-content/uploads/2016/05/cropped-icon-45x45.jpg" sizes="32x32">
    <link rel="icon" href="https://cccbr.org.uk/wp-content/uploads/2016/05/cropped-icon-250x250.jpg" sizes="192x192">
    <link rel="apple-touch-icon-precomposed" href="https://cccbr.org.uk/wp-content/uploads/2016/05/cropped-icon-180x180.jpg">
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="CCCBR">
    <meta property="og:title" content="CCCBR - Framework for Method Ringing">
    <meta property="og:description" content="{html.escape(description, quote=True)}">
    <meta property="og:image" content="https://cccbr.org.uk/wp-content/uploads/2017/02/CCCBR_Logo_col_rev.jpg">
    <meta property="og:url" content="{html.escape(canonical or page_href, quote=True)}">
    <title>Framework for Method Ringing - {html.escape(title)}</title>
    <link href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0-beta/css/bootstrap.min.css" rel="stylesheet">
    <link href="{html.escape(join_href(asset_prefix, 'mrf.css'), quote=True)}" rel="stylesheet">
{schema_block.rstrip()}
</head>
<body>
    <header>
        <nav class="navbar navbar-expand-md navbar-dark fixed-top bg-cccbr">
            <a class="navbar-brand" href="{html.escape(page_home_href, quote=True)}">Framework for Method Ringing&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</a>
            <a class="navbar-brand" href="https://cccbr.org.uk/"><img src="{html.escape(join_href(asset_prefix, 'images/cc-header.png'), quote=True)}" height="60" alt="CCCBR">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</a>
{indent_block(version_switcher, 12)}
        </nav>
    </header>

    <div class="container-fluid collapse-group">
        <div class="row">
            <nav class="col-sm-3 col-xl-2 d-none d-sm-block bg-light sidebar">
{indent_block(sidebar, 16)}
                <div class="btn-navbar">
                    <button class="btn btn-sm btn-block btn-success open-button" type="button">Show all notes</button>
                    <div class="text-success"><small>Click + to show a note.</small></div>
                    <button class="btn btn-sm btn-block btn-success close-button" type="button">Hide all notes</button>
                </div>
            </nav>

            <main role="main" class="col-sm-9 ml-sm-auto col-xl-10 pt-3">
                <div class="container-fluid">
                    <div class="row">
                        <div class="col-sm-12">
                            <h2>{html.escape(heading)}</h2>
                        </div>
                    </div>

{section_html}
                </div>
            </main>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.2.1.slim.min.js" integrity="sha384-KJ3o2DKtIkvYIK3UENzmM7KCkRr/rE9/Qpg6aAZGJwFDMVNA/GpGFF93hXpG5KkN" crossorigin="anonymous"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.11.0/umd/popper.min.js" integrity="sha384-b/U6ypiBEHpOf/4+1nzFpr53nxSS+GLCkfwBdFNTxtclqqenISfwAzpKaMNFNmj4" crossorigin="anonymous"></script>
    <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0-beta/js/bootstrap.min.js" integrity="sha384-h0AbiXch4ZDo7tp9hKZ4TsHbi047NrKGLO3SEJAg45jXxnGIfYzk4Si90RDIqNm1" crossorigin="anonymous"></script>
    <script src="{html.escape(join_href(asset_prefix, 'mrf.js'), quote=True)}"></script>
</body>
</html>
"""
    html_text = autolink_glossary_terms(html_text, glossary_terms, page_href)
    return autolink_cross_references(html_text, cross_reference_links, page_href)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert DocBook XML back into HTML.")
    parser.add_argument("input", help="Path to the input DocBook XML file")
    parser.add_argument("output", help="Path to the output HTML file")
    parser.add_argument("--asset-prefix", default="", help="Prefix to prepend to local site assets and relative links")
    parser.add_argument("--page-href", default=None, help="Sidebar link for the active page")
    parser.add_argument("--switch-version-href", default="../index.html", help="Link used by the [Switch version] control")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    article = etree.parse(str(input_path), etree.XMLParser(remove_blank_text=False)).getroot()
    cross_reference_links = build_site_cross_reference_links(input_path.parent)
    html_text = build_html(
        article,
        asset_prefix=args.asset_prefix,
        page_href=args.page_href or output_path.name,
        switch_version_href=args.switch_version_href,
        cross_reference_links=cross_reference_links,
    )
    output_path.write_text(html_text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
