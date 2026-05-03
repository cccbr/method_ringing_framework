#!/usr/bin/env python3
"""Render DocBook XML back to HTML styled like the original site."""

from __future__ import annotations

import argparse
import html
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


def join_href(prefix: str, path: str) -> str:
    if not prefix:
        return path
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def qualify_href(href: str, asset_prefix: str) -> str:
    if not href or href.startswith(("http://", "https://", "mailto:", "#", "../", "./", "/")):
        return href
    return join_href(asset_prefix, href)


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return collapse_ws("".join(elem.itertext()), strip=True)


def render_mixed(node: etree._Element, asset_prefix: str) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(html.escape(collapse_ws(node.text)))

    for child in node:
        parts.append(render_inline(child, asset_prefix))
        if child.tail:
            parts.append(html.escape(collapse_ws(child.tail)))

    return "".join(parts).strip()


def render_inline(node: etree._Element, asset_prefix: str) -> str:
    name = local_name(node)
    body = render_mixed(node, asset_prefix)

    if name == "emphasis":
        role = (node.get("role") or "").lower()
        if role == "bold":
            return f"<b>{body}</b>"
        if role == "italic":
            return f"<i>{body}</i>"
        return f"<span>{body}</span>"

    if name in {"link", "ulink"}:
        href = (
            node.get(f"{{{NS['xlink']}}}href")
            or node.get("url")
            or node.get("href")
            or "#"
        )
        href = qualify_href(href, asset_prefix)
        return f'<a class="text-success undrln" href="{html.escape(href, quote=True)}">{body or html.escape(href)}</a>'

    if name == "literal":
        return f"<code>{body}</code>"

    if name == "quote":
        return f"'{body}'"

    if name == "subscript":
        return f"<sub>{body}</sub>"

    if name == "superscript":
        return f"<sup>{body}</sup>"

    if name == "glossentry":
        return html.escape(read_text(node.find("db:glossterm", NS)))

    return body


def render_para(node: etree._Element, asset_prefix: str, css_class: str | None = None, prefix: str | None = None) -> str:
    body = render_mixed(node, asset_prefix)
    if prefix:
        body = f"<b>{html.escape(prefix)}</b>" if not body else f"<b>{html.escape(prefix)}</b> {body}"
    class_attr = f' class="{css_class}"' if css_class else ""
    return f"<p{class_attr}>{body}</p>"


def render_mediaobject(node: etree._Element, asset_prefix: str) -> str:
    image = node.find(".//db:imagedata", NS)
    if image is None:
        return ""

    src = qualify_href(image.get("fileref", ""), asset_prefix)
    attrs = [
        f'src="{html.escape(src, quote=True)}"',
        f'alt="{html.escape(Path(image.get("fileref", "image")).stem)}"',
    ]
    width = image.get("width")
    depth = image.get("depth") or image.get("height")
    if width:
        attrs.append(f'width="{html.escape(width, quote=True)}"')
    if depth:
        attrs.append(f'height="{html.escape(depth, quote=True)}"')
    return f"<p><img {' '.join(attrs)} /></p>"


def render_list(node: etree._Element, asset_prefix: str) -> str:
    tag_name = "ol" if local_name(node) == "orderedlist" else "ul"
    items: list[str] = []
    for item in node.findall("db:listitem", NS):
        pieces: list[str] = []
        for child in item:
            child_name = local_name(child)
            if child_name == "para":
                pieces.append(render_mixed(child, asset_prefix))
            elif child_name == "mediaobject":
                pieces.append(render_mediaobject(child, asset_prefix))
        items.append(f"<li>{''.join(pieces).strip()}</li>")
    return f"<{tag_name}>{''.join(items)}</{tag_name}>"


def render_group(node: etree._Element, asset_prefix: str, css_class: str, label: str) -> str:
    blocks: list[str] = []
    first_para = True

    for child in node:
        child_name = local_name(child)
        if child_name == "para":
            blocks.append(render_para(child, asset_prefix, css_class, label if first_para else None))
            first_para = False
        elif child_name == "mediaobject":
            if first_para:
                blocks.append(f'<p class="{css_class}"><b>{html.escape(label)}</b></p>')
                first_para = False
            blocks.append(render_mediaobject(child, asset_prefix))
        elif child_name in {"itemizedlist", "orderedlist"}:
            if first_para:
                blocks.append(f'<p class="{css_class}"><b>{html.escape(label)}</b></p>')
                first_para = False
            blocks.append(render_list(child, asset_prefix))

    if first_para:
        blocks.append(f'<p class="{css_class}"><b>{html.escape(label)}</b></p>')

    return "\n".join(blocks)


