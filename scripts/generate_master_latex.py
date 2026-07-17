#!/usr/bin/env python3
"""Generate styled master LaTeX files for the rendered framework volumes."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from lxml import etree

from publishing_paths import is_revision_stem


NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

SECTION_RE = re.compile(r"Section\s+(\d+)")
APPENDIX_RE = re.compile(r"Appendix\s+([A-Z])")
GLOSSDIV_PREFIX_RE = re.compile(r"^((?:Appendix\s+[A-Z]|\d+|[A-Z])\.)\s+(.*)$")
SUPPLEMENTAL_APPENDIX_ORDERS = {
    "extensionprocesses2": (4, 1),
}
EXCLUDED_PDF_STEMS = {"xref", "issues", "amendedmethodtitles"}


@dataclass(frozen=True)
class TocItem:
    label_id: str
    number: str
    title: str


@dataclass(frozen=True)
class ContentDocument:
    tex_name: str
    source_stem: str
    title: str
    subtitle: str
    volume: str
    sort_key: tuple[int, int, str, str]
    page_item: TocItem
    subsections: tuple[TocItem, ...]


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


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return "".join(elem.itertext()).strip()


def format_edition(edition: str) -> str:
    edition = (edition or "").strip()
    if re.fullmatch(r"\d+(?:\.0+)?", edition):
        return edition.split(".", 1)[0]
    return edition


def extract_metadata_from_xml(xml_dir: Path) -> dict[str, str]:
    """Extract shared document metadata from a version XML directory."""
    metadata = {
        "edition": "1",
        "status": "draft",
        "authority": "CCCBR",
        "canonical": "",
        "implementation_date": "",
        "effective_date": "",
    }

    parser = etree.XMLParser(remove_blank_text=False)
    for xml_file in sorted(xml_dir.glob("*.xml"))[:5]:
        try:
            article = etree.parse(str(xml_file), parser).getroot()
            info = article.find("db:info", NS)

            status = article.get(f"{{{NS['mrf']}}}status")
            if status:
                metadata["status"] = escape_latex(status)

            authority = article.get(f"{{{NS['mrf']}}}authority")
            if authority:
                metadata["authority"] = escape_latex(authority)

            edition = read_text(info.find("db:edition", NS) if info is not None else None)
            if edition:
                metadata["edition"] = format_edition(edition)

            implementation_date = read_text(
                info.find("db:releaseinfo[@role='implementation-date']", NS) if info is not None else None
            )
            if implementation_date:
                metadata["implementation_date"] = implementation_date

            effective_date = read_text(
                info.find("db:releaseinfo[@role='effective-date']", NS) if info is not None else None
            )
            if effective_date:
                metadata["effective_date"] = effective_date
        except Exception:
            continue

    return metadata


def classify_content_document(source_stem: str, title: str, subtitle: str) -> tuple[str, tuple[int, int, str, str], str]:
    """Classify a content file into the main or appendices volume."""
    section_match = SECTION_RE.search(subtitle)
    if section_match:
        number = f"{section_match.group(1)}."
        return (
            "main",
            (int(section_match.group(1)), 0, title.casefold(), source_stem),
            number,
        )

    appendix_match = APPENDIX_RE.search(subtitle)
    if appendix_match:
        appendix_index = ord(appendix_match.group(1)) - ord("A") + 1
        number = f"Appendix {appendix_match.group(1)}."
        return (
            "appendices",
            (appendix_index, 0, title.casefold(), source_stem),
            number,
        )

    if source_stem in SUPPLEMENTAL_APPENDIX_ORDERS:
        appendix_number, supplement_rank = SUPPLEMENTAL_APPENDIX_ORDERS[source_stem]
        return (
            "appendices",
            (appendix_number, supplement_rank, title.casefold(), source_stem),
            "",
        )

    return (
        "appendices",
        (999, 0, title.casefold(), source_stem),
        "",
    )


def build_toc_subsections(article: etree._Element, source_stem: str, page_item: TocItem) -> tuple[TocItem, ...]:
    """Build subsection TOC items from glossdiv or section headings."""
    subsections: list[TocItem] = []

    glossdivs = article.findall("db:glossary/db:glossdiv", NS)
    if glossdivs:
        section_nodes = glossdivs
        label_prefix = "mrf-subsection"
    else:
        section_nodes = article.findall("db:section", NS)
        label_prefix = "mrf-section"

    for index, section_node in enumerate(section_nodes, start=1):
        title = read_text(section_node.find("db:title", NS))
        if not title:
            continue

        match = GLOSSDIV_PREFIX_RE.match(title)
        if match:
            number, label = match.group(1), match.group(2)
        else:
            number, label = "", title

        if page_item.number and title == f"{page_item.number} {page_item.title}".strip():
            continue
        if not page_item.number and title == page_item.title:
            continue

        if label_prefix == "mrf-subsection":
            label_id = f"{label_prefix}-{source_stem}-{index}"
        else:
            label_suffix = section_node.get("{http://www.w3.org/XML/1998/namespace}id", "") or f"{source_stem}-{index}".strip("-")
            label_suffix = re.sub(r"[^A-Za-z0-9:-]+", "-", label_suffix).strip("-") or "section"
            label_id = f"{label_prefix}-{label_suffix}"

        subsections.append(TocItem(label_id=label_id, number=number, title=label))

    return tuple(subsections)


def document_identity(document: ContentDocument) -> tuple[str, str, str]:
    return (document.volume, document.page_item.number, document.page_item.title.casefold())


def document_preference(document: ContentDocument) -> tuple[int, str]:
    return (1 if is_revision_stem(document.source_stem) else 0, document.source_stem)


def load_content_documents(content_dir: Path, xml_dir: Path) -> list[ContentDocument]:
    """Load ordering metadata for rendered TeX content files."""
    parser = etree.XMLParser(remove_blank_text=False)
    documents: list[ContentDocument] = []

    for tex_file in sorted(content_dir.glob("*.tex")):
        if tex_file.name.startswith("framework-"):
            continue

        xml_file = xml_dir / f"{tex_file.stem}.xml"
        if not xml_file.exists():
            volume, sort_key, page_number = classify_content_document(tex_file.stem, tex_file.stem, "")
            page_item = TocItem(
                label_id=f"mrf-page-{tex_file.stem}",
                number=page_number,
                title=tex_file.stem,
            )
            documents.append(
                ContentDocument(
                    tex_name=tex_file.name,
                    source_stem=tex_file.stem,
                    title=tex_file.stem,
                    subtitle="",
                    volume=volume,
                    sort_key=sort_key,
                    page_item=page_item,
                    subsections=(),
                )
            )
            continue

        article = etree.parse(str(xml_file), parser).getroot()
        info = article.find("db:info", NS)
        title = read_text(info.find("db:title", NS) if info is not None else None) or tex_file.stem
        subtitle = read_text(info.find("db:subtitle", NS) if info is not None else None)
        source_meta = info.find("db:othermeta[@role='source-path']", NS) if info is not None else None
        source_stem = Path(read_text(source_meta)).stem or tex_file.stem
        if source_stem in EXCLUDED_PDF_STEMS:
            continue
        volume, sort_key, page_number = classify_content_document(source_stem, title, subtitle)
        page_item = TocItem(
            label_id=f"mrf-page-{source_stem}",
            number=page_number,
            title=title,
        )
        documents.append(
            ContentDocument(
                tex_name=tex_file.name,
                source_stem=source_stem,
                title=title,
                subtitle=subtitle,
                volume=volume,
                sort_key=sort_key,
                page_item=page_item,
                subsections=build_toc_subsections(article, source_stem, page_item),
            )
        )

    deduped_documents: dict[tuple[str, str, str], ContentDocument] = {}
    for document in documents:
        identity = document_identity(document)
        existing = deduped_documents.get(identity)
        if existing is None or document_preference(document) < document_preference(existing):
            deduped_documents[identity] = document

    return list(deduped_documents.values())


def partition_content_documents(content_dir: Path, xml_dir: Path) -> dict[str, list[ContentDocument]]:
    """Split rendered TeX files into ordered main and appendices volumes."""
    volumes: dict[str, list[ContentDocument]] = {
        "main": [],
        "appendices": [],
    }

    for document in load_content_documents(content_dir, xml_dir):
        volumes[document.volume].append(document)

    return {
        volume: sorted(documents, key=lambda document: document.sort_key)
        for volume, documents in volumes.items()
    }


def build_contents_page(content_documents: list[ContentDocument]) -> str:
    """Build the custom contents page for one volume."""
    lines = [
        r"\MRFStartContents",
        r"\MRFContentsTitle{Contents}",
        r"\begin{MRFContentsTable}",
        r"\MRFContentsPageHeading",
    ]

    for document in content_documents:
        lines.append(
            rf"\MRFContentsSectionRow{{{escape_latex(document.page_item.number)}}}"
            rf"{{{escape_latex(document.page_item.title)}}}"
            rf"{{{document.page_item.label_id}}}"
        )
        for subsection in document.subsections:
            lines.append(
                rf"\MRFContentsSubsectionRow{{{escape_latex(subsection.number)}}}"
                rf"{{{escape_latex(subsection.title)}}}"
                rf"{{{subsection.label_id}}}"
            )

    lines.extend(
        [
            r"\end{MRFContentsTable}",
            r"\clearpage",
            r"\pagenumbering{arabic}",
            r"\setcounter{page}{1}",
            r"\pagestyle{mrfcontent}",
        ]
    )
    return "\n".join(lines)


def build_includes(content_documents: list[ContentDocument]) -> str:
    return "\n".join(rf"\input{{{document.tex_name}}}" for document in content_documents)


def build_cover_lines(volume_name: str) -> tuple[str, str]:
    if volume_name == "appendices":
        return ("Framework for Method Ringing --- Appendices", "Appendices")
    return ("Framework for Method Ringing", "")


def build_layout_commands(layout_mode: str, include_details: bool, volume_name: str) -> str:
    layout_command = r"\MRFSetContentLayoutTable" if layout_mode == "table" else r"\MRFSetContentLayoutNarrative"
    details_command = r"\MRFShowDetails" if include_details else r"\MRFHideDetails"
    commands = [layout_command, details_command]
    if volume_name == "appendices":
        commands.append(r"\renewcommand{\MRFHeaderText}{Central Council Framework for Method Ringing - Appendices}")
    return "\n".join(commands)


def generate_master_tex(
    version_name: str,
    volume_name: str,
    subtitle: str,
    output_path: str,
    content_documents: list[ContentDocument],
    *,
    layout_mode: str,
    include_details: bool,
    preamble_path: str = "../../../templates/docbook-preamble.tex",
    logo_path: str = "../../../images/CCCBR_WorkgroupIcon_Col_600_TT.png",
    xml_dir: str | None = None,
) -> None:
    """Generate a styled master TeX file for one framework volume."""
    metadata = extract_metadata_from_xml(Path(xml_dir)) if xml_dir else {}
    edition = metadata.get("edition", "1")
    authority = metadata.get("authority", "CCCBR")
    status = metadata.get("status", "")
    implementation_date = metadata.get("implementation_date", "")
    if not implementation_date and status == "draft":
        implementation_date = f"Draft on {date.today().strftime('%B %d, %Y')}"
    edition_text = f"Edition {edition}"
    if status == "draft":
        edition_text = f"Draft Edition {edition}"
    cover_title, cover_suffix = build_cover_lines(volume_name)
    contents = build_contents_page(content_documents)
    includes = build_includes(content_documents)
    layout_commands = build_layout_commands(layout_mode, include_details, volume_name)

    tex_content = rf"""\input{{{preamble_path}}}

