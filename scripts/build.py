#!/usr/bin/env python3
"""
Build orchestrator: converts HTML → XML → HTML/LaTeX/PDF

Usage:
    python scripts/build.py [--edition EDITION] [--html-only] [--xml-only] [--pdf-only] [--no-cleanup]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from publishing_paths import discover_version_ids, edition_output_dir, normalize_version_id, source_site_dir


def discover_render_versions() -> list[str]:
    versions = discover_version_ids(Path("generated/xml"), Path("xml"))
    if versions:
        return versions
    return discover_version_ids(Path("."), required_file="index.html")


def run_command(cmd: list[str], description: str, cwd: Optional[Path] = None) -> bool:
    """Run a command and report status."""
    print(f"\n>>> {description}")
    try:
        result = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"[FAILED] {description} failed")
        if e.stdout:
            print(f"  stdout: {e.stdout[:500]}")
        if e.stderr:
            print(f"  stderr: {e.stderr[:500]}")
        return False
    except FileNotFoundError:
        print(f"[ERROR] Command not found: {cmd[0]}")
        return False


def build_xml(versions: list[str]) -> bool:
    """Convert HTML to XML for specified versions."""
    print("\n" + "=" * 60)
    print("PHASE 1: HTML -> XML Conversion")
    print("=" * 60)

    script = Path("scripts/convert_html_tree_to_xml.py")
    if not script.exists():
        print(f"[ERROR] Script not found: {script}")
        return False

    for version in versions:
        html_dir = Path(source_site_dir(version))
        if not html_dir.exists():
            print(f"[SKIP] No HTML source directory for {version}: {html_dir}")
            continue

        if not run_command(
            [sys.executable, str(script), str(html_dir), f"generated/xml/{edition_output_dir(version)}"],
            f"Converting {version} HTML to XML"
        ):
            return False

    print("\n[OK] HTML -> XML conversion complete")
    return True


def build_outputs(versions: list[str], html_only: bool = False, pdf_only: bool = False) -> bool:
    """Generate HTML and LaTeX outputs from XML."""
    print("\n" + "=" * 60)
    print("PHASE 2: XML -> Outputs (HTML" + ("/PDF" if not html_only else "") + ")")
    print("=" * 60)

    script = Path("scripts/render_docbook_tree.py")
    if not script.exists():
        print(f"[ERROR] Script not found: {script}")
        return False

    args = [sys.executable, str(script)]
    if html_only:
        args.append("--html-only")
    if pdf_only:
        args.append("--pdf-only")
    if versions:
        for v in versions:
            args.extend(["--edition", v])
    else:
        args.append("--edition")
        args.append("all")

    if not run_command(args, "Rendering XML to outputs"):
        return False

    print("\n[OK] XML -> Outputs complete")
    return True


def generate_pdfs(versions: list[str], no_cleanup: bool = False) -> bool:
    """Generate PDFs from TeX files."""
    print("\n" + "=" * 60)
    print("PHASE 3: TeX -> PDF Compilation")
    print("=" * 60)

    script = Path("scripts/generate_pdf.py")
    if not script.exists():
        print(f"[ERROR] Script not found: {script}")
        return False

    args = [sys.executable, str(script)]
    for v in versions:
        args.extend(["--edition", v])
    if no_cleanup:
        args.append("--no-cleanup")

    if not run_command(args, "Compiling PDFs"):
        return False

    # Display results
    print("\n" + "=" * 60)
    print("PDF Generation Complete!")
    print("=" * 60)
    for v in versions:
        for pdf_path in sorted((Path("generated/pdf") / edition_output_dir(v)).glob(f"framework-{v}*.pdf")):
            size_mb = pdf_path.stat().st_size / 1000000
            print(f"[OK] {pdf_path} ({size_mb:.2f} MB)")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build framework documentation from HTML sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/build.py                              # Full build (all editions)
  python scripts/build.py --edition edition2           # Build only edition 2
  python scripts/build.py --edition edition1 --edition edition2  # Build both editions
  python scripts/build.py --edition edition2 --xml-only  # Only convert HTML to XML
  python scripts/build.py --edition edition2 --html-only # Only generate HTML (no PDF)
  python scripts/build.py --edition edition2 --pdf-only  # Only compile PDFs
        """
    )

    parser.add_argument(
        "--edition",
        "--version",
        action="append",
        dest="editions",
        help="Edition ids to build (e.g., edition2). Legacy version2 ids are also accepted. Can be specified multiple times. Defaults to all."
    )
    parser.add_argument(
        "--xml-only",
        action="store_true",
        help="Only convert HTML to XML, skip outputs"
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Skip PDF generation (only HTML)"
    )
    parser.add_argument(
        "--pdf-only",
        action="store_true",
        help="Only compile PDFs (assumes TeX files exist)"
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep build artifacts"
    )

    args = parser.parse_args()

    # Determine versions to build
    if not args.editions:
        args.editions = discover_render_versions()
    else:
        args.editions = [normalize_version_id(v) for v in args.editions]

    # Validate versions
    args.editions = [normalize_version_id(v) for v in args.editions]
    if not args.editions:
        print("[ERROR] No editions found. Add version*/edition* source folders or XML folders with index.xml.")
        return 1

    print("\n" + "=" * 60)
    print(f"Building editions: {', '.join(edition_output_dir(v) for v in args.editions)}")
    print("=" * 60)

    # Phase 1: HTML to XML
    if not args.pdf_only and not args.html_only:
        if not build_xml(args.editions):
            return 1

    # Phase 2: XML to HTML/LaTeX
    if not args.xml_only and not args.pdf_only:
        if not build_outputs(args.editions, html_only=args.html_only):
            return 1

    # Phase 3: TeX to PDF
    if not args.xml_only and not args.html_only:
        if not generate_pdfs(args.editions, no_cleanup=args.no_cleanup):
            return 1

    if args.pdf_only:
        if not generate_pdfs(args.editions, no_cleanup=args.no_cleanup):
            return 1

    print("\n" + "=" * 60)
    print("[OK] Build Complete!")
    print("=" * 60)
    print("Output: generated/xml/edition*, generated/html/edition*, generated/pdf/edition*")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
