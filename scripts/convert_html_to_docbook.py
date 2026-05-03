#!/usr/bin/env python3
"""Convert Framework HTML pages into DocBook XML with glossary-oriented structure."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from lxml import etree


NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

WHITESPACE_RE = re.compile(r"\s+")


def qname(local: str, prefix: str = "db") -> str:
    return f"{{{NS[prefix]}}}{local}"


def clean_text(text: str | None) -> str:
    if text is None:
        return ""
    return WHITESPACE_RE.sub(" ", text.replace("\xa0", " ")).strip()


def inline_text(text: str | None) -> str:
    if text is None:
        return ""

    raw = text.replace("\xa0", " ")
    collapsed = WHITESPACE_RE.sub(" ", raw)
    if not collapsed.strip():
        return " "

    leading = " " if collapsed[:1].isspace() else ""
    trailing = " " if collapsed[-1:].isspace() else ""
    return leading + collapsed.strip() + trailing


def merge_inline_text(existing: str | None, addition: str) -> str:
    if not existing:
        return addition
    if existing.endswith(" ") and addition.startswith(" "):
        return existing + addition[1:]
    return existing + addition


def slugify(text: str, fallback: str = "item") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", clean_text(text).lower()).strip("-")
    slug = slug or fallback
    if not re.match(r"^[a-z_]", slug):
        slug = f"{fallback}-{slug}"
    return slug


def append_text(elem: etree._Element, text: str | None) -> None:
    value = inline_text(text)
    if not value:
        return

    children = list(elem)
    if not children:
        elem.text = merge_inline_text(elem.text, value)
        return

    last = children[-1]
    last.tail = merge_inline_text(last.tail, value)


def looks_like_heading_row(row: Tag) -> bool:
    return row.find("h2") is not None


def looks_like_section_header_row(row: Tag) -> bool:
    cols = direct_columns(row)
    if len(cols) < 2:
        return False
    return cols[0].find("h5") is not None and cols[1].find("h5") is not None


def direct_columns(row: Tag) -> list[Tag]:
    return [child for child in row.find_all("div", recursive=False)]


def extract_heading_text(main: Tag) -> str:
    heading = main.find("h2")
    return clean_text(heading.get_text(" ", strip=True) if heading else "")


def split_framework_title(title_text: str) -> tuple[str, str]:
    title_text = clean_text(title_text)
    if " - " in title_text:
        _, page_title = title_text.split(" - ", 1)
        return "Framework for Method Ringing", clean_text(page_title)
    return "Framework for Method Ringing", title_text


def derive_title(soup: BeautifulSoup, heading_text: str, html_path: Path) -> str:
    if soup.title and soup.title.string:
        _, page_title = split_framework_title(soup.title.string)
        if page_title:
            return page_title
    if heading_text:
        match = re.match(r"^(?:\d+\.|Appendix\s+[A-Z]\.|[A-Z]\.)\s+(.*)$", heading_text)
        return clean_text(match.group(1) if match else heading_text)
    return html_path.stem.replace("-", " ").title()


def derive_subtitle(heading_text: str, framework_title: str) -> str:
    heading_text = clean_text(heading_text)
    section_match = re.match(r"^(\d+)\.\s+", heading_text)
    if section_match:
        return f"{framework_title}, Section {section_match.group(1)}"

    appendix_match = re.match(r"^Appendix\s+([A-Z])\.\s+", heading_text)
    if appendix_match:
        return f"{framework_title}, Appendix {appendix_match.group(1)}"

    return framework_title


def infer_version_defaults(html_path: Path, version_id: str | None, status: str | None, framework_version: str | None) -> tuple[str, str, str]:
    parts = {part.lower() for part in html_path.parts}
    inferred_version_id = version_id
    inferred_status = status
    inferred_framework_version = framework_version

    if inferred_version_id is None:
        if "version1" in parts:
            inferred_version_id = "v1"
        elif "version2" in parts:
            inferred_version_id = "v2"
        else:
            inferred_version_id = "v0"

    if inferred_status is None:
        if inferred_version_id == "v1":
            inferred_status = "historic"
        elif inferred_version_id == "v2":
            inferred_status = "definitive"
        else:
            inferred_status = "draft"

    if inferred_framework_version is None:
        if inferred_version_id == "v1":
            inferred_framework_version = "1.0"
        elif inferred_version_id == "v2":
            inferred_framework_version = "2.0"
        else:
            inferred_framework_version = "0.0"

    return inferred_version_id, inferred_status, inferred_framework_version


def parse_number(text: str) -> str | None:
    match = re.match(r"^(\d+)\.\s*$", clean_text(text))
    return match.group(1) if match else None


def extract_term(column: Tag) -> str:
    clone = BeautifulSoup(str(column), "html.parser")
    for unwanted in clone.select("span.float-right"):
        unwanted.decompose()
    return clean_text(clone.get_text(" ", strip=True))


def compose_mrf_number(section_title: str, number: str | None) -> str | None:
    if not number:
        return None
    match = re.match(r"^([A-Z])\.\s+", clean_text(section_title))
    if match:
        return f"{match.group(1)}.{number}"
    return number


def make_article(source_path: Path, base_uri: str, framework_title: str, title: str, subtitle: str, version_id: str, status: str, framework_version: str) -> etree._Element:
    root = etree.Element(
        qname("article"),
        nsmap={None: NS["db"], "xlink": NS["xlink"], "mrf": NS["mrf"]},
    )
    root.set("version", "5.0")
    root.set("{http://www.w3.org/XML/1998/namespace}id", f"{slugify(source_path.stem)}-{version_id}")
    root.set("{http://www.w3.org/XML/1998/namespace}lang", "en")
    root.set(qname("status", "mrf"), status)
    root.set(qname("authority", "mrf"), "CCCBR")
    root.set(qname("framework-version", "mrf"), framework_version)

    info = etree.SubElement(root, qname("info"))
    etree.SubElement(info, qname("title")).text = title
    etree.SubElement(info, qname("subtitle")).text = subtitle
    etree.SubElement(info, qname("edition")).text = framework_version

    release_status = etree.SubElement(info, qname("releaseinfo"))
    release_status.set("role", "status")
    release_status.text = status

    release_authority = etree.SubElement(info, qname("releaseinfo"))
    release_authority.set("role", "authority")
    release_authority.text = "CCCBR"

    canonical = etree.SubElement(info, qname("uri"))
    canonical.set("type", "canonical")
    canonical.text = base_uri.rstrip("/") + "/" + source_path.name

    source_meta = etree.SubElement(info, qname("othermeta"))
    source_meta.set("role", "source-path")
    source_meta.text = source_path.as_posix()

    glossary = etree.SubElement(root, qname("glossary"))
    glossary.set(qname("source-title", "mrf"), framework_title)
    return root


def render_inline(node: Tag | NavigableString, parent: etree._Element, strip_prefix_labels: set[str] | None = None) -> None:
    if isinstance(node, NavigableString):
        append_text(parent, str(node))
        return

    if not isinstance(node, Tag):
        return

    tag = node.name.lower()

    if strip_prefix_labels and tag in {"b", "strong"}:
        if clean_text(node.get_text(" ", strip=True)).rstrip(":").lower() in strip_prefix_labels:
            return

    if tag == "br":
        append_text(parent, " ")
        return

    if tag in {"b", "strong"}:
        elem = etree.SubElement(parent, qname("emphasis"))
        elem.set("role", "bold")
        for child in node.children:
            render_inline(child, elem, None)
        return

    if tag in {"i", "em"}:
        elem = etree.SubElement(parent, qname("emphasis"))
        elem.set("role", "italic")
        for child in node.children:
            render_inline(child, elem, None)
        return

    if tag in {"code", "tt"}:
        elem = etree.SubElement(parent, qname("literal"))
        append_text(elem, node.get_text(" ", strip=True))
        return

    if tag == "a":
        elem = etree.SubElement(parent, qname("link"))
        href = node.get("href", "")
        if href:
            elem.set(qname("href", "xlink"), href)
        for child in node.children:
            render_inline(child, elem, None)
        return

    if tag == "img":
        media = etree.SubElement(parent, qname("mediaobject"))
        image_object = etree.SubElement(media, qname("imageobject"))
        image_data = etree.SubElement(image_object, qname("imagedata"))
        if node.get("src"):
            image_data.set("fileref", node["src"])
        if node.get("width"):
            image_data.set("width", node["width"])
        if node.get("height"):
            image_data.set("height", node["height"])
        return

    for child in node.children:
        render_inline(child, parent, None)


def paragraph_is_image_only(p_tag: Tag) -> bool:
    children = [child for child in p_tag.children if clean_text(str(child)) or isinstance(child, Tag)]
    return bool(children) and all(isinstance(child, Tag) and child.name.lower() == "img" for child in children)


def add_paragraph(tag: Tag, parent: etree._Element, strip_prefix_labels: set[str] | None = None) -> bool:
    if paragraph_is_image_only(tag):
        for image in tag.find_all("img", recursive=False):
            render_inline(image, parent, None)
        return True

    para = etree.SubElement(parent, qname("para"))
    for child in tag.children:
        render_inline(child, para, strip_prefix_labels)

    if not clean_text("".join(para.itertext())) and len(para) == 0:
        parent.remove(para)
        return False

    return True


def add_list(tag: Tag, parent: etree._Element) -> None:
    list_tag = qname("orderedlist") if tag.name.lower() == "ol" else qname("itemizedlist")
    doc_list = etree.SubElement(parent, list_tag)
    for item in tag.find_all("li", recursive=False):
        list_item = etree.SubElement(doc_list, qname("listitem"))
        para = etree.SubElement(list_item, qname("para"))
        for child in item.children:
            render_inline(child, para, None)


def add_media_from_img(tag: Tag, parent: etree._Element) -> None:
    render_inline(tag, parent, None)


def add_main_blocks(container: Tag, glossdef: etree._Element) -> None:
    for child in container.children:
        if isinstance(child, NavigableString):
            if clean_text(str(child)):
                para = etree.SubElement(glossdef, qname("para"))
                append_text(para, str(child))
            continue

        if not isinstance(child, Tag):
            continue

        if child.name.lower() == "div" and "collapse" in (child.get("class") or []):
            continue

        if child.name.lower() == "p":
            add_paragraph(child, glossdef)
        elif child.name.lower() in {"ul", "ol"}:
            add_list(child, glossdef)
        elif child.name.lower() == "img":
            add_media_from_img(child, glossdef)


def collapse_segments(collapse: Tag) -> list[list[Tag]]:
    segments: list[list[Tag]] = []
    current: list[Tag] = []
    for child in collapse.children:
        if isinstance(child, NavigableString):
            continue
        if not isinstance(child, Tag):
            continue
        if child.name.lower() == "hr":
            if current:
                segments.append(current)
                current = []
            continue
        current.append(child)
    if current:
        segments.append(current)
    return segments


def detect_segment_kind(segment: list[Tag]) -> str | None:
    for child in segment:
        classes = set(child.get("class") or [])
        if "text-danger" in classes:
            return "example"
        if "text-primary" in classes:
            return "further-explanation"
        if "text-muted" in classes:
            return "technical-comment"
    return None


def add_segment_blocks(segment: list[Tag], parent: etree._Element, kind: str | None) -> None:
    if kind == "example":
        target = etree.SubElement(parent, qname("example"))
        strip_labels = {"example"}
    elif kind:
        target = etree.SubElement(parent, qname("note"))
        target.set("role", kind)
        strip_labels = {"further explanation", "technical comment", "technical comments"}
    else:
        target = parent
        strip_labels = None

    first_para = True
    for child in segment:
        child_name = child.name.lower()
        if child_name == "p":
            labels = strip_labels if first_para else None
            added = add_paragraph(child, target, labels)
            first_para = first_para and not added
        elif child_name in {"ul", "ol"}:
            add_list(child, target)
        elif child_name == "img":
            add_media_from_img(child, target)
        else:
            nested_images = child.find_all("img", recursive=False)
            if nested_images:
                for image in nested_images:
                    add_media_from_img(image, target)


def add_detail_blocks(container: Tag, glossdef: etree._Element) -> None:
    collapse = container.find("div", class_="collapse", recursive=False)
    if collapse is None:
        return

    for segment in collapse_segments(collapse):
        add_segment_blocks(segment, glossdef, detect_segment_kind(segment))


def build_glossentry(term: str, number: str | None, content_col: Tag, section_title: str, status: str, entry_id: str) -> etree._Element:
    entry = etree.Element(qname("glossentry"))
    entry.set("{http://www.w3.org/XML/1998/namespace}id", entry_id)
    if number:
        entry.set(qname("number", "mrf"), compose_mrf_number(section_title, number) or number)
    entry.set(qname("status", "mrf"), status)

    glossterm = etree.SubElement(entry, qname("glossterm"))
    glossterm.text = term

    glossdef = etree.SubElement(entry, qname("glossdef"))
    add_main_blocks(content_col, glossdef)
    add_detail_blocks(content_col, glossdef)
    return entry


def build_glossdiv(glossary: etree._Element, row: Tag, title_text: str | None = None) -> etree._Element:
    row_id = row.get("id") or slugify(title_text or "section")
    section_title = title_text
    if not section_title:
        cols = direct_columns(row)
        marker = clean_text(cols[0].find("h5").get_text(" ", strip=True) if cols and cols[0].find("h5") else "")
        label_node = cols[1].find("h5")
        label = clean_text(label_node.get_text(" ", strip=True) if label_node else row_id.replace("-", " ").title())
        section_title = f"{marker} {label}".strip()

    glossdiv = etree.SubElement(glossary, qname("glossdiv"))
    glossdiv.set("{http://www.w3.org/XML/1998/namespace}id", slugify(row_id))
    etree.SubElement(glossdiv, qname("title")).text = clean_text(section_title)
    return glossdiv


def infer_row_kind(columns: list[Tag]) -> tuple[str, str | None, Tag | None, Tag | None]:
    if not columns:
        return "skip", None, None, None

    number = parse_number(columns[0].get_text(" ", strip=True))

    if number and len(columns) >= 3:
        return "term-entry", number, columns[1], columns[2]
    if number and len(columns) == 2:
        return "full-width-entry", number, None, columns[1]
    if not number and len(columns) >= 2:
        term_classes = " ".join(columns[0].get("class") or [])
        if "col-xl-2" in term_classes or "col-sm-3" in term_classes or "col-md-2" in term_classes:
            return "term-entry", None, columns[0], columns[1]
    if len(columns) == 1:
        return "full-width-entry", None, None, columns[0]
    return "full-width-entry", None, None, columns[-1]


def convert_file(input_path: Path, output_path: Path, base_uri: str, version_id: str | None, status: str | None, framework_version: str | None) -> None:
    with input_path.open("r", encoding="utf-8") as handle:
        soup = BeautifulSoup(handle, "lxml")

    version_id, status, framework_version = infer_version_defaults(input_path, version_id, status, framework_version)
    main = soup.find("main") or soup.body or soup
    content_root = main.find("div", class_="container-fluid", recursive=False) or main
    rows = [row for row in content_root.find_all("div", recursive=False) if "row" in (row.get("class") or [])]

    heading_text = extract_heading_text(main)
    framework_title, _ = split_framework_title(soup.title.string if soup.title and soup.title.string else "Framework for Method Ringing")
    page_title = derive_title(soup, heading_text, input_path)
    subtitle = derive_subtitle(heading_text or page_title, framework_title)

    article = make_article(input_path, base_uri, framework_title, page_title, subtitle, version_id, status, framework_version)
    glossary = article.find(qname("glossary"))
    assert glossary is not None

    current_div: etree._Element | None = None
    current_section_title = clean_text(heading_text or page_title)

    entry_index = 0

    for row in rows:
        if looks_like_heading_row(row):
            continue

        if looks_like_section_header_row(row):
            columns = direct_columns(row)
            marker = clean_text(columns[0].find("h5").get_text(" ", strip=True) if columns and columns[0].find("h5") else "")
            label = clean_text(columns[1].find("h5").get_text(" ", strip=True) if len(columns) > 1 and columns[1].find("h5") else "")
            current_section_title = f"{marker} {label}".strip()
            current_div = build_glossdiv(glossary, row, current_section_title)
            content_col = columns[1] if len(columns) > 1 else None
            if content_col is not None:
                clone = BeautifulSoup(str(content_col), "lxml").find("div")
                if clone is not None:
                    for heading in clone.find_all("h5", recursive=False):
                        heading.decompose()
                    if clean_text(clone.get_text(" ", strip=True)) or clone.find(["p", "img", "ul", "ol", "div"]):
                        entry_index += 1
                        entry_id = f"{current_div.get('{http://www.w3.org/XML/1998/namespace}id')}-entry-{entry_index}"
                        current_div.append(build_glossentry("", None, clone, current_section_title, status, entry_id))
            continue

        if current_div is None:
            current_div = build_glossdiv(glossary, row, current_section_title or page_title)

        columns = direct_columns(row)
        kind, number, term_col, content_col = infer_row_kind(columns)
        if kind == "skip" or content_col is None:
            continue

        term = extract_term(term_col) if term_col is not None else ""
        entry_index += 1
        entry_slug = term or f"entry-{entry_index}"
        entry_id = f"{current_div.get('{http://www.w3.org/XML/1998/namespace}id')}-entry-{entry_index}-{slugify(entry_slug)}"
        entry = build_glossentry(term, number, content_col, current_section_title, status, entry_id)
        current_div.append(entry)

    etree.indent(article, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(etree.tostring(article, xml_declaration=True, encoding="utf-8", pretty_print=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Framework HTML pages into DocBook XML.")
    parser.add_argument("-i", "--input", required=True, help="Input HTML file or directory")
    parser.add_argument("-o", "--output", required=True, help="Output XML file or directory")
    parser.add_argument("--base-uri", required=True, help="Base URI for canonical links")
    parser.add_argument("--version-id", default=None, help="Version identifier such as v1 or v2")
    parser.add_argument("--status", default=None, help="Publication status such as definitive or historic")
    parser.add_argument("--framework-version", default=None, help="Framework version label such as 2.0")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if input_path.is_dir():
        output_path.mkdir(parents=True, exist_ok=True)
        for html_file in sorted(input_path.glob("*.html")):
            if ".generated." in html_file.name:
                continue
            convert_file(
                html_file,
                output_path / f"{html_file.stem}.xml",
                args.base_uri,
                args.version_id,
                args.status,
                args.framework_version,
            )
        return 0

    convert_file(
        input_path,
        output_path,
        args.base_uri,
        args.version_id,
        args.status,
        args.framework_version,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
