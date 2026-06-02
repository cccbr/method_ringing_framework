#!/usr/bin/env python3
"""Render a DocBook glossary article as styled LaTeX content."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from lxml import etree


NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

WHITESPACE_RE = re.compile(r"\s+")
SECTION_RE = re.compile(r"Section\s+(\d+)")
APPENDIX_RE = re.compile(r"Appendix\s+([A-Z])")
GLOSSDIV_PREFIX_RE = re.compile(r"^((?:Appendix\s+[A-Z]|\d+|[A-Z])\.)\s+(.*)$")


def local_name(elem: etree._Element) -> str:
    return etree.QName(elem).localname


def collapse_ws(text: str | None, *, strip: bool = False) -> str:
    if text is None:
        return ""
    value = WHITESPACE_RE.sub(" ", text.replace("\xa0", " "))
    return value.strip() if strip else value


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return collapse_ws("".join(elem.itertext()), strip=True)


def escape_latex(text: str | None) -> str:
    if text is None:
        return ""

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
        "–": "--",
        "—": "---",
        "…": r"\ldots{}",
        "\u00a0": " ",
    }

    return "".join(replacements.get(char, char) for char in text)


def render_mixed(node: etree._Element) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(escape_latex(collapse_ws(node.text)))

    for child in node:
        parts.append(render_inline(child))
        if child.tail:
            parts.append(escape_latex(collapse_ws(child.tail)))

    return normalize_link_phrases("".join(parts).strip())


def normalize_link_phrases(text: str) -> str:
    text = re.sub(
        r"(?i)\bclick\s+\\href\{([^}]*)\}\{here\}",
        lambda match: rf"See \url{{{match.group(1)}}}",
        text,
    )
    text = re.sub(
        r"(?i)\\href\{([^}]*)\}\{here\}",
        lambda match: rf"See \url{{{match.group(1)}}}",
        text,
    )
    return text


def render_inline(node: etree._Element) -> str:
    name = local_name(node)
    body = render_mixed(node)

    if name == "emphasis":
        role = (node.get("role") or "").lower()
        if role == "bold":
            return rf"\textbf{{{body}}}"
        if role == "italic":
            return rf"\textit{{{body}}}"
        if role == "underline":
            return rf"\underline{{{body}}}"
        return rf"\emph{{{body}}}"

    if name in {"link", "ulink"}:
        href = (
            node.get(f"{{{NS['xlink']}}}href")
            or node.get("url")
            or node.get("href")
            or "#"
        )
        return rf"\href{{{escape_latex(href)}}}{{{body or escape_latex(href)}}}"

    if name == "literal":
        return rf"\texttt{{{body}}}"

    if name == "quote":
        return f"``{body}''"

    if name == "subscript":
        return rf"\textsubscript{{{body}}}"

    if name == "superscript":
        return rf"\textsuperscript{{{body}}}"

    if name == "glossentry":
        term = node.find("db:glossterm", NS)
        return escape_latex(read_text(term))

    return body


def width_to_latex(width: str | None) -> str:
    if not width:
        return "0.90\\linewidth"

    value = width.strip().lower()
    if value.endswith("%"):
        try:
            percent = max(20.0, min(98.0, float(value[:-1])))
            return f"{percent / 100:.2f}\\linewidth"
        except ValueError:
            return "0.90\\linewidth"

    if value.endswith("px"):
        try:
            px = float(value[:-2])
            ratio = max(0.25, min(0.98, px / 420.0))
            return f"{ratio:.2f}\\linewidth"
        except ValueError:
            return "0.90\\linewidth"

    return "0.90\\linewidth"


def build_image_include(fileref: str, width: str | None, asset_root: str) -> str:
    asset_path = Path(asset_root) / Path(fileref)
    if Path(fileref).suffix.lower() == ".svg":
        asset_path = asset_path.with_suffix(".pdf")
    return rf"\includegraphics[width={width_to_latex(width)}]{{{escape_latex(asset_path.as_posix())}}}"


def render_mediaobject(node: etree._Element, asset_root: str) -> str:
    image = node.find(".//db:imagedata", NS)
    if image is None:
        return ""

    return rf"\MRFContentImage{{{build_image_include(image.get('fileref', ''), image.get('width') or image.get('contentwidth'), asset_root)}}}"


def render_table_cell(node: etree._Element, asset_root: str, *, monospace: bool) -> str:
    parts: list[str] = []
    if node.text and collapse_ws(node.text, strip=True):
        parts.append(escape_latex(collapse_ws(node.text, strip=True)))

    for child in node:
        name = local_name(child)
        if name == "para":
            parts.append(render_mixed(child))
        elif name in {"itemizedlist", "orderedlist"}:
            parts.append(render_list(child, asset_root))
        elif name == "mediaobject":
            parts.append(render_mediaobject(child, asset_root))
        elif name == "informaltable":
            parts.append(render_informaltable(child, asset_root))
        else:
            parts.append(render_inline(child))
        if child.tail and collapse_ws(child.tail, strip=True):
            parts.append(escape_latex(collapse_ws(child.tail, strip=True)))

    body = r" \\ ".join(part for part in parts if part).strip()
    if monospace and body:
        return rf"\texttt{{{body}}}"
    return body


def render_informaltable(node: etree._Element, asset_root: str) -> str:
    role = (node.get("role") or "").strip()
    monospace = False
    font_size = r"\footnotesize" if role == "leadhead-codes" else r"\small"
    tabcolsep = "2pt" if role == "leadhead-codes" else "4pt"
    tgroup = node.find("db:tgroup", NS)
    table_root = tgroup if tgroup is not None else node
    head_rows = table_root.findall("db:thead/db:row", NS)
    body_rows = table_root.findall("db:tbody/db:row", NS)
    if not head_rows and not body_rows:
        body_rows = table_root.findall("db:row", NS)

    max_cols = 0
    for row in [*head_rows, *body_rows]:
        max_cols = max(max_cols, len(row.findall("db:entry", NS)))
    if max_cols == 0:
        return ""

    lines = [
        r"\begingroup",
        font_size,
        rf"\setlength{{\tabcolsep}}{{{tabcolsep}}}",
        rf"\begin{{longtable}}{{@{{}}{'l' * max_cols}@{{}}}}",
    ]

    def append_rows(rows: list[etree._Element], *, header: bool) -> None:
        for row in rows:
            cells = [render_table_cell(entry, asset_root, monospace=monospace) for entry in row.findall("db:entry", NS)]
            cells.extend([""] * (max_cols - len(cells)))
            if header:
                cells = [rf"\textbf{{{cell}}}" if cell else "" for cell in cells]
            lines.append(" & ".join(cells) + r" \\")
            lines.append(r"\hline")

    append_rows(head_rows, header=True)
    append_rows(body_rows, header=False)
    lines.extend([r"\end{longtable}", r"\endgroup"])
    return "\n".join(lines)


def render_list(node: etree._Element, asset_root: str, level: int = 1) -> str:
    ordered = local_name(node) == "orderedlist"
    numeration = (node.get("numeration") or "").lower()
    items: list[str] = []
    for index, item in enumerate(node.findall("db:listitem", NS), start=1):
        parts: list[str] = []
        for child in item:
            child_name = local_name(child)
            if child_name == "para":
                parts.append(render_mixed(child))
            elif child_name == "mediaobject":
                parts.append(render_mediaobject(child, asset_root))
            elif child_name in {"itemizedlist", "orderedlist"}:
                parts.append(render_list(child, asset_root, level + 1))
            elif child_name in {"example", "note"}:
                detail = render_detail(child, asset_root)
                if detail:
                    parts.append(detail)
            elif child_name == "informaltable":
                parts.append(render_informaltable(child, asset_root))
        if ordered and numeration == "loweralpha":
            label = f"{chr(ord('a') + index - 1)})"
        else:
            label = f"{index}." if ordered else r"\textbullet"
        body = "\n".join(part for part in parts if part).strip()
        if body:
            items.append(rf"\MRFListItem{{{level}}}{{{label}}}{{{body}}}")
    return "\n".join(items)


def render_detail_body(node: etree._Element, asset_root: str) -> str:
    blocks: list[str] = []
    for child in node:
        name = local_name(child)
        if name == "para":
            blocks.append(rf"\MRFDetailPara{{{render_mixed(child)}}}")
        elif name == "mediaobject":
            blocks.append(render_mediaobject(child, asset_root))
        elif name in {"itemizedlist", "orderedlist"}:
            blocks.append(render_list(child, asset_root))
    return "\n".join(blocks)


def render_detail(node: etree._Element, asset_root: str) -> str:
    name = local_name(node)
    if name == "mediaobject":
        return render_mediaobject(node, asset_root)
    if name == "informaltable":
        return render_informaltable(node, asset_root)
    if name in {"itemizedlist", "orderedlist"}:
        return render_list(node, asset_root)
    body = render_detail_body(node, asset_root)
    if not body:
        return ""

    if name == "example":
        return rf"\MRFExample{{{body}}}"
    if name == "note":
        role = (node.get("role") or "").lower()
        if role == "technical-comment":
            return rf"\MRFTechnical{{{body}}}"
        return rf"\MRFFurther{{{body}}}"
    return ""


def render_glossdef_blocks(glossdef: etree._Element | None, asset_root: str) -> list[str]:
    if glossdef is None:
        return []

    parts: list[str] = []
    for child in glossdef:
        name = local_name(child)
        if name == "para":
            parts.append(rf"\MRFBodyPara{{{render_mixed(child)}}}")
        else:
            detail = render_detail(child, asset_root)
            if detail:
                parts.append(detail)
    return parts


def render_glossdef(glossdef: etree._Element | None, asset_root: str) -> str:
    return "\n".join(render_glossdef_blocks(glossdef, asset_root))


def render_block(node: etree._Element, asset_root: str) -> str:
    name = local_name(node)
    if name == "para":
        return rf"\MRFBodyPara{{{render_mixed(node)}}}"
    if name in {"example", "note", "mediaobject", "itemizedlist", "orderedlist", "informaltable"}:
        return render_detail(node, asset_root)
    if name == "section":
        return render_narrative_section(node, asset_root, "", node.get("{http://www.w3.org/XML/1998/namespace}id", ""))
    return ""


def render_block_children(node: etree._Element, asset_root: str, *, skip_titles: bool = True, skip_entries: bool = True) -> list[str]:
    blocks: list[str] = []
    for child in node:
        name = local_name(child)
        if skip_titles and name == "title":
            continue
        if skip_entries and name == "glossentry":
            continue
        block = render_block(child, asset_root)
        if block:
            blocks.append(block)
    return [block for block in blocks if block]


def render_entry_row(entry: etree._Element, asset_root: str) -> str:
    number = entry.get(f"{{{NS['mrf']}}}number", "")
    local_number = re.sub(r"^[A-Z]\.", "", number)
    display_number = local_number if local_number.endswith(".") else local_number + "." if local_number else ""
    term = escape_latex(read_text(entry.find("db:glossterm", NS)))
    body = render_glossdef(entry.find("db:glossdef", NS), asset_root)

    if not display_number and not term and not body:
        return ""

    return rf"\MRFEntry{{{escape_latex(display_number)}}}{{{term}}}{{{body}}}"


def parse_page_heading(title: str, subtitle: str) -> tuple[str, str]:
    section_match = SECTION_RE.search(subtitle)
    if section_match:
        return f"{section_match.group(1)}.", title

    appendix_match = APPENDIX_RE.search(subtitle)
    if appendix_match:
        return f"Appendix {appendix_match.group(1)}.", title

    return "", title


def parse_glossdiv_heading(title: str) -> tuple[str, str]:
    match = GLOSSDIV_PREFIX_RE.match(title)
    if match:
        return match.group(1), match.group(2)
    return "", title


def build_document(article: etree._Element, asset_root: str) -> str:
    info = article.find("db:info", NS)
    title = read_text(info.find("db:title", NS) if info is not None else None)
    subtitle = read_text(info.find("db:subtitle", NS) if info is not None else None)
    source_meta = info.find("db:othermeta[@role='source-path']", NS) if info is not None else None
    source_stem = Path(read_text(source_meta)).stem or article.get("{http://www.w3.org/XML/1998/namespace}id", "page")
    page_number, page_title = parse_page_heading(title, subtitle)

    sections: list[str] = [
        rf"\MRFPageHeading{{{escape_latex(page_number)}}}{{{escape_latex(page_title)}}}{{mrf-page-{source_stem}}}"
    ]

    glossdivs = article.findall("db:glossary/db:glossdiv", NS)
    if glossdivs:
        for index, glossdiv in enumerate(glossdivs, start=1):
            glossdiv_title = read_text(glossdiv.find("db:title", NS))
            subsection_number, subsection_title = parse_glossdiv_heading(glossdiv_title)
            section_blocks: list[str] = []

            if glossdiv_title:
                page_heading_title = f"{page_number} {page_title}".strip()
                if glossdiv_title != page_heading_title and glossdiv_title != page_title:
                    section_blocks.append(
                        rf"\MRFSubsectionHeading{{{escape_latex(subsection_number)}}}"
                        rf"{{{escape_latex(subsection_title)}}}"
                        rf"{{mrf-subsection-{source_stem}-{index}}}"
                    )

            entry_rows: list[str] = []

            def flush_entries() -> None:
                nonlocal entry_rows
                if entry_rows:
                    section_blocks.extend(
                        [
                            r"\begin{MRFEntries}",
                            *entry_rows,
                            r"\end{MRFEntries}",
                        ]
                    )
                    entry_rows = []

            for child in glossdiv:
                name = local_name(child)
                if name == "title":
                    continue
                if name == "glossentry":
                    row = render_entry_row(child, asset_root)
                    if row:
                        entry_rows.append(row)
                    continue

                flush_entries()
                block = render_block(child, asset_root)
                if block:
                    section_blocks.append(block)

            flush_entries()

            if section_blocks:
                sections.append("\n".join(section_blocks))
    else:
        for index, section in enumerate(article.findall("db:section", NS), start=1):
            sections.append(render_narrative_section(section, asset_root, source_stem, str(index)))

    return "\n\n".join(sections)


def render_narrative_section(section: etree._Element, asset_root: str, source_stem: str, index: str) -> str:
    title = read_text(section.find("db:title", NS))
    subsection_number, subsection_title = parse_glossdiv_heading(title)
    label_suffix = section.get("{http://www.w3.org/XML/1998/namespace}id", "") or f"{source_stem}-{index}".strip("-")
    label_suffix = re.sub(r"[^A-Za-z0-9:-]+", "-", label_suffix).strip("-") or "section"
    blocks: list[str] = []
    if title:
        blocks.append(
            rf"\MRFSubsectionHeading{{{escape_latex(subsection_number)}}}"
            rf"{{{escape_latex(subsection_title)}}}"
            rf"{{mrf-section-{label_suffix}}}"
        )
    blocks.extend(render_block_children(section, asset_root, skip_titles=True, skip_entries=False))
    return "\n".join(blocks)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert DocBook glossary XML to LaTeX.")
    parser.add_argument("input", help="Input DocBook XML file")
    parser.add_argument("output", help="Output .tex file")
    parser.add_argument(
        "--asset-root",
        default=".",
        help="Path prefix from the .tex file to the HTML asset root",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    parser = etree.XMLParser(remove_blank_text=False)
    article = etree.parse(str(input_path), parser).getroot()
    latex = build_document(article, args.asset_root)
    output_path.write_text(latex, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
