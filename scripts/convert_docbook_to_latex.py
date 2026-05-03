#!/usr/bin/env python3
"""Render a DocBook glossary article as LaTeX suitable for PDF generation."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from lxml import etree


NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

WHITESPACE_RE = re.compile(r"\s+")


def local_name(elem: etree._Element) -> str:
    return etree.QName(elem).localname


def collapse_ws(text: str | None, *, strip: bool = False) -> str:
    if text is None:
        return ""
    value = WHITESPACE_RE.sub(" ", text.replace("\xa0", " "))
    return value.strip() if strip else value


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return collapse_ws("".join(elem.itertext()), strip=True)


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


def render_mixed(node: etree._Element) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(escape_latex(collapse_ws(node.text)))

    for child in node:
        parts.append(render_inline(child))
        if child.tail:
            parts.append(escape_latex(collapse_ws(child.tail)))

    return "".join(parts).strip()


def render_inline(node: etree._Element) -> str:
    name = local_name(node)
    body = render_mixed(node)

    if name == "emphasis":
        role = (node.get("role") or "").lower()
        if role == "bold":
            return rf"\textbf{{{body}}}"
        if role == "italic":
            return rf"\textit{{{body}}}"
        return rf"\emph{{{body}}}"

    if name in {"link", "ulink"}:
        href = (
            node.get(f"{{{NS['xlink']}}}href")
            or node.get("url")
            or node.get("href")
            or "#"
        )
        return rf"\href{{{escape_latex(href)}}}{{{body or escape_latex(href)}}}"

    if name == "literal":
        return rf"\texttt{{{body}}}"

    if name == "quote":
        return f"``{body}''"

    if name == "subscript":
        return rf"\textsubscript{{{body}}}"

    if name == "superscript":
        return rf"\textsuperscript{{{body}}}"

    if name == "glossentry":
        term = node.find("db:glossterm", NS)
        return escape_latex(read_text(term))

    return body


def width_to_latex(width: str | None) -> str:
    if not width:
        return "0.75\\linewidth"

    value = width.strip().lower()
    if value.endswith("%"):
        try:
            percent = max(20.0, min(98.0, float(value[:-1])))
            return f"{percent / 100:.2f}\\linewidth"
        except ValueError:
            return "0.75\\linewidth"

    if value.endswith("px"):
        try:
            px = float(value[:-2])
            ratio = max(0.25, min(0.98, px / 420.0))
            return f"{ratio:.2f}\\linewidth"
        except ValueError:
            return "0.75\\linewidth"

    return "0.75\\linewidth"


def build_image_include(fileref: str, width: str | None, asset_root: str) -> str:
    asset_path = Path(asset_root) / Path(fileref)
    asset_tex = escape_latex(asset_path.as_posix())
    width_tex = width_to_latex(width)
    suffix = Path(fileref).suffix.lower()

    if suffix in {".pdf", ".png", ".jpg", ".jpeg"}:
        return (
            rf"\IfFileExists{{{asset_tex}}}{{\includegraphics[width={width_tex}]{{{asset_tex}}}}}"
            rf"{{\MRFImagePlaceholder{{{asset_tex}}}}}"
        )

    if suffix == ".svg":
        candidates = [".pdf", ".png", ".jpg", ".jpeg"]
        chain = rf"\MRFImagePlaceholder{{{asset_tex}}}"
        for ext in reversed(candidates):
            candidate = escape_latex(asset_path.with_suffix(ext).as_posix())
            chain = (
                rf"\IfFileExists{{{candidate}}}{{\includegraphics[width={width_tex}]{{{candidate}}}}}"
                rf"{{{chain}}}"
            )
        return chain

    return rf"\MRFImagePlaceholder{{{asset_tex}}}"


def render_mediaobject(node: etree._Element, asset_root: str) -> str:
    image = node.find(".//db:imagedata", NS)
    if image is None:
        return ""

    fileref = image.get("fileref", "")
    asset_path = Path(asset_root) / Path(fileref)
    return (
        rf"\MRFImage{{{escape_latex(asset_path.as_posix())}}}"
        rf"{{{escape_latex(asset_path.with_suffix('.pdf').as_posix())}}}"
        rf"{{{escape_latex(asset_path.with_suffix('.png').as_posix())}}}"
        rf"{{{escape_latex(asset_path.with_suffix('.jpg').as_posix())}}}"
        rf"{{{escape_latex(asset_path.with_suffix('.jpeg').as_posix())}}}"
        rf"{{{width_to_latex(image.get('width') or image.get('contentwidth'))}}}"
    )


def render_list(node: etree._Element, asset_root: str) -> str:
    env = "enumerate" if local_name(node) == "orderedlist" else "itemize"
    items: list[str] = [rf"\begin{{{env}}}"]
    for item in node.findall("db:listitem", NS):
        item_parts: list[str] = []
        for child in item:
            name = local_name(child)
            if name == "para":
                item_parts.append(render_mixed(child))
            elif name == "mediaobject":
                item_parts.append(render_mediaobject(child, asset_root))
        items.append(rf"\item {' '.join(part for part in item_parts if part).strip()}")
    items.append(rf"\end{{{env}}}")
    return "\n".join(items)


def render_labeled_block(node: etree._Element, para_macro: str, asset_root: str) -> str:
    blocks: list[str] = []

    for child in node:
        name = local_name(child)
        if name == "para":
            text = render_mixed(child)
            blocks.append(rf"\{para_macro}{{{text}}}")
        elif name == "mediaobject":
            blocks.append(render_mediaobject(child, asset_root))
        elif name in {"itemizedlist", "orderedlist"}:
            blocks.append(render_list(child, asset_root))

    return "\n".join(blocks)


def render_detail(node: etree._Element, asset_root: str) -> str:
    name = local_name(node)
    if name == "example":
        return rf"\MRFExample{{{render_labeled_block(node, 'MRFExamplePara', asset_root)}}}"
    if name == "note":
        role = (node.get("role") or "").lower()
        if role == "technical-comment":
            return rf"\MRFTechnical{{{render_labeled_block(node, 'MRFTechnicalPara', asset_root)}}}"
        return rf"\MRFFurther{{{render_labeled_block(node, 'MRFFurtherPara', asset_root)}}}"
    if name == "mediaobject":
        return render_mediaobject(node, asset_root)
    if name in {"itemizedlist", "orderedlist"}:
        return render_list(node, asset_root)
    return ""


def render_glossdef(glossdef: etree._Element, asset_root: str) -> str:
    parts: list[str] = []
    for child in glossdef:
        name = local_name(child)
        if name == "para":
            parts.append(rf"\MRFMainPara{{{render_mixed(child)}}}")
        else:
            detail = render_detail(child, asset_root)
            if detail:
                parts.append(detail)
    return "\n\n".join(parts)


def render_entry(entry: etree._Element, asset_root: str) -> str:
    number = entry.get(f"{{{NS['mrf']}}}number", "")
    display_number = number.split(".")[-1] + "." if "." in number else number
    term = escape_latex(read_text(entry.find("db:glossterm", NS)))
    glossdef = entry.find("db:glossdef", NS)
    body = render_glossdef(glossdef, asset_root) if glossdef is not None else ""

    if not term and not display_number:
        return body

    return rf"""\MRFEntry{{{escape_latex(display_number)}}}{{{term}}}{{
{body}
}}"""


def render_section(section: etree._Element, asset_root: str) -> str:
    title = escape_latex(read_text(section.find("db:title", NS)))
    entries = [
        render_entry(entry, asset_root)
        for entry in section.findall("db:glossentry", NS)
    ]
    return rf"""\MRFSection{{{title}}}

