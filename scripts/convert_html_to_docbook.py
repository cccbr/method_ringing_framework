#!/usr/bin/env python3
"""Convert Framework HTML pages into DocBook XML with glossary-oriented structure."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag
from lxml import etree


NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

WHITESPACE_RE = re.compile(r"\s+")
ARABIC_LIST_MARKER_RE = re.compile(r"^\s*\d+[\.\)]\s+")
LOWER_ALPHA_LIST_MARKER_RE = re.compile(r"^\s*[a-z]\)\s+")
BULLET_LIST_MARKER_RE = re.compile(r"^\s*-\s+")
NON_GLOSSTERM_LABELS = {
    "[add issue]",
    "1. introduction",
    "3. fundamentals",
    "3. fundamentals of method ringing",
    "4. classification",
    "5. method naming",
    "7. record lengths",
    "9. related roles",
    "appendix b. method name syntax",
    "appendix d. extension processes",
    "appendix e. development",
    "appendix f. framework principles",
    "appendix f. transitional arrangements",
    "appendix g. related material",
    "appendix g. version 2 development",
    "appendix i. faqs",
    "articles by john harrison",
    "articles by peter scott",
    "continuity",
    "decisions to be replaced",
    "define and explain",
    "description not prescription",
    "faq articles",
    "fifth workgroup rw article",
    "first workgroup rw article",
    "fourth workgroup rw article",
    "framework presentation to the 2018 central council meeting",
    "cover bells",
    "length and stage",
    "notice of framework implementation",
    "performance reporting",
    "q.",
    "scope",
    "second workgroup rw article",
    "simple, generic, consistent",
    "simple, generic and consistent",
    "third workgroup rw article",
    "version 1",
    "version 2",
}


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


def trim_para_whitespace(para: etree._Element) -> None:
    if para.text is not None:
        para.text = para.text.lstrip() if len(para) else para.text.strip()
    if len(para):
        last = para[-1]
        if last.tail is not None:
            last.tail = last.tail.rstrip()


def strip_leading_pattern(elem: etree._Element, pattern: re.Pattern[str]) -> bool:
    if elem.text is not None:
        updated, count = pattern.subn("", elem.text, count=1)
        if count:
            elem.text = updated.lstrip()
            return True
        if elem.text.strip():
            return False

    for child in elem:
        if strip_leading_pattern(child, pattern):
            return True
        if child.tail is not None:
            updated, count = pattern.subn("", child.tail, count=1)
            if count:
                child.tail = updated.lstrip()
                return True
            if child.tail.strip():
                return False

    return False


def split_nodes_on_breaks(tag: Tag) -> list[list[Tag | NavigableString]]:
    segments: list[list[Tag | NavigableString]] = []
    current: list[Tag | NavigableString] = []

    for child in tag.children:
        if isinstance(child, Tag) and child.name.lower() == "br":
            if current:
                segments.append(current)
                current = []
            continue
        current.append(child)

    if current:
        segments.append(current)

    return segments


def segment_text(nodes: list[Tag | NavigableString]) -> str:
    parts: list[str] = []
    for node in nodes:
        if isinstance(node, NavigableString):
            parts.append(str(node))
        elif isinstance(node, Tag):
            parts.append(node.get_text(" ", strip=False))
    return clean_text("".join(parts))


def add_nodes_as_para(
    nodes: list[Tag | NavigableString],
    parent: etree._Element,
    strip_marker: re.Pattern[str] | None = None,
    strip_prefix_labels: set[str] | None = None,
) -> bool:
    para = etree.SubElement(parent, qname("para"))
    for child in nodes:
        render_inline(child, para, strip_prefix_labels)

    if strip_marker:
        strip_leading_pattern(para, strip_marker)

    if not clean_text("".join(para.itertext())) and len(para) == 0:
        parent.remove(para)
        return False

    trim_para_whitespace(para)
    return True


def add_break_separated_list(tag: Tag, parent: etree._Element) -> bool:
    if not any(isinstance(child, Tag) and child.name.lower() == "br" for child in tag.children):
        return False

    segments = [segment for segment in split_nodes_on_breaks(tag) if segment_text(segment)]
    if len(segments) < 2:
        return False

    markers = [parse_any_list_marker(segment_text(segment)) for segment in segments]
    if not any(marker is not None for marker in markers):
        return False

    index = 0
    converted = False
    while index < len(segments):
        marker = markers[index]
        if marker is None:
            next_index = index + 1
            if next_index < len(segments) and markers[next_index] is not None:
                add_nodes_as_para(segments[index], parent)
                index += 1
                continue
            return False

        list_kind, numeration, marker_pattern = marker
        if list_kind == "bullet":
            doc_list = build_unordered_list(parent, compact=True)
        else:
            doc_list = build_ordered_list(parent, numeration, compact=True)
        while index < len(segments):
            marker = markers[index]
            if marker is None or marker[0] != list_kind or marker[1] != numeration:
                break
            list_item = etree.SubElement(doc_list, qname("listitem"))
            add_nodes_as_para(segments[index], list_item, marker_pattern)
            index += 1
            converted = True

    return converted


def looks_like_heading_row(row: Tag) -> bool:
    return row.find("h2") is not None


def looks_like_section_header_row(row: Tag) -> bool:
    cols = direct_columns(row)
    if len(cols) < 2:
        return False
    return cols[0].find("h5") is not None and cols[1].find("h5") is not None


def direct_columns(row: Tag) -> list[Tag]:
    return [child for child in row.find_all("div", recursive=False)]


def make_table_text_cell(text: str, bold: bool = False) -> Tag:
    soup = BeautifulSoup("", "lxml")
    div = soup.new_tag("div")
    if text:
        if bold:
            strong = soup.new_tag("b")
            strong.string = text
            div.append(strong)
        else:
            div.string = text
    return div


def nested_row_columns(column: Tag) -> list[Tag]:
    for child in column.find_all("div", recursive=False):
        if "row" in (child.get("class") or []):
            return direct_columns(child)
    return []


def bootstrap_table_columns(row: Tag) -> list[Tag]:
    columns = direct_columns(row)
    if not columns:
        return []

    if "flex-nowrap" in (row.get("class") or []):
        normalized = list(columns)
    elif len(columns) == 2:
        left_nested = nested_row_columns(columns[0])
        right_columns = nested_row_columns(columns[1])
        if not left_nested:
            return []
        left_columns = left_nested or [columns[0]]
        normalized = left_columns + right_columns
    elif len(columns) == 3:
        first_classes = set(columns[0].get("class") or [])
        second_classes = set(columns[1].get("class") or [])
        third_classes = set(columns[2].get("class") or [])
        first_text = clean_text(columns[0].get_text(" ", strip=True))
        if (
            not first_text
            and "col-sm-1" in first_classes
            and "col-sm-5" in second_classes
            and "col-sm-6" in third_classes
        ):
            normalized = [columns[1], columns[2]]
        else:
            return []
    else:
        return []

    first_text = clean_text(normalized[0].get_text(" ", strip=True)) if normalized else ""
    if first_text == "LH Code" and len(normalized) == 8:
        normalized = [normalized[0], make_table_text_cell("")] + normalized[1:]
    elif "flex-nowrap" in (row.get("class") or []) and normalized:
        first_is_bold = normalized[0].find(["b", "strong"]) is not None
        split_values = first_text.split()
        if len(split_values) == 2:
            normalized = [
                make_table_text_cell(split_values[0], bold=first_is_bold),
                make_table_text_cell(split_values[1], bold=first_is_bold),
                *normalized[1:],
            ]

    return normalized


def extract_heading_text(main: Tag) -> str:
    heading = main.find("h2") or main.find("h3")
    return clean_text(heading.get_text(" ", strip=True) if heading else "")


def split_framework_title(title_text: str) -> tuple[str, str]:
    title_text = clean_text(title_text)
    if " - " in title_text:
        _, page_title = title_text.split(" - ", 1)
        return "Framework for Method Ringing", clean_text(page_title)
    return "Framework for Method Ringing", title_text


def derive_title(soup: BeautifulSoup, heading_text: str, html_path: Path) -> str:
    if heading_text:
        normalized_heading = clean_text(heading_text)
        if soup.title and soup.title.string:
            _, page_title = split_framework_title(soup.title.string)
            if clean_text(page_title).lower() in {"faq", "faqs"} and normalized_heading.lower() != clean_text(page_title).lower():
                match = re.match(r"^(?:\d+\.|Appendix\s+[A-Z]\.|[A-Z]\.)\s+(.*)$", normalized_heading)
                return clean_text(match.group(1) if match else normalized_heading)
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


def infer_version_defaults(
    html_path: Path,
    version_id: str | None,
    status: str | None,
    framework_version: str | None,
    implementation_date: str | None,
    effective_date: str | None,
) -> tuple[str, str, str, str, str]:
    parts = {part.lower() for part in html_path.parts}
    inferred_version_id = version_id
    inferred_status = status
    inferred_framework_version = framework_version
    inferred_implementation_date = implementation_date
    inferred_effective_date = effective_date

    if inferred_version_id is None:
        if "version1" in parts:
            inferred_version_id = "v1"
        elif "version2" in parts:
            inferred_version_id = "v2"
        elif "version3" in parts:
            inferred_version_id = "v3"
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
            inferred_framework_version = "1"
        elif inferred_version_id == "v2":
            inferred_framework_version = "2"
        elif inferred_version_id == "v3":
            inferred_framework_version = "3"
        else:
            inferred_framework_version = "0"

    if inferred_implementation_date is None:
        if inferred_version_id == "v1":
            inferred_implementation_date = "February 24, 2019"
        elif inferred_version_id == "v2":
            inferred_implementation_date = "January 26, 2022"
        else:
            inferred_implementation_date = ""

    if inferred_effective_date is None:
        if inferred_version_id == "v1":
            inferred_effective_date = "June 1, 2019"
        elif inferred_version_id == "v2":
            inferred_effective_date = "May 1, 2022"
        else:
            inferred_effective_date = ""

    return (
        inferred_version_id,
        inferred_status,
        inferred_framework_version,
        inferred_implementation_date,
        inferred_effective_date,
    )


def parse_number(text: str) -> str | None:
    match = re.match(r"^(\d+(?:\.\d+)*)\.?\s*$", clean_text(text))
    return match.group(1) if match else None


def parse_list_marker(text: str) -> tuple[str, re.Pattern[str]] | None:
    if ARABIC_LIST_MARKER_RE.match(text):
        return "arabic", ARABIC_LIST_MARKER_RE
    if LOWER_ALPHA_LIST_MARKER_RE.match(text):
        return "loweralpha", LOWER_ALPHA_LIST_MARKER_RE
    return None


def parse_any_list_marker(text: str) -> tuple[str, str, re.Pattern[str]] | None:
    ordered = parse_list_marker(text)
    if ordered is not None:
        return ("ordered", ordered[0], ordered[1])
    if BULLET_LIST_MARKER_RE.match(text):
        return ("bullet", "bullet", BULLET_LIST_MARKER_RE)
    return None


def extract_term(column: Tag) -> str:
    clone = BeautifulSoup(str(column), "html.parser")
    for unwanted in clone.select("span.float-right"):
        unwanted.decompose()
    return clean_text(clone.get_text(" ", strip=True))


def row_term_label(number: str | None, term: str) -> str:
    term = clean_text(term)
    if number and term:
        return f"{number}. {term}"
    return term


def is_non_glossterm_label(number: str | None, term: str) -> bool:
    label = row_term_label(number, term).casefold()
    return term.casefold() in NON_GLOSSTERM_LABELS or label in NON_GLOSSTERM_LABELS


def extract_embedded_label(content_col: Tag) -> str:
    first_para = content_col.find("p", recursive=False)
    if first_para is None:
        return ""
    text = clean_text(first_para.get_text(" ", strip=True))
    if ":" not in text:
        return ""
    label = clean_text(text.split(":", 1)[0])
    label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
    return clean_text(label)


def display_row_label(section_title: str, number: str | None, label: str) -> str:
    display_number = compose_mrf_number(section_title, number) or number
    if display_number:
        return f"{display_number}. {clean_text(label)}"
    return clean_text(label)


def compose_mrf_number(section_title: str, number: str | None) -> str | None:
    if not number:
        return None
    match = re.match(r"^([A-Z])\.\s+", clean_text(section_title))
    if match:
        return f"{match.group(1)}.{number}"
    return number


def make_article(
    source_path: Path,
    base_uri: str,
    framework_title: str,
    title: str,
    subtitle: str,
    version_id: str,
    status: str,
    framework_version: str,
    implementation_date: str,
    effective_date: str,
    content_model: str,
) -> etree._Element:
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
    root.set(qname("edition-label", "mrf"), f"Edition {framework_version}")

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

    release_implementation_date = etree.SubElement(info, qname("releaseinfo"))
    release_implementation_date.set("role", "implementation-date")
    release_implementation_date.text = implementation_date

    release_effective_date = etree.SubElement(info, qname("releaseinfo"))
    release_effective_date.set("role", "effective-date")
    release_effective_date.text = effective_date

    canonical = etree.SubElement(info, qname("uri"))
    canonical.set("type", "canonical")
    canonical.text = base_uri.rstrip("/") + "/" + source_path.name

    source_meta = etree.SubElement(info, qname("othermeta"))
    source_meta.set("role", "source-path")
    source_meta.text = source_path.as_posix()

    if content_model == "glossary":
        glossary = etree.SubElement(root, qname("glossary"))
        glossary.set(qname("source-title", "mrf"), framework_title)
    return root


def get_or_create_glossary(article: etree._Element, framework_title: str) -> etree._Element:
    glossary = article.find(qname("glossary"))
    if glossary is None:
        glossary = etree.SubElement(article, qname("glossary"))
        glossary.set(qname("source-title", "mrf"), framework_title)
    return glossary


def build_section(parent: etree._Element, title_text: str | None, section_id: str | None = None) -> etree._Element:
    root = parent.getroottree().getroot() if parent.getroottree() is not None else parent
    section = etree.SubElement(parent, qname("section"))
    section.set(
        "{http://www.w3.org/XML/1998/namespace}id",
        unique_xml_id(root, section_id or title_text or "section"),
    )
    cleaned_title = clean_text(title_text)
    if cleaned_title:
        etree.SubElement(section, qname("title")).text = cleaned_title
    return section


def unique_xml_id(root: etree._Element, raw_id: str) -> str:
    base_id = slugify(raw_id)
    existing_ids = {
        elem.get("{http://www.w3.org/XML/1998/namespace}id")
        for elem in root.xpath(".//*[@xml:id]", namespaces={"xml": "http://www.w3.org/XML/1998/namespace"})
    }
    if base_id not in existing_ids:
        return base_id
    suffix = 2
    while f"{base_id}-{suffix}" in existing_ids:
        suffix += 1
    return f"{base_id}-{suffix}"


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

    if tag == "u":
        elem = etree.SubElement(parent, qname("emphasis"))
        elem.set("role", "underline")
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


def add_paragraph(
    tag: Tag,
    parent: etree._Element,
    strip_prefix_labels: set[str] | None = None,
    strip_marker: re.Pattern[str] | None = None,
) -> bool:
    if paragraph_is_image_only(tag):
        for image in tag.find_all("img", recursive=False):
            render_inline(image, parent, None)
        return True

    if add_break_separated_list(tag, parent):
        return True

    para = etree.SubElement(parent, qname("para"))
    for child in tag.children:
        render_inline(child, para, strip_prefix_labels)

    if not clean_text("".join(para.itertext())) and len(para) == 0:
        parent.remove(para)
        return False

    if strip_marker:
        strip_leading_pattern(para, strip_marker)
        if not clean_text("".join(para.itertext())) and len(para) == 0:
            parent.remove(para)
            return False

    trim_para_whitespace(para)

    return True


def add_list(tag: Tag, parent: etree._Element) -> None:
    list_tag = qname("orderedlist") if tag.name.lower() == "ol" else qname("itemizedlist")
    doc_list = etree.SubElement(parent, list_tag)
    if tag.name.lower() == "ol":
        list_type = clean_text(tag.get("type", "")).lower()
        doc_list.set("numeration", "loweralpha" if list_type == "a" else "arabic")
    for item in tag.find_all("li", recursive=False):
        list_item = etree.SubElement(doc_list, qname("listitem"))
        para = etree.SubElement(list_item, qname("para"))
        for child in item.children:
            render_inline(child, para, None)
        trim_para_whitespace(para)


def add_table_cell(column: Tag, row_elem: etree._Element) -> None:
    entry = etree.SubElement(row_elem, qname("entry"))
    segments = split_nodes_on_breaks(column)
    if not segments:
        return

    added_content = False
    for segment in segments:
        para = etree.SubElement(entry, qname("para"))
        for child in segment:
            render_inline(child, para, None)
        if not clean_text("".join(para.itertext())) and len(para) == 0:
            entry.remove(para)
            continue
        trim_para_whitespace(para)
        added_content = True

    if not added_content:
        return


def is_bootstrap_table_row(row: Tag) -> bool:
    return bool(bootstrap_table_columns(row))


def is_bootstrap_table_header_row(row: Tag) -> bool:
    nonempty_columns = [column for column in bootstrap_table_columns(row) if clean_text(column.get_text(" ", strip=True))]
    if not nonempty_columns:
        return False
    if all(column.find(["b", "strong"]) is not None for column in nonempty_columns) and all(column.find("a") is None for column in nonempty_columns):
        return True
    return "background-color" in (row.get("style") or "").lower()


def bootstrap_table_role(rows: list[Tag]) -> str | None:
    for row in rows:
        columns = bootstrap_table_columns(row)
        if not columns:
            continue
        if clean_text(columns[0].get_text(" ", strip=True)) == "LH Code":
            return "leadhead-codes"
    return None


def html_table_rows(table: Tag) -> list[Tag]:
    sections = table.find_all(["thead", "tbody"], recursive=False)
    if sections:
        rows: list[Tag] = []
        for section in sections:
            rows.extend(section.find_all("tr", recursive=False))
        return rows
    return table.find_all("tr", recursive=False)


def add_html_table(table: Tag, parent: etree._Element) -> None:
    rows = html_table_rows(table)
    if not rows:
        return

    cols = max(len(row.find_all(["th", "td"], recursive=False)) for row in rows)
    doc_table = etree.SubElement(parent, qname("informaltable"))
    tgroup = etree.SubElement(doc_table, qname("tgroup"))
    tgroup.set("cols", str(cols))

    body = etree.SubElement(tgroup, qname("tbody"))
    for row in rows:
        row_elem = etree.SubElement(body, qname("row"))
        cells = row.find_all(["th", "td"], recursive=False)
        for cell in cells:
            add_table_cell(cell, row_elem)
        for _ in range(len(cells), cols):
            add_table_cell(make_table_text_cell(""), row_elem)


def paragraph_list_marker(tag: Tag) -> tuple[str, str, re.Pattern[str]] | None:
    if tag.name.lower() != "p":
        return None
    return parse_any_list_marker(clean_text(tag.get_text(" ", strip=True)))


def add_paragraph_marker_list(children: list[Tag | NavigableString], start_index: int, parent: etree._Element) -> int:
    first_child = children[start_index]
    if not isinstance(first_child, Tag):
        return 0

    first_marker = paragraph_list_marker(first_child)
    if first_marker is None:
        return 0

    list_kind, numeration, marker_pattern = first_marker
    matched_tags: list[Tag] = []
    index = start_index
    while index < len(children):
        child = children[index]
        if isinstance(child, Comment):
            index += 1
            continue
        if isinstance(child, NavigableString):
            if clean_text(str(child)):
                break
            index += 1
            continue
        if not isinstance(child, Tag):
            break
        marker = paragraph_list_marker(child)
        if marker is None or marker[0] != list_kind or marker[1] != numeration:
            break
        matched_tags.append(child)
        index += 1

    if len(matched_tags) < 2:
        return 0

    if list_kind == "bullet":
        list_container = build_unordered_list(parent, compact=True)
    else:
        list_container = build_ordered_list(parent, numeration, compact=True)
    for tag in matched_tags:
        list_item = etree.SubElement(list_container, qname("listitem"))
        add_paragraph(tag, list_item, strip_marker=marker_pattern)
    return index - start_index


def add_child_blocks(container: Tag, parent: etree._Element, strip_prefix_labels: set[str] | None = None) -> None:
    children = list(container.children)
    child_index = 0
    first_para = True

    while child_index < len(children):
        child = children[child_index]
        if isinstance(child, Comment):
            child_index += 1
            continue
        if isinstance(child, NavigableString):
            if clean_text(str(child)):
                para = etree.SubElement(parent, qname("para"))
                append_text(para, str(child))
                trim_para_whitespace(para)
            child_index += 1
            continue

        if not isinstance(child, Tag):
            child_index += 1
            continue

        child_name = child.name.lower()
        if child_name == "div" and "collapse" in (child.get("class") or []):
            child_index += 1
            continue

        converted_paragraphs = add_paragraph_marker_list(children, child_index, parent)
        if converted_paragraphs:
            child_index += converted_paragraphs
            first_para = False
            continue

        if is_bootstrap_table_row(child):
            table_rows: list[Tag] = []
            while child_index < len(children):
                row_candidate = children[child_index]
                if isinstance(row_candidate, Comment):
                    child_index += 1
                    continue
                if isinstance(row_candidate, NavigableString):
                    if clean_text(str(row_candidate)):
                        break
                    child_index += 1
                    continue
                if not isinstance(row_candidate, Tag) or not is_bootstrap_table_row(row_candidate):
                    break
                table_rows.append(row_candidate)
                child_index += 1
            add_bootstrap_table(table_rows, parent)
            first_para = False
            continue

        if child_name == "p":
            labels = strip_prefix_labels if first_para else None
            added = add_paragraph(child, parent, labels)
            first_para = first_para and not added
        elif child_name in {"ul", "ol"}:
            add_list(child, parent)
            first_para = False
        elif child_name == "img":
            add_media_from_img(child, parent)
            first_para = False
        elif child_name == "table":
            add_html_table(child, parent)
            first_para = False
        else:
            nested_images = child.find_all("img", recursive=False)
            if nested_images:
                for image in nested_images:
                    add_media_from_img(image, parent)
                first_para = False

        child_index += 1


def add_bootstrap_table(rows: list[Tag], parent: etree._Element) -> None:
    if not rows:
        return

    normalized_rows = [bootstrap_table_columns(row) for row in rows]
    cols = max(len(columns) for columns in normalized_rows)
    table = etree.SubElement(parent, qname("informaltable"))
    role = bootstrap_table_role(rows)
    if role:
        table.set("role", role)
    tgroup = etree.SubElement(table, qname("tgroup"))
    tgroup.set("cols", str(cols))

    header_rows: list[Tag] = []
    body_rows: list[Tag] = []
    seen_body = False
    for row in rows:
        if not seen_body and is_bootstrap_table_header_row(row):
            header_rows.append(row)
        else:
            seen_body = True
            body_rows.append(row)

    if header_rows:
        thead = etree.SubElement(tgroup, qname("thead"))
        for columns in normalized_rows[: len(header_rows)]:
            row_elem = etree.SubElement(thead, qname("row"))
            for column in columns:
                add_table_cell(column, row_elem)
            for _ in range(len(columns), cols):
                add_table_cell(make_table_text_cell(""), row_elem)

    tbody = etree.SubElement(tgroup, qname("tbody"))
    for columns in normalized_rows[len(header_rows) :]:
        row_elem = etree.SubElement(tbody, qname("row"))
        for column in columns:
            add_table_cell(column, row_elem)
        for _ in range(len(columns), cols):
            add_table_cell(make_table_text_cell(""), row_elem)


def build_unordered_list(parent: etree._Element, compact: bool = False) -> etree._Element:
    itemized_list = etree.SubElement(parent, qname("itemizedlist"))
    if compact:
        itemized_list.set("role", "compact")
    return itemized_list


def add_media_from_img(tag: Tag, parent: etree._Element) -> None:
    render_inline(tag, parent, None)


def add_main_blocks(container: Tag, glossdef: etree._Element) -> None:
    add_child_blocks(container, glossdef)


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
        strip_labels = {"further explanation", "futher explanation", "technical comment", "technical comments"}
    else:
        target = parent
        strip_labels = None

    wrapper = BeautifulSoup("", "lxml").new_tag("div")
    for child in segment:
        wrapper.append(child)
    add_child_blocks(wrapper, target, strip_labels)


def add_detail_blocks(container: Tag, glossdef: etree._Element) -> None:
    collapse = container.find("div", class_="collapse", recursive=False)
    if collapse is None:
        return

    for segment in collapse_segments(collapse):
        add_segment_blocks(segment, glossdef, detect_segment_kind(segment))


def add_content_blocks(container: Tag, parent: etree._Element) -> None:
    add_main_blocks(container, parent)
    add_detail_blocks(container, parent)


def add_labeled_content(parent: etree._Element, label: str, content_col: Tag, content_id: str | None = None) -> etree._Element:
    if etree.QName(parent).localname == "glossdiv":
        para = etree.SubElement(parent, qname("para"))
        emphasis = etree.SubElement(para, qname("emphasis"))
        emphasis.set("role", "bold")
        emphasis.text = clean_text(label)
        trim_para_whitespace(para)
        add_content_blocks(content_col, parent)
        return parent

    section = build_section(parent, label, content_id or label)
    add_content_blocks(content_col, section)
    return section


def build_ordered_list(parent: etree._Element, numeration: str = "arabic", compact: bool = False) -> etree._Element:
    ordered_list = etree.SubElement(parent, qname("orderedlist"))
    ordered_list.set("numeration", numeration)
    if compact:
        ordered_list.set("role", "compact")
    return ordered_list


def add_numbered_list_item(ordered_list: etree._Element, content_col: Tag) -> etree._Element:
    list_item = etree.SubElement(ordered_list, qname("listitem"))
    add_content_blocks(content_col, list_item)
    return list_item


def build_glossentry(term: str, number: str | None, content_col: Tag, section_title: str, entry_id: str) -> etree._Element:
    entry = etree.Element(qname("glossentry"))
    entry.set("{http://www.w3.org/XML/1998/namespace}id", entry_id)
    if number:
        entry.set(qname("number", "mrf"), compose_mrf_number(section_title, number) or number)

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
    root = glossary.getroottree().getroot() if glossary.getroottree() is not None else glossary
    glossdiv.set("{http://www.w3.org/XML/1998/namespace}id", unique_xml_id(root, row_id))
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


def detect_glossary_page(rows: list[Tag]) -> bool:
    for row in rows:
        if looks_like_heading_row(row):
            continue
        if looks_like_section_header_row(row):
            continue
        columns = direct_columns(row)
        kind, number, term_col, _content_col = infer_row_kind(columns)
        term = extract_term(term_col) if term_col is not None else ""
        if kind == "term-entry" and not is_non_glossterm_label(number, term) and (number or term):
            return True
    return False


def narrative_row_label(columns: list[Tag]) -> str:
    if len(columns) >= 2:
        return clean_text(columns[0].get_text(" ", strip=True))
    return ""


def convert_narrative_rows(article: etree._Element, rows: list[Tag], page_title: str) -> None:
    current_section: etree._Element | None = None
    current_container: etree._Element | None = None
    current_numbered_list: etree._Element | None = None

    row_index = 0
    while row_index < len(rows):
        row = rows[row_index]
        display_index = row_index + 1
        if looks_like_heading_row(row):
            row_index += 1
            continue

        if looks_like_section_header_row(row):
            columns = direct_columns(row)
            marker = clean_text(columns[0].find("h5").get_text(" ", strip=True) if columns and columns[0].find("h5") else "")
            label = clean_text(columns[1].find("h5").get_text(" ", strip=True) if len(columns) > 1 and columns[1].find("h5") else "")
            section_title = f"{marker} {label}".strip()
            current_section = build_section(article, section_title, row.get("id") or f"section-{display_index}")
            current_container = current_section
            current_numbered_list = None
            content_col = columns[1] if len(columns) > 1 else None
            if content_col is not None:
                clone = BeautifulSoup(str(content_col), "lxml").find("div")
                if clone is not None:
                    for heading in clone.find_all("h5", recursive=False):
                        heading.decompose()
                    if clean_text(clone.get_text(" ", strip=True)) or clone.find(["p", "img", "ul", "ol", "div"]):
                        add_content_blocks(clone, current_section)
            row_index += 1
            continue

        if is_bootstrap_table_row(row):
            if current_section is None:
                current_section = build_section(article, None, row.get("id") or f"section-{display_index}")
                current_container = current_section
                current_numbered_list = None

            table_rows: list[Tag] = []
            while row_index < len(rows) and is_bootstrap_table_row(rows[row_index]):
                table_rows.append(rows[row_index])
                row_index += 1
            add_bootstrap_table(table_rows, current_section)
            current_container = current_section
            current_numbered_list = None
            continue

        columns = direct_columns(row)
        kind, number, _term_col, content_col = infer_row_kind(columns)
        if kind == "skip" or content_col is None:
            row_index += 1
            continue

        if current_section is None:
            current_section = build_section(article, None, row.get("id") or f"section-{display_index}")
            current_container = current_section
            current_numbered_list = None

        label = narrative_row_label(columns)
        if label and len(columns) >= 2 and clean_text(content_col.get_text(" ", strip=True)):
            if number:
                if current_numbered_list is None or current_numbered_list.getparent() is not current_section:
                    current_numbered_list = build_ordered_list(current_section)
                current_container = add_numbered_list_item(current_numbered_list, content_col)
            else:
                current_numbered_list = None
                current_container = add_labeled_content(
                    current_section,
                    label,
                    content_col,
                    row.get("id") or f"{current_section.get('{http://www.w3.org/XML/1998/namespace}id')}-row-{display_index}",
                )
            row_index += 1
            continue

        target = current_container if current_container is not None else current_section
        add_content_blocks(content_col, target)
        row_index += 1


def convert_file(input_path: Path, output_path: Path, base_uri: str, version_id: str | None, status: str | None, framework_version: str | None) -> None:
    with input_path.open("r", encoding="utf-8") as handle:
        soup = BeautifulSoup(handle, "lxml")

    version_id, status, framework_version, implementation_date, effective_date = infer_version_defaults(
        input_path,
        version_id,
        status,
        framework_version,
        None,
        None,
    )
    main = soup.find("main") or soup.body or soup
    content_root = main.find("div", class_="container-fluid", recursive=False) or main
    rows = [row for row in content_root.find_all("div", recursive=False) if "row" in (row.get("class") or [])]

    heading_text = extract_heading_text(main)
    framework_title, _ = split_framework_title(soup.title.string if soup.title and soup.title.string else "Framework for Method Ringing")
    page_title = derive_title(soup, heading_text, input_path)
    subtitle = derive_subtitle(heading_text or page_title, framework_title)

    content_model = "glossary" if detect_glossary_page(rows) else "narrative"

    article = make_article(
        input_path,
        base_uri,
        framework_title,
        page_title,
        subtitle,
        version_id,
        status,
        framework_version,
        implementation_date,
        effective_date,
        content_model,
    )
    if content_model == "narrative":
        convert_narrative_rows(article, rows, page_title)
    else:
        glossary = get_or_create_glossary(article, framework_title)
        current_div: etree._Element | None = None
        current_numbered_list: etree._Element | None = None
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
                current_numbered_list = None
                content_col = columns[1] if len(columns) > 1 else None
                if content_col is not None:
                    clone = BeautifulSoup(str(content_col), "lxml").find("div")
                    if clone is not None:
                        for heading in clone.find_all("h5", recursive=False):
                            heading.decompose()
                        if clean_text(clone.get_text(" ", strip=True)) or clone.find(["p", "img", "ul", "ol", "div"]):
                            add_content_blocks(clone, current_div)
                continue

            if current_div is None:
                current_div = build_glossdiv(glossary, row, current_section_title or page_title)

            columns = direct_columns(row)
            kind, number, term_col, content_col = infer_row_kind(columns)
            if kind == "skip" or content_col is None:
                continue

            term = extract_term(term_col) if term_col is not None else ""
            embedded_label = extract_embedded_label(content_col)
            if kind == "term-entry" and is_non_glossterm_label(number, term):
                current_numbered_list = None
                add_labeled_content(
                    current_div,
                    display_row_label(current_section_title, number, term),
                    content_col,
                    row.get("id") or row_term_label(number, term),
                )
            elif embedded_label and is_non_glossterm_label(number, embedded_label):
                current_numbered_list = None
                add_content_blocks(content_col, current_div)
            elif kind == "term-entry" and (number or term):
                current_numbered_list = None
                entry_index += 1
                entry_slug = term or f"entry-{entry_index}"
                entry_id = f"{current_div.get('{http://www.w3.org/XML/1998/namespace}id')}-entry-{entry_index}-{slugify(entry_slug)}"
                entry = build_glossentry(term, number, content_col, current_section_title, entry_id)
                current_div.append(entry)
            elif number:
                if current_numbered_list is None or current_numbered_list.getparent() is not current_div:
                    current_numbered_list = build_ordered_list(current_div)
                add_numbered_list_item(current_numbered_list, content_col)
            else:
                current_numbered_list = None
                add_content_blocks(content_col, current_div)

    etree.indent(article, space="  ")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(etree.tostring(article, xml_declaration=True, encoding="utf-8", pretty_print=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert Framework HTML pages into DocBook XML.")
    parser.add_argument("-i", "--input", required=True, help="Input HTML file or directory")
    parser.add_argument("-o", "--output", required=True, help="Output XML file or directory")
    parser.add_argument("--base-uri", required=True, help="Base URI for canonical links")
    parser.add_argument("--edition-id", "--version-id", dest="version_id", default=None, help="Edition identifier such as edition1 or edition2")
    parser.add_argument("--status", default=None, help="Publication status such as definitive or historic")
    parser.add_argument("--framework-edition", "--framework-version", dest="framework_version", default=None, help="Framework edition number such as 2")
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