\hypersetup{{
    pdftitle={{Framework for Method Ringing - {escape_latex(subtitle)}}},
    pdfauthor={{{escape_latex(authority)}}}
}}

\begin{{document}}

\MRFSetEditionText{{{escape_latex(edition_text)}}}
{layout_commands}
\MRFTitlePage{{{escape_latex(cover_title)}}}{{{escape_latex(cover_suffix)}}}{{{escape_latex(edition_text)}}}{{{escape_latex(implementation_date)}}}{{{logo_path}}}
{contents}
{includes}

\end{{document}}
"""

    Path(output_path).write_text(tex_content, encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a master LaTeX file for a framework volume.")
    parser.add_argument("version_name", help="Edition identifier (e.g., edition2; legacy version2 ids are also accepted)")
    parser.add_argument("volume_name", help="Volume name (e.g., main, main-full, appendices)")
    parser.add_argument("output", help="Path to the output master .tex file")
    parser.add_argument("--preamble", default="../../../templates/docbook-preamble.tex", help="Path to preamble template")
    parser.add_argument("--content-dir", required=True, help="Directory containing content .tex files")
    parser.add_argument("--xml-dir", required=True, help="Directory containing original XML files for metadata extraction")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    partitions = partition_content_documents(Path(args.content_dir), Path(args.xml_dir))
    if args.volume_name.startswith("main"):
        content_documents = partitions.get("main", [])
    else:
        content_documents = partitions.get("appendices", [])

    if not content_documents:
        raise ValueError(f"No content found for volume '{args.volume_name}'")

    layout_mode = "table" if args.volume_name == "main" else "narrative"
    include_details = args.volume_name != "main"
    subtitle = "Appendices" if args.volume_name == "appendices" else "Framework"

    generate_master_tex(
        version_name=args.version_name,
        volume_name=args.volume_name,
        subtitle=subtitle,
        output_path=str(output_path),
        content_documents=content_documents,
        layout_mode=layout_mode,
        include_details=include_details,
        preamble_path=args.preamble,
        xml_dir=args.xml_dir,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