def render_detail_group(node: etree._Element, asset_prefix: str) -> str:
    name = local_name(node)
    if name == "example":
        return render_group(node, asset_prefix, "text-danger", "Example:")
    if name == "note":
        role = (node.get("role") or "").lower()
        if role == "technical-comment":
            return render_group(node, asset_prefix, "text-muted", "Technical comment:")
        return render_group(node, asset_prefix, "text-primary", "Further explanation:")
    if name == "mediaobject":
        return render_mediaobject(node, asset_prefix)
    if name in {"itemizedlist", "orderedlist"}:
        return render_list(node, asset_prefix)
    return ""


def split_section_title(title: str) -> tuple[str, str]:
    match = re.match(r"^([A-Z]\.)\s+(.*)$", title)
    if match:
        return match.group(1), match.group(2)
    return "", title


def main_heading(title: str, subtitle: str) -> str:
    section_match = re.search(r"Section\s+(\d+)", subtitle)
    if section_match and not re.match(rf"^{section_match.group(1)}\.\s+", title):
        return f"{section_match.group(1)}. {title}"
    return title


def indent_block(text: str, spaces: int) -> str:
    prefix = " " * spaces
    return "\n".join(prefix + line for line in text.splitlines())


def entry_number_text(entry: etree._Element) -> str:
    number = entry.get(f"{{{NS['mrf']}}}number", "")
    if not number:
        return ""
    if "." in number:
        return number.split(".")[-1] + "."
    return number


def entry_term(entry: etree._Element) -> str:
    return read_text(entry.find("db:glossterm", NS))


def render_glossdef(glossdef: etree._Element, asset_prefix: str) -> tuple[list[str], list[str]]:
    main_blocks: list[str] = []
    detail_groups: list[str] = []

    for child in glossdef:
        name = local_name(child)
        if name == "para":
            main_blocks.append(render_para(child, asset_prefix))
        elif name in {"example", "note", "mediaobject", "itemizedlist", "orderedlist"}:
            rendered = render_detail_group(child, asset_prefix)
            if rendered:
                detail_groups.append(rendered)

    return main_blocks, detail_groups


