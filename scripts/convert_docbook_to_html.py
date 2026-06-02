#!/usr/bin/env python3
"""Render DocBook XML back to HTML styled like the original site."""

from __future__ import annotations

import argparse
import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from lxml import etree


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
    class_attr = f' class="{css_class}"' if css_class else ""
    return f"<p{class_attr}>{body}</p>"


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
    return f"<p><img {' '.join(attrs)} /></p>"


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


def render_informaltable(node: etree._Element, asset_prefix: str) -> str:
    role = (node.get("role") or "").strip()
    role_class = " mrf-code-table" if role == "leadhead-codes" else ""
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
    return (
        f'<div class="table-responsive"><table class="table table-sm table-bordered mrf-table{role_class}">'
        f"{thead_html}{tbody_html}</table></div>"
    )


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
        elif child_name in {"itemizedlist", "orderedlist"}:
            main_blocks.append(render_list(child, asset_prefix, level=level + 1, collapse_seed=f"{collapse_seed}-{index}"))
        elif child_name in {"example", "note"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                detail_groups.append(rendered)

    return main_blocks, detail_groups


def render_numbered_list(node: etree._Element, asset_prefix: str, *, level: int, collapse_seed: str) -> str:
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
        content = indent_block("\n".join(main_blocks), 28) if main_blocks else ""
        items.append(
            "                    <div class=\"row mrf-numbered-item mrf-numbered-level-0\">\n"
            "                        <div class=\"col-sm-1 mrf-numbered-marker\">\n"
            f"                            {index}.{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-sm-11 mrf-numbered-content\">\n"
            f"{content}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )
    return "\n\n".join(items)


def render_list(node: etree._Element, asset_prefix: str, level: int = 0, collapse_seed: str | None = None) -> str:
    if collapse_seed is None:
        collapse_seed = f"list-{id(node)}"
    ordered = local_name(node) == "orderedlist"
    numeration = (node.get("numeration") or "").lower()
    if ordered and numeration != "loweralpha" and level == 0:
        return render_numbered_list(node, asset_prefix, level=level, collapse_seed=collapse_seed)

    attrs = [f'class="mrf-list mrf-list-level-{level}"']
    if ordered and numeration == "loweralpha":
        attrs.append('type="a"')
    tag_name = "ol" if ordered else "ul"
    open_tag = f"<{tag_name} {' '.join(attrs)}>"
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
                blocks.append(f'<p class="{css_class}"><b>{html.escape(label)}</b></p>')
                first_para = False
            blocks.append(render_mediaobject(child, asset_prefix))
        elif child_name in {"itemizedlist", "orderedlist"}:
            if first_para:
                blocks.append(f'<p class="{css_class}"><b>{html.escape(label)}</b></p>')
                first_para = False
            blocks.append(render_list(child, asset_prefix, level=1, collapse_seed=label.lower().replace(" ", "-")))

    if first_para:
        blocks.append(f'<p class="{css_class}"><b>{html.escape(label)}</b></p>')

    group_slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return f'<div class="mrf-detail-group mrf-detail-group-{group_slug}">{"".join(blocks)}</div>'


def build_detail_collapse(collapse_seed: str, detail_groups: Sequence[str], toggle_context: str) -> tuple[str, str]:
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
    toggle_title = f"Show or hide {toggle_context}"
    toggle_html = (
        '\n                            <span class="float-right">\n'
        f'                                <a class="text-success more collapsed" data-toggle="collapse" href="#{collapse_id}" aria-label="{html.escape(toggle_title, quote=True)}" title="{html.escape(toggle_title, quote=True)}"></a>\n'
        "                            </span>"
    )
    return toggle_html, detail_html


def render_detail_group(node: etree._Element, asset_prefix: str) -> str:
    name = local_name(node)
    if name == "example":
        return render_group(node, asset_prefix, "text-danger", "Example:")
    if name == "note":
        role = (node.get("role") or "").lower()
        if role == "technical-comment":
            return render_group(node, asset_prefix, "text-muted", "Technical comment:")
        return render_group(node, asset_prefix, "text-primary", "Further explanation:")
    if name == "mediaobject":
        return render_mediaobject(node, asset_prefix)
    if name in {"itemizedlist", "orderedlist"}:
        return render_list(node, asset_prefix)
    if name == "informaltable":
        return render_informaltable(node, asset_prefix)
    return ""


def split_section_title(title: str) -> tuple[str, str]:
    match = re.match(r"^([A-Z]\.)\s+(.*)$", title)
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


def main_heading(title: str, subtitle: str) -> str:
    section_match = re.search(r"Section\s+(\d+)", subtitle)
    if section_match and not re.match(rf"^{section_match.group(1)}\.\s+", title):
        return f"{section_match.group(1)}. {title}"
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

    for index, child in enumerate(glossdef, start=1):
        name = local_name(child)
        if name == "para":
            main_blocks.append(render_para(child, asset_prefix))
        elif name == "informaltable":
            main_blocks.append(render_informaltable(child, asset_prefix))
        elif name in {"itemizedlist", "orderedlist"}:
            detail_groups.append(render_list(child, asset_prefix, collapse_seed=f"{glossdef_seed}-{name}-{index}"))
        elif name in {"example", "note", "mediaobject"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                detail_groups.append(rendered)

    return main_blocks, detail_groups


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
            blocks.append(render_para(child, asset_prefix))
        elif name in {"itemizedlist", "orderedlist"}:
            blocks.append(render_list(child, asset_prefix, collapse_seed=f"{node_seed}-{name}-{index}"))
        elif name in {"example", "note", "mediaobject", "informaltable"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                blocks.append(rendered)
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

    if term and number:
        return (
            "                    <div class=\"row\">\n"
            "                        <div class=\"col-sm-1\">\n"
            f"                            {html.escape(number)}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-2 col-sm-3\">\n"
            f"                            {html.escape(term)}{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-9 col-sm-8\">\n"
            f"{content}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )

    if term and not number:
        return (
            "                    <div class=\"row\">\n"
            "                        <div class=\"col-xl-2 col-sm-3\">\n"
            f"                            {html.escape(term)}{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-10 col-sm-9\">\n"
            f"{content}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )

    if not term and number:
        return (
            "                    <div class=\"row\">\n"
            "                        <div class=\"col-sm-1\">\n"
            f"                            {html.escape(number)}\n"
            "                        </div>\n"
            "                        <div class=\"col-sm-11\">\n"
            f"{indent_block('\n'.join(main_blocks), 28) if main_blocks else ''}{detail_html}\n"
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
    intro_html = "\n".join(render_block_children(glossdiv, asset_prefix))

    if len(entries) == 1 and blank_unheaded_entry(entries[0]) and show_header:
        glossdef = entries[0].find("db:glossdef", NS)
        main_blocks, detail_groups = render_glossdef(glossdef, asset_prefix) if glossdef is not None else ([], [])
        toggle_html, detail_html = build_detail_collapse(
            section_id or title or "section",
            detail_groups,
            f"details for section {marker or name or title}",
        )
        combined_content = "\n".join(part for part in [intro_html, *main_blocks] if part).strip()
        return (
            f'                    <div class="row" id="{html.escape(section_id, quote=True)}">\n'
            '                        <div class="col-sm-1">\n'
            f"                            <h5>{html.escape(marker)}{toggle_html}</h5>\n"
            "                        </div>\n"
            '                        <div class="col-sm-11">\n'
            f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
            f"{indent_block(combined_content, 28) if combined_content else ''}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )

    header_html = ""
    if show_header:
        header_html = (
            f'                    <div class="row" id="{html.escape(section_id, quote=True)}">\n'
            '                        <div class="col-sm-1">\n'
            f"                            <h5>{html.escape(marker)}</h5>\n"
            "                        </div>\n"
            '                        <div class="col-sm-11">\n'
            f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
            "                        </div>\n"
            "                    </div>\n\n"
        )

    rendered_entries = "\n\n".join(render_entry(entry, asset_prefix) for entry in entries if render_entry(entry, asset_prefix))
    body_parts = [part for part in [intro_html, rendered_entries] if part]
    return header_html + "\n\n".join(body_parts)


def render_section(section: etree._Element, asset_prefix: str) -> str:
    title = read_text(section.find("db:title", NS))
    marker, name = split_section_title(title)
    section_id = section.get("{http://www.w3.org/XML/1998/namespace}id", "")
    main_blocks: list[str] = []
    detail_groups: list[str] = []
    section_seed = context_seed(section, title or "section")
    for index, child in enumerate(section, start=1):
        child_name = local_name(child)
        if child_name == "title":
            continue
        if child_name == "para":
            main_blocks.append(render_para(child, asset_prefix))
        elif child_name in {"itemizedlist", "orderedlist"}:
            main_blocks.append(render_list(child, asset_prefix, collapse_seed=f"{section_seed}-{child_name}-{index}"))
        elif child_name in {"mediaobject", "informaltable"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                main_blocks.append(rendered)
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
    toggle_html, detail_html = build_detail_collapse(
        section_id or title,
        detail_groups,
        f"details for section {marker or name or title}",
    )
    return (
        f'                    <div class="row" id="{html.escape(section_id, quote=True)}">\n'
        '                        <div class="col-sm-1">\n'
        f"                            <h5>{html.escape(marker)}{toggle_html}</h5>\n"
        "                        </div>\n"
        '                        <div class="col-sm-11">\n'
        f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
        f"{indent_block(content_html, 28) if content_html else ''}{detail_html}\n"
        "                        </div>\n"
        "                    </div>"
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


def build_html(
    article: etree._Element,
    asset_prefix: str,
    page_href: str,
    switch_version_href: str,
    *,
    sidebar_pages: Sequence[SidebarPage] | None = None,
    version_options: Sequence[VersionOption] | None = None,
    home_href: str | None = None,
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
            title = read_text(section_node.find("db:title", NS))
            if not re.match(r"^[A-Z]\.\s+", title):
                continue
            section_id = section_node.get("{http://www.w3.org/XML/1998/namespace}id", "")
            fallback_subsections.append(SidebarSubsection(title=title, href=f"#{section_id}"))
        sidebar = render_sidebar(
            [SidebarPage(label=heading, href=page_href, active=True, subsections=tuple(fallback_subsections))]
        )
    version_switcher = render_version_switcher(version_options, switch_version_href)
    page_home_href = home_href or join_href(asset_prefix, "index.html")

    return f"""<!DOCTYPE html>
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
    html_text = build_html(
        article,
        asset_prefix=args.asset_prefix,
        page_href=args.page_href or output_path.name,
        switch_version_href=args.switch_version_href,
    )
    output_path.write_text(html_text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
