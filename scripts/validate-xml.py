#!/usr/bin/env python3
"""Validate XML source files for structural correctness before building."""

import argparse
import sys
from pathlib import Path

from lxml import etree

NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}

DB = f"{{{NS['db']}}}"


def _line(elem: etree._Element) -> int:
    """Get the line number of an element, falling back to 0."""
    return elem.sourceline or 0


def _tag(elem: etree._Element) -> str:
    """Get the local tag name."""
    return etree.QName(elem).localname


def validate_file(path: Path) -> list[str]:
    """Validate a single XML file. Returns a list of error messages."""
    errors: list[str] = []

    # Step 1: Parse with line-number reporting
    parser = etree.XMLParser(remove_blank_text=False)
    try:
        root = etree.parse(str(path), parser).getroot()
    except etree.XMLSyntaxError as e:
        line = e.lineno if hasattr(e, "lineno") else "?"
        errors.append(f"{path}: line {line}: XML syntax error: {e}")
        return errors
    except OSError as e:
        errors.append(f"{path}: could not read file: {e}")
        return errors

    # Step 2: Check glossary structure
    glossary = root.find(f"{DB}glossary")
    if glossary is not None:
        glossdivs = glossary.findall(f"{DB}glossdiv")
        bare_entries = glossary.findall(f"{DB}glossentry")

        # Critical: bare glossentry outside glossdiv
        if bare_entries:
            for entry in bare_entries:
                terms = entry.findall(f"{DB}glossterm")
                term_text = terms[0].text if terms else "(unnamed)"
                errors.append(
                    f"{path}: line {_line(entry)}: "
                    f"<glossentry> '{term_text}' is a direct child of <glossary> "
                    f"without a <glossdiv> wrapper — will be SILENTLY DROPPED from output"
                )

        # Each glossdiv must have a title
        for div in glossdivs:
            title = div.find(f"{DB}title")
            if title is None:
                div_id = div.get("{http://www.w3.org/XML/1998/namespace}id", "")
                errors.append(
                    f"{path}: line {_line(div)}: "
                    f"<glossdiv xml:id=\"{div_id}\"> has no <title> — section will render incorrectly"
                )

        # Content directly in glossary (not in glossdiv)
        for child in glossary:
            if _tag(child) not in {"glossdiv", "glossentry"}:
                errors.append(
                    f"{path}: line {_line(child)}: "
                    f"<{_tag(child)}> is a direct child of <glossary> outside any <glossdiv> — will be SILENTLY DROPPED"
                )

    # Step 3: Elements that will be silently dropped by renderers
    # Check for common patterns that cause content loss:
    DROPPED_IN_GLOSSDIV = {
        "section", "question", "answer",
    }
    for glossdiv in root.findall(f".//{DB}glossdiv"):
        for child in glossdiv:
            name = _tag(child)
            if name == "title":
                continue
            if name in DROPPED_IN_GLOSSDIV:
                errors.append(
                    f"{path}: line {_line(child)}: "
                    f"<{name}> inside <glossdiv> — will be SILENTLY DROPPED by renderers. "
                    f"Use <glossentry> only within a <glossdiv>, or use <section> for narrative content."
                )

    # Check listitem children that would be dropped
    DROPPED_IN_LISTITEM = {
        "section", "glossdiv",
    }
    for li in root.findall(f".//{DB}listitem"):
        for child in li:
            name = _tag(child)
            if name in DROPPED_IN_LISTITEM:
                errors.append(
                    f"{path}: line {_line(child)}: "
                    f"<{name}> inside <listitem> — will be SILENTLY DROPPED by renderers"
                )

    # Step 4: Check glossentry structure
    for entry in root.findall(f".//{DB}glossentry"):
        glossterm = entry.find(f"{DB}glossterm")
        if glossterm is None:
            entry_id = entry.get("{http://www.w3.org/XML/1998/namespace}id", "")
            errors.append(
                f"{path}: line {_line(entry)}: "
                f"<glossentry xml:id=\"{entry_id}\"> has no <glossterm>"
            )

        glossdef = entry.find(f"{DB}glossdef")
        if glossdef is None:
            entry_id = entry.get("{http://www.w3.org/XML/1998/namespace}id", "")
            errors.append(
                f"{path}: line {_line(entry)}: "
                f"<glossentry xml:id=\"{entry_id}\"> has no <glossdef>"
            )

    # Step 5: Warn about elements inside glossdef that may be silently dropped
    for glossdef in root.findall(f".//{DB}glossdef"):
        for child in glossdef:
            name = _tag(child)
            if name not in {"para", "informaltable", "itemizedlist", "orderedlist",
                           "example", "note", "mediaobject", "section"}:
                errors.append(
                    f"{path}: line {_line(child)}: "
                    f"<{name}> inside <glossdef> — may be SILENTLY DROPPED by renderers"
                )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate DocBook XML source files before building"
    )
    parser.add_argument(
        "source_dir", nargs="?", default="xml-source",
        help="Source XML directory (default: xml-source)"
    )
    args = parser.parse_args()

    base = Path(args.source_dir)
    if not base.exists():
        print(f"Error: directory not found: {base}", file=sys.stderr)
        return 1

    xml_files = sorted(base.rglob("*.xml"))
    if not xml_files:
        print(f"No XML files found in {base}", file=sys.stderr)
        return 1

    print(f"Validating {len(xml_files)} XML file(s) in {base} ...\n")

    total_errors = 0
    for path in xml_files:
        errors = validate_file(path)
        if errors:
            for e in errors:
                print(f"  ERROR: {e}", file=sys.stderr)
            total_errors += len(errors)

    if total_errors:
        print(f"\n{total_errors} validation error(s) found", file=sys.stderr)
        return 1

    print("All files passed validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