def render_entry(entry: etree._Element, asset_prefix: str) -> str:
    term = entry_term(entry)
    number = entry_number_text(entry)
    glossdef = entry.find("db:glossdef", NS)
    if glossdef is None:
        return ""

    main_blocks, detail_groups = render_glossdef(glossdef, asset_prefix)
    detail_html = ""
    if detail_groups:
        collapse_seed = entry.get("{http://www.w3.org/XML/1998/namespace}id", "entry")
        collapse_id = "detail" + re.sub(r"[^A-Za-z0-9]+", "", collapse_seed)
        detail_html = (
            f'\n                            <div class="collapse" id="{collapse_id}">\n'
            "                                <hr />\n"
            f"{indent_block(chr(10).join(detail_groups), 32)}\n"
            "                                <hr />\n"
            "                            </div>"
        )
        toggle_html = (
            '\n                            <span class="float-right">\n'
            f'                                <a class="text-success more collapsed" data-toggle="collapse" href="#{collapse_id}"></a>\n'
            "                            </span>"
        )
    else:
        toggle_html = ""

    content = indent_block("\n".join(main_blocks), 28) if main_blocks else ""

    if term and number:
        return (
            "                    <div class=\"row\">\n"
            "                        <div class=\"col-sm-1\">\n"
            f"                            {html.escape(number)}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-2 col-sm-3\">\n"
            f"                            {html.escape(term)}{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-9 col-sm-8\">\n"
            f"{content}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )

    if term and not number:
        return (
            "                    <div class=\"row\">\n"
            "                        <div class=\"col-xl-2 col-sm-3\">\n"
            f"                            {html.escape(term)}{toggle_html}\n"
            "                        </div>\n"
            "                        <div class=\"col-xl-10 col-sm-9\">\n"
            f"{content}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )

    if not term and number:
        return (
            "                    <div class=\"row\">\n"
            "                        <div class=\"col-sm-1\">\n"
            f"                            {html.escape(number)}\n"
            "                        </div>\n"
            "                        <div class=\"col-sm-11\">\n"
            f"{indent_block('\n'.join(main_blocks), 28) if main_blocks else ''}{detail_html}\n"
            "                        </div>\n"
            "                    </div>"
        )

    return "\n".join(main_blocks + detail_groups)


def blank_unheaded_entry(entry: etree._Element) -> bool:
    return not entry_term(entry) and not entry_number_text(entry)


def render_glossdiv(glossdiv: etree._Element, asset_prefix: str, show_header: bool) -> str:
    title = read_text(glossdiv.find("db:title", NS))
    marker, name = split_section_title(title)
    section_id = glossdiv.get("{http://www.w3.org/XML/1998/namespace}id", "")
    entries = glossdiv.findall("db:glossentry", NS)

    if len(entries) == 1 and blank_unheaded_entry(entries[0]) and show_header:
        glossdef = entries[0].find("db:glossdef", NS)
        main_blocks, detail_groups = render_glossdef(glossdef, asset_prefix) if glossdef is not None else ([], [])
        combined_content = "\n".join(main_blocks + detail_groups)
        return (
            f'                    <div class="row" id="{html.escape(section_id, quote=True)}">\n'
            '                        <div class="col-sm-1">\n'
            f"                            <h5>{html.escape(marker)}</h5>\n"
            "                        </div>\n"
            '                        <div class="col-sm-11">\n'
            f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
            f"{indent_block(combined_content, 28)}\n"
            "                        </div>\n"
            "                    </div>"
        )

    header_html = ""
    if show_header:
        header_html = (
            f'                    <div class="row" id="{html.escape(section_id, quote=True)}">\n'
            '                        <div class="col-sm-1">\n'
            f"                            <h5>{html.escape(marker)}</h5>\n"
            "                        </div>\n"
            '                        <div class="col-sm-11">\n'
            f'                            <h5 class="border-bottom">{html.escape(name)}</h5>\n'
            "                        </div>\n"
            "                    </div>\n\n"
        )

    rendered_entries = "\n\n".join(render_entry(entry, asset_prefix) for entry in entries if render_entry(entry, asset_prefix))
    return header_html + rendered_entries


def render_sidebar(glossdivs: list[etree._Element], page_title: str, page_href: str) -> str:
    section_links = []
    for glossdiv in glossdivs:
        title = read_text(glossdiv.find("db:title", NS))
        if not re.match(r"^[A-Z]\.\s+", title):
            continue
        section_id = glossdiv.get("{http://www.w3.org/XML/1998/namespace}id", "")
        section_links.append(
            "                            <li class=\"nav-item\">\n"
            f'                                <a class="nav-link" href="#{html.escape(section_id, quote=True)}">{html.escape(title)}</a>\n'
            "                            </li>"
        )

    subsection_html = ""
    if section_links:
        subsection_html = (
            '                        <ul class="nav nav-pills flex-column nav-subsection">\n'
            + "\n".join(section_links)
            + "\n                        </ul>\n"
        )

    return (
        '                <ul class="nav nav-pills flex-column">\n'
        '                    <li class="nav-item">\n'
        f'                        <a class="nav-link active" href="{html.escape(page_href, quote=True)}">{html.escape(page_title)}</a>\n'
        f"{subsection_html}"
        "                    </li>\n"
        "                </ul>"
    )


def build_html(article: etree._Element, asset_prefix: str, page_href: str, switch_version_href: str) -> str:
    info = article.find("db:info", NS)
    title = read_text(info.find("db:title", NS) if info is not None else None)
    subtitle = read_text(info.find("db:subtitle", NS) if info is not None else None)
    canonical = read_text(info.find('db:uri[@type="canonical"]', NS) if info is not None else None)
    glossdivs = article.findall("db:glossary/db:glossdiv", NS)
    heading = main_heading(title, subtitle)
    description = f"{title} ({article.get(f'{{{NS['mrf']}}}status', 'working')} version {article.get(f'{{{NS['mrf']}}}framework-version', '')})".strip()

    skip_redundant_header = len(glossdivs) == 1 and read_text(glossdivs[0].find("db:title", NS)) == heading
    section_html = "\n\n".join(render_glossdiv(glossdiv, asset_prefix, not skip_redundant_header) for glossdiv in glossdivs)
    sidebar = render_sidebar(glossdivs, heading, page_href)

    return f"""<!DOCTYPE html>
<html lang="en">
<head prefix="og: http://ogp.me/ns/#">
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no">
    <meta name="description" content="{html.escape(description, quote=True)}">
    <meta name="author" content="CCCBR">
    <link rel="icon" href="https://cccbr.org.uk/wp-content/uploads/2016/05/cropped-icon-45x45.jpg" sizes="32x32">
    <link rel="icon" href="https://cccbr.org.uk/wp-content/uploads/2016/05/cropped-icon-250x250.jpg" sizes="192x192">
    <link rel="apple-touch-icon-precomposed" href="https://cccbr.org.uk/wp-content/uploads/2016/05/cropped-icon-180x180.jpg">
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="CCCBR">
    <meta property="og:title" content="CCCBR - Framework for Method Ringing">
    <meta property="og:description" content="{html.escape(description, quote=True)}">
    <meta property="og:image" content="https://cccbr.org.uk/wp-content/uploads/2017/02/CCCBR_Logo_col_rev.jpg">
    <meta property="og:url" content="{html.escape(canonical or page_href, quote=True)}">
    <title>Framework for Method Ringing - {html.escape(title)}</title>
    <link href="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0-beta/css/bootstrap.min.css" rel="stylesheet">
    <link href="{html.escape(join_href(asset_prefix, 'mrf.css'), quote=True)}" rel="stylesheet">
</head>
<body>
    <header>
        <nav class="navbar navbar-expand-md navbar-dark fixed-top bg-cccbr">
            <a class="navbar-brand" href="{html.escape(join_href(asset_prefix, 'index.html'), quote=True)}">Framework for Method Ringing&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</a>
            <a class="navbar-brand" href="https://cccbr.org.uk/"><img src="{html.escape(join_href(asset_prefix, 'images/cc-header.png'), quote=True)}" height="60" alt="CCCBR">&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</a>
            <img src="{html.escape(join_href(asset_prefix, 'images/version.svg'), quote=True)}" width="200" height="36" alt="Version banner" />
            <small><a id="switchv" href="{html.escape(switch_version_href, quote=True)}">[Switch version]</a></small>
        </nav>
    </header>

    <div class="container-fluid collapse-group">
        <div class="row">
            <nav class="col-sm-3 col-xl-2 d-none d-sm-block bg-light sidebar">
{indent_block(sidebar, 16)}
                <div class="btn-navbar">
                    <button class="btn btn-sm btn-block btn-success open-button" type="button">Show all notes</button>
                    <div class="text-success"><small>Click + to show a note.</small></div>
                    <button class="btn btn-sm btn-block btn-success close-button" type="button">Hide all notes</button>
                </div>
            </nav>

            <main role="main" class="col-sm-9 ml-sm-auto col-xl-10 pt-3">
                <div class="container-fluid">
                    <div class="row">
                        <div class="col-sm-12">
                            <h2>{html.escape(heading)}</h2>
                        </div>
                    </div>

{section_html}
                </div>
            </main>
        </div>
    </div>

    <script src="https://code.jquery.com/jquery-3.2.1.slim.min.js" integrity="sha384-KJ3o2DKtIkvYIK3UENzmM7KCkRr/rE9/Qpg6aAZGJwFDMVNA/GpGFF93hXpG5KkN" crossorigin="anonymous"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/popper.js/1.11.0/umd/popper.min.js" integrity="sha384-b/U6ypiBEHpOf/4+1nzFpr53nxSS+GLCkfwBdFNTxtclqqenISfwAzpKaMNFNmj4" crossorigin="anonymous"></script>
    <script src="https://maxcdn.bootstrapcdn.com/bootstrap/4.0.0-beta/js/bootstrap.min.js" integrity="sha384-h0AbiXch4ZDo7tp9hKZ4TsHbi047NrKGLO3SEJAg45jXxnGIfYzk4Si90RDIqNm1" crossorigin="anonymous"></script>
    <script src="{html.escape(join_href(asset_prefix, 'mrf.js'), quote=True)}"></script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert DocBook XML back into HTML.")
    parser.add_argument("input", help="Path to the input DocBook XML file")
    parser.add_argument("output", help="Path to the output HTML file")
    parser.add_argument("--asset-prefix", default="", help="Prefix to prepend to local site assets and relative links")
    parser.add_argument("--page-href", default=None, help="Sidebar link for the active page")
    parser.add_argument("--switch-version-href", default="../index.html", help="Link used by the [Switch version] control")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    article = etree.parse(str(input_path), etree.XMLParser(remove_blank_text=False)).getroot()
    html_text = build_html(
        article,
        asset_prefix=args.asset_prefix,
        page_href=args.page_href or output_path.name,
        switch_version_href=args.switch_version_href,
    )
    output_path.write_text(html_text, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