{chr(10).join(entries)}"""


def build_document(article: etree._Element, asset_root: str) -> str:
    info = article.find("db:info", NS)
    title = escape_latex(read_text(info.find("db:title", NS) if info is not None else None))
    subtitle = escape_latex(read_text(info.find("db:subtitle", NS) if info is not None else None))
    edition = escape_latex(read_text(info.find("db:edition", NS) if info is not None else None))
    canonical = escape_latex(read_text(info.find('db:uri[@type="canonical"]', NS) if info is not None else None))
    status = escape_latex(article.get(f"{{{NS['mrf']}}}status", ""))
    authority = escape_latex(article.get(f"{{{NS['mrf']}}}authority", ""))
    sections = article.findall("db:glossary/db:glossdiv", NS)

    section_body = "\n\n".join(render_section(section, asset_root) for section in sections)

    return rf"""\documentclass[11pt,a4paper]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage[T1]{{fontenc}}
\usepackage[utf8]{{inputenc}}
\usepackage{{lmodern}}
\usepackage{{parskip}}
\usepackage{{array}}
\usepackage{{tabularx}}
\usepackage{{graphicx}}
\usepackage{{xcolor}}
\usepackage{{hyperref}}
\usepackage{{fancyhdr}}
\usepackage{{textcomp}}
\usepackage{{xparse}}

