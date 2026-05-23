#!/usr/bin/env python3
"""Generate PDFs from TeX files using pdflatex."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path


def find_latex_engine() -> tuple[str, str] | tuple[None, None]:
    """Find a LaTeX engine, preferring XeLaTeX for system font support."""
    candidates = [
        ("xelatex", shutil.which("xelatex")),
        ("lualatex", shutil.which("lualatex")),
        ("pdflatex", shutil.which("pdflatex")),
        ("xelatex", r"C:\Program Files\MiKTeX\miktex\bin\x64\xelatex.exe"),
        ("xelatex", r"C:\Program Files (x86)\MiKTeX\miktex\bin\xelatex.exe"),
        ("lualatex", r"C:\Program Files\MiKTeX\miktex\bin\x64\lualatex.exe"),
        ("pdflatex", r"C:\Program Files\MiKTeX\miktex\bin\x64\pdflatex.exe"),
        ("pdflatex", r"C:\Program Files (x86)\MiKTeX\miktex\bin\pdflatex.exe"),
    ]
    for engine_name, path in candidates:
        if path and Path(path).exists():
            return engine_name, path
    return None, None


def copy_pdf_with_retry(pdf_src: Path, pdf_dst: Path) -> Path:
    """Copy a generated PDF, tolerating transient locks on Windows."""
    last_error: PermissionError | None = None
    for _ in range(20):
        try:
            shutil.copy2(pdf_src, pdf_dst)
            return pdf_dst
        except PermissionError as exc:
            last_error = exc
            time.sleep(1)

    fallback_dst = pdf_dst.with_name(f"{pdf_dst.stem}-rebuilt{pdf_dst.suffix}")
    for _ in range(20):
        try:
            shutil.copy2(pdf_src, fallback_dst)
            print(f"  Warning: {pdf_dst.name} is locked; wrote rebuilt PDF to {fallback_dst.name} instead")
            return fallback_dst
        except PermissionError as exc:
            last_error = exc
            time.sleep(1)

    raise last_error


def compile_pdf(master_tex: Path, tex_dir: Path, aux_dir: Path, output_dir: Path, latex_cmd: str, engine_name: str) -> bool:
    """Compile TeX to PDF using the selected LaTeX engine."""
    print(f"  Compiling {master_tex.name}...")

    document_name = master_tex.stem

    # Run pdflatex twice (first for document, second for TOC)
    for pass_num in [1, 2]:
        print(f"    Pass {pass_num}...")
        try:
            result = subprocess.run(
                [
                    latex_cmd,
                    "-interaction=nonstopmode",
                    f"-output-directory={aux_dir.name}",
                    master_tex.name,
                ],
                cwd=tex_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            # MiKTeX engines may return non-zero exit codes due to background checks.
            # Check if PDF was created instead
            if pass_num == 2:
                pdf_file = aux_dir / f"{document_name}.pdf"
                if not pdf_file.exists():
                    print(f"    Error: PDF not created")
                    if result.stderr:
                        print(f"    stderr: {result.stderr[:200]}")
                    return False
        except subprocess.TimeoutExpired:
            print(f"    Error: {engine_name} timed out")
            return False
        except FileNotFoundError:
            print(f"    Error: {engine_name} not found")
            return False

    # Move PDF to output directory
    pdf_src = aux_dir / f"{document_name}.pdf"
    if pdf_src.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_dst = output_dir / f"{document_name}.pdf"
        written_pdf = copy_pdf_with_retry(pdf_src, pdf_dst)
        size_mb = written_pdf.stat().st_size / 1000000
        print(f"  [OK] PDF created: {written_pdf} ({size_mb:.2f} MB)")
        return True
    else:
        print(f"    Error: PDF not found after compilation")
        return False


def build_version(version: str, tex_dir: Path, pdf_output_dir: Path, templates_dir: Path, latex_cmd: str, engine_name: str, no_cleanup: bool = False) -> bool:
    """Build PDF for a single version."""
    print(f"\nCompiling {version}...")

    version_tex_dir = tex_dir / version
    if not version_tex_dir.exists():
        print(f"  Error: TeX directory not found: {version_tex_dir}")
        return False

    # Create build directory
    aux_dir = version_tex_dir / ".build-aux"
    aux_dir.mkdir(parents=True, exist_ok=True)

    master_files = sorted(version_tex_dir.glob(f"framework-{version}-*.tex"))
    if not master_files:
        legacy_master = version_tex_dir / f"framework-{version}.tex"
        if legacy_master.exists():
            master_files = [legacy_master]
        else:
            print(f"  Error: No master TeX files found in {version_tex_dir}")
            return False

    # Compile PDF
    version_pdf_dir = pdf_output_dir / version
    if len(master_files) > 1:
        legacy_pdf = version_pdf_dir / f"framework-{version}.pdf"
        if legacy_pdf.exists():
            legacy_pdf.unlink()
    for master_file in master_files:
        if not compile_pdf(master_file, version_tex_dir, aux_dir, version_pdf_dir, latex_cmd, engine_name):
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

    # Find LaTeX engine
    engine_name, latex_cmd = find_latex_engine()
    if not latex_cmd:
        print("Error: no LaTeX engine found. Please install MiKTeX or TeX Live.")
        return 1

    print(f"Using {engine_name}: {latex_cmd}")

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
        if not build_version(version, tex_dir, pdf_output_dir, templates_dir, latex_cmd, engine_name, args.no_cleanup):
            return 1

    print("\n" + "=" * 60)
    print("[OK] PDF Generation Complete!")
    print("=" * 60)
    for v in args.versions:
        for pdf_path in sorted((pdf_output_dir / v).glob(f"framework-{v}*.pdf")):
            size_mb = pdf_path.stat().st_size / 1000000
            print(f"[OK] {pdf_path} ({size_mb:.2f} MB)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
