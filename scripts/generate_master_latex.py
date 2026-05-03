#!/usr/bin/env python3
"""Generate a master LaTeX file that includes all content files and compiles to a single PDF per version."""

from __future__ import annotations

import argparse
from pathlib import Path

from lxml import etree


NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}


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

    result: list[str] = []
    for char in text:
        result.append(replacements.get(char, char))
    return "".join(result)


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return "".join(elem.itertext()).strip()


def extract_metadata_from_xml(xml_dir: Path) -> dict:
    """Extract metadata from XML files in the directory.
    
    Look for consistent metadata across all files (e.g., status, authority).
    Use a default title that includes the version name.
    """
    metadata = {
        "title": "Framework for Method Ringing",
        "subtitle": "Complete Framework",
        "edition": "1.0",
        "status": "draft",
        "authority": "CCCBR",
        "canonical": "",
    }

    try:
        # Look at first few files to extract consistent metadata
        xml_files = list(xml_dir.glob("*.xml"))[:3]
        parser = etree.XMLParser(remove_blank_text=False)
        
        for xml_file in xml_files:
            try:
                article = etree.parse(str(xml_file), parser).getroot()
                info = article.find("db:info", NS)
                
                # Extract status and authority from article root (consistent across all files)
                status = article.get(f"{{{NS['mrf']}}}status")
                if status:
                    metadata["status"] = escape_latex(status)
                
                authority = article.get(f"{{{NS['mrf']}}}authority")
                if authority:
                    metadata["authority"] = escape_latex(authority)
                
                # Get edition from first file that has it
                if not metadata["edition"].startswith("1.0"):
                    continue
                edition = read_text(info.find("db:edition", NS) if info is not None else None)
                if edition:
                    metadata["edition"] = escape_latex(edition)
                    
            except Exception:
                continue
                
    except Exception as e:
        print(f"Warning: Could not extract metadata from {xml_dir}: {e}")

    return metadata


def generate_master_tex(
    version_name: str,
    title: str,
    subtitle: str,
    edition: str,
    status: str,
    authority: str,
    canonical: str,
    content_files: list[str],
    output_path: str,
    preamble_path: str = "../../templates/docbook-preamble.tex",
    xml_dir: str | None = None,
) -> None:
    """Generate master TeX file that includes preamble and all content.
    
    Args:
        version_name: Version identifier
        title: Document title
        subtitle: Document subtitle
        edition: Edition number
        status: Publication status
        authority: Document authority
        canonical: Canonical URI
        content_files: List of content .tex file names to include
        output_path: Path where master .tex file will be written
        preamble_path: Path to preamble template (relative or absolute)
        xml_dir: Optional directory to extract metadata from
    """
    # Extract metadata from XML if provided
    if xml_dir:
        metadata = extract_metadata_from_xml(Path(xml_dir))
        title = metadata.get("title", title)
        subtitle = metadata.get("subtitle", subtitle)
        edition = metadata.get("edition", edition)
        status = metadata.get("status", status)
        authority = metadata.get("authority", authority)
        canonical = metadata.get("canonical", canonical)
    
    includes = "\n".join(f"\\input{{{cf}}}" for cf in content_files)

    tex_content = rf"""\input{{{preamble_path}}}

\hypersetup{{
    pdftitle={{{title}}},
    pdfauthor={{{authority}}}
}}

\fancyhead[R]{{\textit{{{title}}}}}

\begin{{document}}

\begin{{center}}
\setlength{{\fboxsep}}{{10pt}}
\colorbox{{mrfHeader}}{{%
  \parbox{{0.96\linewidth}}{{%
    \color{{white}}\Large\textbf{{Framework for Method Ringing}}\\[0.35em]
    \large {title}
  }}%
}}
\end{{center}}

{{\large\textbf{{{subtitle}}}\par}}

\smallskip

\textbf{{Edition:}} {edition} \hfill \textbf{{Status:}} {status} \\
\textbf{{Authority:}} {authority} \\
\textbf{{Canonical URI:}} \url{{{canonical}}}

\medskip

\textit{{Note: SVG illustrations are rendered as placeholders unless matching PDF, PNG or JPG files are available alongside them.}}

\tableofcontents

\bigskip

{includes}

\end{{document}}
"""
    
    Path(output_path).write_text(tex_content, encoding="utf-8", newline="\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a master LaTeX file for a framework version.")
    parser.add_argument("version_name", help="Version identifier (e.g., version1, version2)")
    parser.add_argument("output", help="Path to the output master .tex file")
    parser.add_argument("--preamble", default="../../templates/docbook-preamble.tex", help="Path to preamble template")
    parser.add_argument("--content-dir", default=None, help="Directory containing content .tex files")
    parser.add_argument("--xml-dir", default=None, help="Directory containing original XML files for metadata extraction")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine content files
    if args.content_dir:
        content_dir = Path(args.content_dir)
        # Get all .tex files except the master file itself, sorted
        content_files = sorted(
            cf.name for cf in content_dir.glob("*.tex")
            if not cf.name.startswith("framework-") and cf.name != output_path.name
        )
    else:
        raise ValueError("Must provide --content-dir")

    generate_master_tex(
        version_name=args.version_name,
        title="Framework for Method Ringing",
        subtitle="Complete Framework",
        edition="1.0",
        status="draft",
        authority="CCCBR",
        canonical="",
        content_files=content_files,
        output_path=str(output_path),
        preamble_path=args.preamble,
        xml_dir=args.xml_dir,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