\definecolor{{mrfHeader}}{{HTML}}{{132243}}
\definecolor{{mrfExample}}{{HTML}}{{C0392B}}
\definecolor{{mrfFurther}}{{HTML}}{{1F5F99}}
\definecolor{{mrfTechnical}}{{HTML}}{{6C757D}}

\hypersetup{{
    colorlinks=true,
    linkcolor=mrfHeader,
    urlcolor=mrfHeader,
    pdftitle={{{title}}},
    pdfauthor={{{authority or "CCCBR"}}}
}}

\setlength{{\parindent}}{{0pt}}
\setlength{{\parskip}}{{0.65em}}
\renewcommand{{\arraystretch}}{{1.1}}

\newcommand{{\MRFImagePlaceholder}}[1]{{%
  \fbox{{\parbox{{0.82\linewidth}}{{\centering\textit{{Illustration omitted in this build}}\\\small\texttt{{#1}}}}}}%
}}

\NewDocumentCommand{{\MRFSection}}{{m}}{{%
  \section*{{#1}}%
  \addcontentsline{{toc}}{{section}}{{#1}}%
}}

\NewDocumentCommand{{\MRFMainPara}}{{+m}}{{#1\par}}
\NewDocumentCommand{{\MRFExamplePara}}{{+m}}{{\noindent #1\par}}
\NewDocumentCommand{{\MRFFurtherPara}}{{+m}}{{\noindent #1\par}}
\NewDocumentCommand{{\MRFTechnicalPara}}{{+m}}{{\noindent #1\par}}

\NewDocumentCommand{{\MRFDetailBlock}}{{m m +m}}{{%
  \medskip
  {{\color{{#1}}\noindent\textbf{{#2}}\par
  #3}}%
}}

\NewDocumentCommand{{\MRFExample}}{{+m}}{{\MRFDetailBlock{{mrfExample}}{{Example:}}{{#1}}}}
\NewDocumentCommand{{\MRFFurther}}{{+m}}{{\MRFDetailBlock{{mrfFurther}}{{Further explanation:}}{{#1}}}}
\NewDocumentCommand{{\MRFTechnical}}{{+m}}{{\MRFDetailBlock{{mrfTechnical}}{{Technical comment:}}{{#1}}}}

\NewDocumentCommand{{\MRFImage}}{{m m m m m m}}{{%
  \begin{{center}}
  \IfFileExists{{#2}}{{\includegraphics[width=#6]{{#2}}}}{{%
    \IfFileExists{{#3}}{{\includegraphics[width=#6]{{#3}}}}{{%
      \IfFileExists{{#4}}{{\includegraphics[width=#6]{{#4}}}}{{%
        \IfFileExists{{#5}}{{\includegraphics[width=#6]{{#5}}}}{{%
          \MRFImagePlaceholder{{#1}}%
        }}%
      }}%
    }}%
  }}%
  \end{{center}}
}}

\NewDocumentCommand{{\MRFEntry}}{{m m +m}}{{%
  \begin{{tabularx}}{{\textwidth}}{{@{{}}>{{\raggedleft\arraybackslash}}p{{0.06\textwidth}} >{{\raggedright\arraybackslash}}p{{0.22\textwidth}} X@{{}}}}
  \textbf{{#1}} & \textbf{{#2}} & \begin{{minipage}}[t]{{\linewidth}}
  #3
  \end{{minipage}} \\
  \end{{tabularx}}
  \vspace{{0.9\baselineskip}}
}}

\pagestyle{{fancy}}
\fancyhf{{}}
\fancyhead[L]{{\textit{{Framework for Method Ringing}}}}
\fancyhead[R]{{\textit{{{title}}}}}
\fancyfoot[C]{{\thepage}}

\begin{{document}}

% Compile after installing LaTeX with:
%   cd version2
%   pdflatex fundamentals-sample.tex

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

{section_body}

\end{{document}}
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert DocBook glossary XML to LaTeX.")
    parser.add_argument("input", help="Input DocBook XML file")
    parser.add_argument("output", help="Output .tex file")
    parser.add_argument(
        "--asset-root",
        default=".",
        help="Path prefix from the .tex file to the HTML asset root",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    parser = etree.XMLParser(remove_blank_text=False)
    article = etree.parse(str(input_path), parser).getroot()
    latex = build_document(article, args.asset_root)
    output_path.write_text(latex, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
