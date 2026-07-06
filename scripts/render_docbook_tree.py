#!/usr/bin/env python3
"""Render DocBook XML to HTML and LaTeX outputs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
import re
import shutil
import subprocess
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
from convert_docbook_to_html import (
    CrossReferenceLink,
    GlossaryTermLink,
    SchemaVersionContext,
    SidebarPage,
    SidebarSubsection,
    VersionOption,
    build_html,
    build_site_cross_reference_links,
)
from convert_docbook_to_latex import build_document
from generate_master_latex import classify_content_document, generate_master_tex, partition_content_documents
from publishing_paths import discover_version_ids, edition_output_dir, is_revision_stem, normalize_version_id, source_site_dir

NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

REPO_ROOT = Path(__file__).resolve().parent.parent
METADATA_XML_ROOT = REPO_ROOT / "xml"


@dataclass(frozen=True)
class VersionMetadata:
    version_id: str
    version_name: str
    status: str
    edition_label: str
    approval_date: str | None = None
    superseded_date: str | None = None
    state: str | None = None


def find_inkscape() -> str | None:
    """Find an Inkscape executable for high-quality SVG conversion."""
    candidates = [
        shutil.which("inkscape"),
        r"C:\Program Files\Inkscape\bin\inkscape.exe",
        r"C:\Program Files\Inkscape\inkscape.exe",
        r"C:\Program Files (x86)\Inkscape\inkscape.exe",
        str(Path.home() / "AppData/Local/Programs/Inkscape/bin/inkscape.exe"),
        str(Path.home() / "AppData/Local/Programs/Inkscape/inkscape.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def find_headless_browser() -> str | None:
    """Find a Chromium-based browser that can print SVGs to PDF."""
    candidates = [
        shutil.which("msedge"),
        shutil.which("chrome"),
        shutil.which("chromium"),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def resolve_asset_path(fileref: str, version: str, version_xml_dir: Path) -> Path | None:
    """Resolve a DocBook image reference to a real repository file."""
    candidates = [
        REPO_ROOT / source_site_dir(version) / fileref,
        version_xml_dir / fileref,
        REPO_ROOT / fileref,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def copy_if_stale(source: Path, destination: Path) -> None:
    """Copy an asset when the destination is missing or older."""
    if destination.exists() and destination.stat().st_mtime >= source.stat().st_mtime:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def render_svg_to_pdf_with_inkscape(source: Path, destination: Path, inkscape: str) -> None:
    """Render an SVG source file to PDF using Inkscape."""
    if destination.exists() and destination.stat().st_mtime >= source.stat().st_mtime:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        inkscape,
        str(source.resolve()),
        "--export-filename",
        str(destination.resolve()),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode != 0 or not destination.exists():
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Failed to render SVG {source} to PDF with Inkscape: {detail}")


def render_svg_to_pdf_with_browser(source: Path, destination: Path, browser: str) -> None:
    """Render an SVG source file to PDF via a headless browser."""
    if destination.exists() and destination.stat().st_mtime >= source.stat().st_mtime:
        return

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        browser,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={destination.resolve()}",
        source.resolve().as_uri(),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    if result.returncode != 0 or not destination.exists():
        detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
        raise RuntimeError(f"Failed to render SVG {source} to PDF with browser: {detail}")


def stage_latex_assets(version: str, article: etree._Element, version_xml_dir: Path, tex_dir: Path) -> None:
    """Materialize image assets alongside the generated TeX files."""
    inkscape: str | None = None
    browser: str | None = None

    for image in article.findall(".//db:imagedata", NS):
        fileref = image.get("fileref", "").strip()
        if not fileref:
            continue

        source = resolve_asset_path(fileref, version, version_xml_dir)
        if source is None:
            raise FileNotFoundError(f"Image asset not found for fileref '{fileref}'")

        source_suffix = source.suffix.lower()
        if source_suffix == ".svg":
            destination = tex_dir / Path(fileref).with_suffix(".pdf")
            sibling_pdf = source.with_suffix(".pdf")
            if sibling_pdf.exists():
                copy_if_stale(sibling_pdf, destination)
                continue

            if inkscape is None:
                inkscape = find_inkscape()
            if inkscape is not None:
                render_svg_to_pdf_with_inkscape(source, destination, inkscape)
                continue

            if browser is None:
                browser = find_headless_browser()
            if browser is None:
                raise RuntimeError(
                    "No SVG to PDF converter found. Install Inkscape, Microsoft Edge, or Google Chrome."
                )
            render_svg_to_pdf_with_browser(source, destination, browser)
            continue

        destination = tex_dir / Path(fileref)
        copy_if_stale(source, destination)


def read_version_metadata(version_id: str, version_xml_dir: Path) -> VersionMetadata:
    index_xml = version_xml_dir / "index.xml"
    if not index_xml.exists():
        return VersionMetadata(
            version_id=version_id,
            version_name=version_id,
            status="draft",
            edition_label=version_id,
            state="draft",
        )

    article = etree.parse(str(index_xml), etree.XMLParser(remove_blank_text=False)).getroot()
    version_name = article.get(f"{{{NS['mrf']}}}framework-version", version_xml_dir.name)
    status = article.get(f"{{{NS['mrf']}}}status", "draft")
    edition_label = article.get(f"{{{NS['mrf']}}}edition-label", "")
    approval_date = article.get(f"{{{NS['mrf']}}}approval-date")
    superseded_date = article.get(f"{{{NS['mrf']}}}superseded-date")
    state = article.get(f"{{{NS['mrf']}}}edition-state") or article.get(f"{{{NS['mrf']}}}version-state")

    info = article.find("db:info", NS)
    if info is not None:
        for release in info.findall("db:releaseinfo", NS):
            role = (release.get("role") or "").strip()
            value = (release.text or "").strip()
            if role in {"implementation-date", "approval-date"} and value and not approval_date:
                approval_date = value
            elif role == "superseded-date" and value and not superseded_date:
                superseded_date = value

    if not edition_label:
        if re.fullmatch(r"\d+(?:\.0+)?", version_name):
            edition_label = f"Edition {version_name.split('.', 1)[0]}"
        else:
            edition_label = version_name

    return VersionMetadata(
        version_id=version_id,
        version_name=version_name,
        status=status,
        edition_label=edition_label,
        approval_date=approval_date,
        superseded_date=superseded_date,
        state=state,
    )


def version_key(version_name: str) -> tuple[int, ...]:
    digits = re.findall(r"\d+", version_name)
    if not digits:
        return (0,)
    return tuple(int(part) for part in digits)


def parse_display_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def format_display_date(value: str | None) -> str | None:
    parsed = parse_display_date(value)
    if parsed is None:
        return value
    return parsed.strftime("%d %b %Y")


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return " ".join("".join(elem.itertext()).replace("\xa0", " ").split()).strip()


def resolve_version_dir(version_id: str, source_xml_dir: Path, metadata_xml_dir: Path) -> Path | None:
    for candidate_name in (edition_output_dir(version_id), normalize_version_id(version_id), source_site_dir(version_id)):
        generated_dir = source_xml_dir / candidate_name
        if generated_dir.exists():
            return generated_dir
        metadata_dir = metadata_xml_dir / candidate_name
        if metadata_dir.exists():
            return metadata_dir
    return None


def load_version_metadata(source_xml_dir: Path, metadata_xml_dir: Path) -> dict[str, VersionMetadata]:
    version_ids = set(discover_version_ids(source_xml_dir, metadata_xml_dir))

    metadata_by_id: dict[str, VersionMetadata] = {}
    for version_id in sorted(version_ids):
        version_dir = resolve_version_dir(version_id, source_xml_dir, metadata_xml_dir)
        if version_dir is None:
            continue
        metadata_by_id[version_id] = read_version_metadata(version_id, version_dir)
    return metadata_by_id


def approved_successor_map(metadata_by_id: dict[str, VersionMetadata]) -> dict[str, VersionMetadata]:
    approved = sorted(
        (meta for meta in metadata_by_id.values() if meta.status != "draft"),
        key=lambda meta: version_key(meta.version_name),
    )
    return {
        approved[index].version_id: approved[index + 1]
        for index in range(len(approved) - 1)
    }


def resolve_asset_version(version_id: str, source_xml_dir: Path, metadata_xml_dir: Path) -> str:
    source_dir = source_site_dir(version_id)
    if (REPO_ROOT / source_dir).exists():
        return source_dir

    version_ids = set(discover_version_ids(source_xml_dir, metadata_xml_dir, required_file=None))

    approved_versions: list[VersionMetadata] = []
    for candidate in version_ids:
        if not (REPO_ROOT / source_site_dir(candidate)).exists():
            continue
        candidate_dir = resolve_version_dir(candidate, source_xml_dir, metadata_xml_dir)
        if candidate_dir is None:
            continue
        metadata = read_version_metadata(candidate, candidate_dir)
        if metadata.status != "draft":
            approved_versions.append(metadata)

    if approved_versions:
        return max(approved_versions, key=lambda meta: version_key(meta.version_name)).version_id
    return version_id


def build_version_options(current_version: str, source_xml_dir: Path, metadata_xml_dir: Path) -> list[VersionOption]:
    metadata_by_id = load_version_metadata(source_xml_dir, metadata_xml_dir)

    approved_versions = [meta for meta in metadata_by_id.values() if meta.status != "draft"]
    latest_approved = max(approved_versions, key=lambda meta: version_key(meta.version_name)).version_id if approved_versions else None
    latest_approved_date = (
        parse_display_date(metadata_by_id[latest_approved].approval_date) if latest_approved and metadata_by_id.get(latest_approved) else None
    )

    for version_id, meta in list(metadata_by_id.items()):
        if meta.status == "draft" or version_id == latest_approved or meta.superseded_date or latest_approved_date is None:
            continue
        metadata_by_id[version_id] = VersionMetadata(
            version_id=meta.version_id,
            version_name=meta.version_name,
            status=meta.status,
            edition_label=meta.edition_label,
            approval_date=meta.approval_date,
            superseded_date=(latest_approved_date - timedelta(days=1)).strftime("%Y-%m-%d"),
            state=meta.state,
        )

    def metadata_order(meta: VersionMetadata) -> tuple[int, tuple[int, ...]]:
        state = meta.state
        if not state:
            if meta.status == "draft":
                state = "draft"
            elif meta.version_id == latest_approved:
                state = "latest-approved"
            else:
                state = "superseded"
        rank = {"latest-approved": 0, "superseded": 1, "draft": 2}.get(state, 9)
        return (rank, tuple(-value for value in version_key(meta.version_name)))

    options: list[VersionOption] = []
    for meta in sorted(metadata_by_id.values(), key=metadata_order):
        state = meta.state
        if not state:
            if meta.status == "draft":
                state = "draft"
            elif meta.version_id == latest_approved:
                state = "latest-approved"
            else:
                state = "superseded"

        if state == "draft":
            label = f"Draft - {meta.edition_label} (unapproved)"
        elif state == "latest-approved":
            approved = format_display_date(meta.approval_date)
            label = f"Latest Approved - {meta.edition_label}" + (f" (approved {approved})" if approved else "")
        else:
            approved = format_display_date(meta.approval_date)
            superseded = format_display_date(meta.superseded_date)
            if approved and superseded:
                dates = f" ({approved} - {superseded})"
            elif approved:
                dates = f" ({approved})"
            else:
                dates = ""
            label = f"Superseded - {meta.edition_label}{dates}"

        href = "index.html" if meta.version_id == current_version else f"../{edition_output_dir(meta.version_id)}/index.html"
        options.append(VersionOption(label=label, button_label=label, href=href, active=meta.version_id == current_version))

    return options


def build_schema_version_context(
    current_version: str,
    metadata_by_id: dict[str, VersionMetadata],
) -> SchemaVersionContext | None:
    current_meta = metadata_by_id.get(current_version)
    if current_meta is None:
        return None

    successor = approved_successor_map(metadata_by_id).get(current_version)
    return SchemaVersionContext(
        edition_label=current_meta.edition_label,
        status=current_meta.status,
        version_url=f"https://cccbr.org.uk/{edition_output_dir(current_version)}/index.html",
        approval_date=current_meta.approval_date,
        superseded_by_label=successor.edition_label if successor is not None else None,
        superseded_by_url=(
            f"https://cccbr.org.uk/{edition_output_dir(successor.version_id)}/index.html"
            if successor is not None
            else None
        ),
    )


def sidebar_page_label(page_number: str, title: str) -> str:
    appendix_match = re.fullmatch(r"Appendix ([A-Z])\.", page_number)
    if appendix_match:
        return f"{appendix_match.group(1)}. {title}"
    if page_number:
        return f"{page_number} {title}"
    return title


def extract_sidebar_subsections(article: etree._Element) -> tuple[SidebarSubsection, ...]:
    section_nodes = article.findall("db:glossary/db:glossdiv", NS)
    if not section_nodes:
        section_nodes = article.findall("db:section", NS)

    subsections: list[SidebarSubsection] = []
    for section_node in section_nodes:
        title = (section_node.findtext("db:title", default="", namespaces=NS) or "").strip()
        if not re.match(r"^[A-Z]\.\s+", title):
            continue
        section_id = section_node.get("{http://www.w3.org/XML/1998/namespace}id", "").strip()
        if not section_id:
            continue
        subsections.append(SidebarSubsection(title=title, href=f"#{section_id}"))
    return tuple(subsections)


def sidebar_identity(page_number: str, title: str) -> tuple[str, str]:
    return (page_number, title.casefold())


def sidebar_preference(source_stem: str, current_stem: str) -> tuple[int, int, str]:
    return (
        0 if source_stem == current_stem else 1,
        1 if is_revision_stem(source_stem) else 0,
        source_stem,
    )


def build_sidebar_pages(version_xml_dir: Path, current_stem: str) -> list[SidebarPage]:
    parser = etree.XMLParser(remove_blank_text=False)
    page_entries: list[tuple[int, tuple[int, int, str, str], str, str, str, SidebarPage]] = []

    for xml_file in sorted(version_xml_dir.glob("*.xml")):
        article = etree.parse(str(xml_file), parser).getroot()
        info = article.find("db:info", NS)
        title = (info.findtext("db:title", default="", namespaces=NS) or "").strip() if info is not None else ""
        subtitle = (info.findtext("db:subtitle", default="", namespaces=NS) or "").strip() if info is not None else ""
        volume, sort_key, page_number = classify_content_document(xml_file.stem, title, subtitle)
        if not page_number:
            continue

        page_entries.append(
            (
                0 if volume == "main" else 1,
                sort_key,
                xml_file.stem,
                page_number,
                title,
                SidebarPage(
                    label=sidebar_page_label(page_number, title),
                    href=f"{xml_file.stem}.html",
                    active=xml_file.stem == current_stem,
                    subsections=extract_sidebar_subsections(article) if xml_file.stem == current_stem else (),
                ),
            )
        )

    deduped_entries: dict[tuple[int, tuple[str, str]], tuple[int, tuple[int, int, str, str], str, SidebarPage]] = {}
    for volume_order, sort_key, source_stem, page_number, title, page in page_entries:
        identity = (volume_order, sidebar_identity(page_number, title))
        existing = deduped_entries.get(identity)
        candidate = (volume_order, sort_key, source_stem, page)
        if existing is None or sidebar_preference(source_stem, current_stem) < sidebar_preference(existing[2], current_stem):
            deduped_entries[identity] = candidate

    sorted_pages = [page for _, _, _, page in sorted(deduped_entries.values(), key=lambda entry: (entry[0], entry[1]))]
    appendix_header_inserted = False
    sidebar_pages: list[SidebarPage] = []
    for page in sorted_pages:
        if not appendix_header_inserted and page.label.startswith(tuple(f"{letter}." for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")):
            sidebar_pages.append(
                SidebarPage(
                    label=page.label,
                    href=page.href,
                    active=page.active,
                    appendices_header=True,
                    subsections=page.subsections,
                )
            )
            appendix_header_inserted = True
            continue
        sidebar_pages.append(page)

    return sidebar_pages


def collect_glossary_terms(
    xml_files: list[Path],
    articles_by_file: dict[Path, etree._Element],
) -> list[GlossaryTermLink]:
    terms_by_text: dict[str, GlossaryTermLink] = {}
    for xml_file in xml_files:
        article = articles_by_file[xml_file]
        page_href = f"{xml_file.stem}.html"
        for entry in article.findall(".//db:glossentry", NS):
            glossterms = entry.findall("db:glossterm", NS)
            if not glossterms:
                continue
            primary = read_text(glossterms[0])
            entry_id = entry.get("{http://www.w3.org/XML/1998/namespace}id", "").strip()
            if not primary or not entry_id:
                continue
            alternatives = tuple(
                read_text(t) for t in glossterms[1:]
                if read_text(t) and read_text(t).casefold() != primary.casefold()
            )
            terms_by_text.setdefault(
                primary.casefold(),
                GlossaryTermLink(term=primary, page_href=page_href, anchor_id=entry_id, alt_terms=alternatives),
            )
    return sorted(
        terms_by_text.values(),
        key=lambda item: (-len(item.term), item.term.casefold()),
    )


def render_version(
    version: str,
    source_xml_dir: Path,
    metadata_xml_dir: Path,
    html_output_dir: Path,
    tex_output_dir: Path,
    html_asset_prefix_template: str,
    html_only: bool = False,
) -> bool:
    """Render a single version to HTML and LaTeX."""
    print(f"\nProcessing {version}...")

    version_xml_dir = resolve_version_dir(version, source_xml_dir, metadata_xml_dir)
    if version_xml_dir is None or not version_xml_dir.exists():
        print(f"  Error: XML directory not found: {version_xml_dir}")
        return False

    # Create output directories
    html_dir = html_output_dir / edition_output_dir(version)
    tex_dir = tex_output_dir / edition_output_dir(version)
    html_dir.mkdir(parents=True, exist_ok=True)
    tex_dir.mkdir(parents=True, exist_ok=True)
    asset_version = resolve_asset_version(version, source_xml_dir, metadata_xml_dir)
    html_asset_prefix = html_asset_prefix_template.format(
        asset_version=asset_version,
        version=version,
        edition=edition_output_dir(version),
    )
    version_options = build_version_options(version, source_xml_dir, metadata_xml_dir)
    metadata_by_id = load_version_metadata(source_xml_dir, metadata_xml_dir)
    sidebar_pages_by_stem = {
        xml_file.stem: build_sidebar_pages(version_xml_dir, xml_file.stem)
        for xml_file in sorted(version_xml_dir.glob("*.xml"))
    }

    # Get all XML files
    xml_files = sorted(version_xml_dir.glob("*.xml"))
    if not xml_files:
        print(f"  No XML files found in {version_xml_dir}")
        return False

    parser = etree.XMLParser(remove_blank_text=False)
    articles_by_file = {
        xml_file: etree.parse(str(xml_file), parser).getroot()
        for xml_file in xml_files
    }
    glossary_terms = collect_glossary_terms(xml_files, articles_by_file)
    cross_reference_links = build_site_cross_reference_links(version_xml_dir)

    print(f"  Found {len(xml_files)} XML files")

    # Render each XML file
    for xml_file in xml_files:
        print(f"  Rendering {xml_file.name}...")

        try:
            article = articles_by_file[xml_file]

            # HTML output
            html_output = html_dir / f"{xml_file.stem}.html"
            html_text = build_html(
                article,
                asset_prefix=html_asset_prefix,
                page_href=html_output.name,
                switch_version_href="../index.html",
                sidebar_pages=sidebar_pages_by_stem.get(xml_file.stem),
                version_options=version_options,
                home_href="index.html",
                schema_version=build_schema_version_context(version, metadata_by_id),
                glossary_terms=glossary_terms,
                cross_reference_links=cross_reference_links,
            )
            html_output.write_text(html_text, encoding="utf-8", newline="\n")

            # LaTeX output (skip when html_only so PDF build owns this step)
            if not html_only:
                tex_output = tex_dir / f"{xml_file.stem}.tex"
                stage_latex_assets(version, article, version_xml_dir, tex_dir)
                latex_text = build_document(article, asset_root="")
                tex_output.write_text(latex_text, encoding="utf-8", newline="\n")

        except Exception as e:
            print(f"    Error rendering {xml_file.name}: {e}")
            import traceback
            traceback.print_exc()
            return False

    # Generate master TeX file
    if not html_only:
        try:
            volume_content = partition_content_documents(tex_dir, version_xml_dir)
            legacy_master = tex_dir / f"framework-{version}.tex"
            if legacy_master.exists():
                legacy_master.unlink()

            for volume_name, subtitle, layout_mode, include_details in (
                ("main", "Framework", "table", False),
                ("main-full", "Framework", "narrative", True),
                ("appendices", "Appendices", "narrative", True),
            ):
                target_volume = "main" if volume_name.startswith("main") else "appendices"
                content_documents = volume_content.get(target_volume, [])
                if not content_documents:
                    continue

                master_tex_path = tex_dir / f"framework-{version}-{volume_name}.tex"
                generate_master_tex(
                    version_name=version,
                    volume_name=volume_name,
                    subtitle=subtitle,
                    content_documents=content_documents,
                    output_path=str(master_tex_path),
                    layout_mode=layout_mode,
                    include_details=include_details,
                    preamble_path="../../../templates/docbook-preamble.tex",
                    xml_dir=str(version_xml_dir),
                )
                print(f"  Generated master TeX file: {master_tex_path.name}")
        except Exception as e:
            print(f"  Error generating master TeX file: {e}")
            import traceback
            traceback.print_exc()
            return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Render DocBook XML to HTML and LaTeX")
    parser.add_argument(
        "--edition",
        "--version",
        action="append",
        dest="editions",
        default=[],
        help="Specific editions to render (e.g., edition2). Legacy version2 ids are also accepted.",
    )
    parser.add_argument("--html-only", action="store_true", help="Only render HTML, skip LaTeX")
    parser.add_argument("--pdf-only", action="store_true", help="Skip rendering, only generate PDFs (not supported in this script)")
    parser.add_argument("--source-xml", default="generated/xml", help="Source XML directory")
    parser.add_argument("--metadata-xml", default="xml", help="Committed XML stubs/metadata directory")
    parser.add_argument("--output-html", default="generated/html", help="Output HTML directory")
    parser.add_argument("--output-tex", default="generated/tex", help="Output TeX directory")
    parser.add_argument(
        "--html-asset-prefix-template",
        default="../../../{asset_version}",
        help="Format string for HTML asset paths; available fields: asset_version, version, edition",
    )
    args = parser.parse_args()

    xml_dir = Path(args.source_xml)
    metadata_xml_dir = Path(args.metadata_xml)
    if not xml_dir.exists():
        print(f"Error: XML directory not found: {xml_dir}")
        return 1

    # If no versions specified, process all subdirectories
    if not args.editions:
        versions = discover_version_ids(xml_dir, metadata_xml_dir)
    else:
        versions = [normalize_version_id(version) for version in args.editions]

    if not versions:
        print("No editions found to process")
        return 1

    print(f"Rendering {len(versions)} edition(s): {', '.join(edition_output_dir(version) for version in versions)}")

    for version in versions:
        if not render_version(
            version,
            xml_dir,
            metadata_xml_dir,
            Path(args.output_html),
            Path(args.output_tex),
            args.html_asset_prefix_template,
            args.html_only,
        ):
            print(f"Error: Failed to render {version}")
            return 1

    print("\nAll editions rendered successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
