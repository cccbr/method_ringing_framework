#!/usr/bin/env python3
"""
Build orchestrator: converts HTML → XML → HTML/LaTeX/PDF

Usage:
    python scripts/build.py [--version VERSION] [--html-only] [--xml-only] [--pdf-only] [--no-cleanup]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


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
        html_dir = Path(f"version{version[7:]}" if version.startswith("version") else version)
        if not html_dir.exists():
            print(f"[ERROR] HTML directory not found: {html_dir}")
            return False

        if not run_command(
            [sys.executable, str(script), str(html_dir), f"generated/xml/{version}"],
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
            args.extend(["--version", v])
    else:
        args.append("--version")
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
        args.extend(["--version", v])
    if no_cleanup:
        args.append("--no-cleanup")

    if not run_command(args, "Compiling PDFs"):
        return False

    # Display results
    print("\n" + "=" * 60)
    print("PDF Generation Complete!")
    print("=" * 60)
    for v in versions:
        pdf_path = Path(f"generated/pdf/{v}/framework-{v}.pdf")
        if pdf_path.exists():
            size_mb = pdf_path.stat().st_size / 1000000
            print(f"[OK] {pdf_path} ({size_mb:.2f} MB)")

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build framework documentation from HTML sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/build.py                              # Full build (all versions)
  python scripts/build.py --version version2           # Build only version2
  python scripts/build.py --version version1 version2  # Build both versions
  python scripts/build.py --version version2 --xml-only  # Only convert HTML to XML
  python scripts/build.py --version version2 --html-only # Only generate HTML (no PDF)
  python scripts/build.py --version version2 --pdf-only  # Only compile PDFs
        """
    )

    parser.add_argument(
        "--version",
        action="append",
        dest="versions",
        help="Version(s) to build (e.g., version1, version2). Can be specified multiple times. Defaults to all."
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
    if not args.versions:
        args.versions = ["version1", "version2"]

    # Validate versions
    for v in args.versions:
        if not v.startswith("version"):
            v = f"version{v}"

    print("\n" + "=" * 60)
    print(f"Building versions: {', '.join(args.versions)}")
    print("=" * 60)

    # Phase 1: HTML to XML
    if not args.pdf_only and not args.html_only:
        if not build_xml(args.versions):
            return 1

    # Phase 2: XML to HTML/LaTeX
    if not args.xml_only and not args.pdf_only:
        if not build_outputs(args.versions, html_only=args.html_only):
            return 1

    # Phase 3: TeX to PDF
    if not args.xml_only and not args.html_only:
        if not generate_pdfs(args.versions, no_cleanup=args.no_cleanup):
            return 1

    if args.pdf_only:
        if not generate_pdfs(args.versions, no_cleanup=args.no_cleanup):
            return 1

    print("\n" + "=" * 60)
    print("[OK] Build Complete!")
    print("=" * 60)
    print(f"Output: generated/xml/, generated/html/, generated/pdf/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
