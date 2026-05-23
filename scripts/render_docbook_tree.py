#!/usr/bin/env python3
"""Render DocBook XML to HTML and LaTeX outputs."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
from convert_docbook_to_html import build_html
from convert_docbook_to_latex import build_document
from generate_master_latex import generate_master_tex, partition_content_documents

NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

REPO_ROOT = Path(__file__).resolve().parent.parent


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
        REPO_ROOT / version / fileref,
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


def render_version(version: str, source_xml_dir: Path, html_output_dir: Path, tex_output_dir: Path, html_only: bool = False) -> bool:
    """Render a single version to HTML and LaTeX."""
    print(f"\nProcessing {version}...")

    version_xml_dir = source_xml_dir / version
    if not version_xml_dir.exists():
        print(f"  Error: XML directory not found: {version_xml_dir}")
        return False

    # Create output directories
    html_dir = html_output_dir / version
    tex_dir = tex_output_dir / version
    html_dir.mkdir(parents=True, exist_ok=True)
    tex_dir.mkdir(parents=True, exist_ok=True)

    # Get all XML files
    xml_files = sorted(version_xml_dir.glob("*.xml"))
    if not xml_files:
        print(f"  No XML files found in {version_xml_dir}")
        return False

    print(f"  Found {len(xml_files)} XML files")

    # Render each XML file
    for xml_file in xml_files:
        print(f"  Rendering {xml_file.name}...")

        try:
            # Parse XML
            tree = etree.parse(str(xml_file), etree.XMLParser(remove_blank_text=False))
            article = tree.getroot()

            # HTML output
            if not html_only:
                html_output = html_dir / f"{xml_file.stem}.html"
                html_text = build_html(
                    article,
                    asset_prefix="",
                    page_href=html_output.name,
                    switch_version_href="../index.html"
                )
                html_output.write_text(html_text, encoding="utf-8", newline="\n")

            # LaTeX output
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
    parser.add_argument("--version", action="append", dest="versions", default=[], help="Specific versions to render (can specify multiple times)")
    parser.add_argument("--html-only", action="store_true", help="Only render HTML, skip LaTeX")
    parser.add_argument("--pdf-only", action="store_true", help="Skip rendering, only generate PDFs (not supported in this script)")
    parser.add_argument("--source-xml", default="generated/xml", help="Source XML directory")
    parser.add_argument("--output-html", default="generated/html", help="Output HTML directory")
    parser.add_argument("--output-tex", default="generated/tex", help="Output TeX directory")
    args = parser.parse_args()

    xml_dir = Path(args.source_xml)
    if not xml_dir.exists():
        print(f"Error: XML directory not found: {xml_dir}")
        return 1

    # If no versions specified, process all subdirectories
    if not args.versions:
        versions = sorted([d.name for d in xml_dir.iterdir() if d.is_dir() and d.name != "__pycache__"])
    else:
        versions = args.versions

    if not versions:
        print("No versions found to process")
        return 1

    print(f"Rendering {len(versions)} version(s): {', '.join(versions)}")

    for version in versions:
        if not render_version(version, xml_dir, Path(args.output_html), Path(args.output_tex), args.html_only):
            print(f"Error: Failed to render {version}")
            return 1

    print("\nAll versions rendered successfully")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
