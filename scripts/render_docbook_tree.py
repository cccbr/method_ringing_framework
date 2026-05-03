#!/usr/bin/env python3
"""Render DocBook XML to HTML and LaTeX outputs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).parent))
from convert_docbook_to_html import build_html
from convert_docbook_to_latex import build_document
from generate_master_latex import generate_master_tex

NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}


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
            content_files = sorted(
                cf.name for cf in tex_dir.glob("*.tex")
                if not cf.name.startswith("framework-")
            )

            master_tex_path = tex_dir / f"framework-{version}.tex"
            generate_master_tex(
                version_name=version,
                title="Framework for Method Ringing",
                subtitle="Complete Framework",
                edition="1.0",
                status="draft",
                authority="CCCBR",
                canonical="",
                content_files=content_files,
                output_path=str(master_tex_path),
                preamble_path="../../templates/docbook-preamble.tex",
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
