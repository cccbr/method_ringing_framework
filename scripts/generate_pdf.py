#!/usr/bin/env python3
"""Generate PDFs from TeX files using pdflatex."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path


def find_pdflatex() -> str | None:
    """Find pdflatex executable."""
    result = shutil.which("pdflatex")
    if result:
        return result
    # Try common locations on Windows
    for path in [
        r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe",
        r"C:\Program Files (x86)\MiKTeX\miktex\bin\pdflatex.exe",
    ]:
        if Path(path).exists():
            return path
    return None


def prepare_build_dir(version: str, tex_dir: Path, aux_dir: Path, templates_dir: Path) -> bool:
    """Copy TeX files and preamble to build directory."""
    print(f"  Preparing build directory...")

    # Copy master TeX file
    master_src = tex_dir / f"framework-{version}.tex"
    master_dst = aux_dir / f"framework-{version}.tex"
    if not master_src.exists():
        print(f"    Error: Master TeX not found: {master_src}")
        return False

    shutil.copy2(master_src, master_dst)

    # Copy preamble
    preamble_src = templates_dir / "docbook-preamble.tex"
    preamble_dst = aux_dir / "docbook-preamble.tex"
    if not preamble_src.exists():
        print(f"    Error: Preamble not found: {preamble_src}")
        return False

    shutil.copy2(preamble_src, preamble_dst)

    # Copy all content TeX files
    for tex_file in tex_dir.glob("*.tex"):
        if not tex_file.name.startswith("framework-"):
            shutil.copy2(tex_file, aux_dir / tex_file.name)

    # Update preamble path in master file
    master_content = master_dst.read_text(encoding="utf-8")
    master_content = re.sub(r'\\input\{[^}]*docbook-preamble\.tex\}', r'\\input{docbook-preamble.tex}', master_content)
    master_dst.write_text(master_content, encoding="utf-8")

    return True


def compile_pdf(version: str, aux_dir: Path, output_dir: Path, pdflatex_cmd: str) -> bool:
    """Compile TeX to PDF using pdflatex."""
    print(f"  Compiling PDF...")

    master_tex = f"framework-{version}.tex"

    # Run pdflatex twice (first for document, second for TOC)
    for pass_num in [1, 2]:
        print(f"    Pass {pass_num}...")
        try:
            result = subprocess.run(
                [pdflatex_cmd, "-interaction=nonstopmode", master_tex],
                cwd=aux_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            # pdflatex may return non-zero exit code due to MiKTeX update check
            # Check if PDF was created instead
            if pass_num == 2:
                pdf_file = aux_dir / f"framework-{version}.pdf"
                if not pdf_file.exists():
                    print(f"    Error: PDF not created")
                    if result.stderr:
                        print(f"    stderr: {result.stderr[:200]}")
                    return False
        except subprocess.TimeoutExpired:
            print(f"    Error: pdflatex timed out")
            return False
        except FileNotFoundError:
            print(f"    Error: pdflatex not found")
            return False

    # Move PDF to output directory
    pdf_src = aux_dir / f"framework-{version}.pdf"
    if pdf_src.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_dst = output_dir / f"framework-{version}.pdf"
        shutil.copy2(pdf_src, pdf_dst)
        size_mb = pdf_dst.stat().st_size / 1000000
        print(f"  [OK] PDF created: {pdf_dst} ({size_mb:.2f} MB)")
        return True
    else:
        print(f"    Error: PDF not found after compilation")
        return False


def build_version(version: str, tex_dir: Path, pdf_output_dir: Path, templates_dir: Path, pdflatex_cmd: str, no_cleanup: bool = False) -> bool:
    """Build PDF for a single version."""
    print(f"\nCompiling {version}...")

    version_tex_dir = tex_dir / version
    if not version_tex_dir.exists():
        print(f"  Error: TeX directory not found: {version_tex_dir}")
        return False

    # Create build directory
    aux_dir = version_tex_dir / ".build-aux"
    aux_dir.mkdir(parents=True, exist_ok=True)

    # Prepare build directory
    if not prepare_build_dir(version, version_tex_dir, aux_dir, templates_dir):
        return False

    # Compile PDF
    version_pdf_dir = pdf_output_dir / version
    if not compile_pdf(version, aux_dir, version_pdf_dir, pdflatex_cmd):
        return False

    # Cleanup
    if not no_cleanup:
        shutil.rmtree(aux_dir, ignore_errors=True)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PDFs from TeX files")
    parser.add_argument("--version", action="append", dest="versions", help="Version(s) to compile")
    parser.add_argument("--tex-dir", default="generated/tex", help="TeX files directory")
    parser.add_argument("--pdf-dir", default="generated/pdf", help="Output PDF directory")
    parser.add_argument("--templates-dir", default="templates", help="Templates directory (for preamble)")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep build artifacts")

    args = parser.parse_args()

    if not args.versions:
        args.versions = ["version1", "version2"]

    # Find pdflatex
    pdflatex_cmd = find_pdflatex()
    if not pdflatex_cmd:
        print("Error: pdflatex not found. Please install MiKTeX or TeX Live.")
        return 1

    print(f"Using pdflatex: {pdflatex_cmd}")

    tex_dir = Path(args.tex_dir)
    pdf_output_dir = Path(args.pdf_dir)
    templates_dir = Path(args.templates_dir)

    if not tex_dir.exists():
        print(f"Error: TeX directory not found: {tex_dir}")
        return 1

    if not templates_dir.exists():
        print(f"Error: Templates directory not found: {templates_dir}")
        return 1

    print("\nGenerating PDFs...")

    for version in args.versions:
        if not build_version(version, tex_dir, pdf_output_dir, templates_dir, pdflatex_cmd, args.no_cleanup):
            return 1

    print("\n" + "=" * 60)
    print("[OK] PDF Generation Complete!")
    print("=" * 60)
    for v in args.versions:
        pdf_path = pdf_output_dir / v / f"framework-{v}.pdf"
        if pdf_path.exists():
            size_mb = pdf_path.stat().st_size / 1000000
            print(f"[OK] {pdf_path} ({size_mb:.2f} MB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
