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
    title: str,
    subtitle: str,
    edition: str,
    status: str,
    authority: str,
    canonical: str,
    content_files: list[str],
    preamble_path: str = "../../../scripts/templates/docbook-preamble.tex",
) -> str:
    """Generate master TeX file that includes preamble and all content."""

    includes = "\n".join(f"\\input{{{cf}}}" for cf in content_files)

    return rf"""\input{{{preamble_path}}}

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a master LaTeX file for a framework version.")
    parser.add_argument("version_name", help="Version identifier (e.g., version1, version2)")
    parser.add_argument("output", help="Path to the output master .tex file")
    parser.add_argument("--preamble", default="../../../scripts/templates/docbook-preamble.tex", help="Path to preamble template")
    parser.add_argument("--content-dir", default=None, help="Directory containing content .tex files")
    parser.add_argument("--xml-dir", default=None, help="Directory containing original XML files for metadata extraction")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Extract metadata from XML if available
    metadata = {
        "title": "Framework for Method Ringing",
        "subtitle": "Complete Framework",
        "edition": "1.0",
        "status": "draft",
        "authority": "CCCBR",
        "canonical": "",
    }

    if args.xml_dir:
        xml_dir = Path(args.xml_dir)
        first_xml = next(xml_dir.glob("*.xml"), None)
        if first_xml:
            metadata = extract_metadata_from_xml(first_xml)

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

    master_tex = generate_master_tex(
        title=metadata["title"],
        subtitle=metadata["subtitle"],
        edition=metadata["edition"],
        status=metadata["status"],
        authority=metadata["authority"],
        canonical=metadata["canonical"],
        content_files=content_files,
        preamble_path=args.preamble,
    )

    output_path.write_text(master_tex, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
