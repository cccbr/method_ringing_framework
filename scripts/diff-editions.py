#!/usr/bin/env python3
"""Compare two editions of the Framework and produce a readable diff report."""

import argparse
import difflib
import sys
from pathlib import Path

from lxml import etree

NS = {
    "db": "http://docbook.org/ns/docbook",
    "xlink": "http://www.w3.org/1999/xlink",
    "mrf": "https://cccbr.org.uk/ns/method-ringing-framework",
}


def read_text(elem: etree._Element | None) -> str:
    if elem is None:
        return ""
    return "".join(elem.itertext()).strip()


def normalize_xml(text: str) -> str:
    """Pretty-print and normalize whitespace for comparison."""
    try:
        root = etree.fromstring(text.encode("utf-8"))
        etree.indent(root, space="  ")
        return etree.tostring(root, encoding="unicode", pretty_print=True)
    except Exception:
        return text


def compare_glossary_terms(
    old_dir: Path, new_dir: Path, stem: str
) -> list[str]:
    """Compare glossary terms between two editions for a given page."""
    report: list[str] = []
    old_terms: dict[str, tuple[str, tuple[str, ...]]] = {}
    new_terms: dict[str, tuple[str, tuple[str, ...]]] = {}

    for label, d, store in [("old", old_dir, old_terms), ("new", new_dir, new_terms)]:
        path = d / f"{stem}.xml"
        if not path.exists():
            continue
        root = etree.parse(str(path)).getroot()
        for entry in root.findall(".//db:glossentry", NS):
            terms = entry.findall("db:glossterm", NS)
            if not terms:
                continue
            primary = read_text(terms[0])
            if not primary:
                continue
            syns = tuple(read_text(t) for t in terms[1:] if read_text(t))
            mrf_num = entry.get(f"{{{NS['mrf']}}}number", "")
            store[primary.casefold()] = (mrf_num, syns)

    old_keys = set(old_terms.keys())
    new_keys = set(new_terms.keys())

    added = new_keys - old_keys
    removed = old_keys - new_keys

    if added:
        report.append(f"  **Terms added:**")
        for key in sorted(added, key=str.casefold):
            mrf_num, syns = new_terms[key]
            syn_str = f" (synonyms: {', '.join(syns)})" if syns else ""
            report.append(f"    - {key} [{mrf_num}]{syn_str}")

    if removed:
        report.append(f"  **Terms removed:**")
        for key in sorted(removed, key=str.casefold):
            mrf_num, _syns = old_terms[key]
            report.append(f"    - {key} [{mrf_num}]")

    # Check for synonym changes
    common = old_keys & new_keys
    for key in sorted(common, key=str.casefold):
        _, old_syns = old_terms[key]
        _, new_syns = new_terms[key]
        if set(old_syns) != set(new_syns):
            added_syns = set(new_syns) - set(old_syns)
            removed_syns = set(old_syns) - set(new_syns)
            parts = []
            if added_syns:
                parts.append(f"added {', '.join(sorted(added_syns))}")
            if removed_syns:
                parts.append(f"removed {', '.join(sorted(removed_syns))}")
            report.append(f"  **Synonyms changed for '{key}':** {', '.join(parts)}")

    return report


def compare_sections(
    old_dir: Path, new_dir: Path, stem: str
) -> list[str]:
    """Compare section/glossdiv headings between editions."""
    report: list[str] = []
    old_sections: set[str] = set()
    new_sections: set[str] = set()

    for label, d, store in [("old", old_dir, old_sections), ("new", new_dir, new_sections)]:
        path = d / f"{stem}.xml"
        if not path.exists():
            continue
        root = etree.parse(str(path)).getroot()
        for elem in root.findall(".//db:title", NS):
            title = read_text(elem)
            if title:
                store.add(title)

    added = new_sections - old_sections
    removed = old_sections - new_sections

    if added:
        report.append("  **Sections added:**")
        for t in sorted(added):
            report.append(f"    - {t}")
    if removed:
        report.append("  **Sections removed:**")
        for t in sorted(removed):
            report.append(f"    - {t}")

    return report


def format_diff_header(old_path: str, new_path: str) -> str:
    return f"--- {old_path}\n+++ {new_path}"


def produce_report(
    old_edition: str,
    new_edition: str,
    old_dir: Path,
    new_dir: Path,
    *,
    full_diff: bool = False,
) -> str:
    lines: list[str] = []
    lines.append(f"# Framework Diff: {old_edition} → {new_edition}\n")
    lines.append(f"Comparing `{old_dir}` with `{new_dir}`\n")

    old_files = {f.stem for f in old_dir.glob("*.xml")} if old_dir.exists() else set()
    new_files = {f.stem for f in new_dir.glob("*.xml")} if new_dir.exists() else set()

    all_stems = sorted(old_files | new_files)

    only_old = old_files - new_files
    only_new = new_files - old_files

    if only_old:
        lines.append("## Pages removed\n")
        for s in sorted(only_old):
            lines.append(f"- {s}")
        lines.append("")

    if only_new:
        lines.append("## Pages added\n")
        for s in sorted(only_new):
            lines.append(f"- {s}")
        lines.append("")

    changed_count = 0
    for stem in sorted(old_files & new_files):
        old_path = old_dir / f"{stem}.xml"
        new_path = new_dir / f"{stem}.xml"

        try:
            old_text = normalize_xml(old_path.read_text(encoding="utf-8"))
            new_text = normalize_xml(new_path.read_text(encoding="utf-8"))
        except Exception as e:
            lines.append(f"### {stem} (error reading: {e})\n")
            continue

        if old_text == new_text:
            continue

        changed_count += 1
        lines.append(f"## {stem}\n")

        term_report = compare_glossary_terms(old_dir, new_dir, stem)
        section_report = compare_sections(old_dir, new_dir, stem)

        if term_report:
            lines.append("### Glossary term changes\n")
            lines.extend(term_report)
            lines.append("")

        if section_report:
            lines.append("### Section changes\n")
            lines.extend(section_report)
            lines.append("")

        if full_diff:
            lines.append("### Full diff\n")
            lines.append("```diff")
            diff_lines = list(
                difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile=f"{old_edition}/{stem}.xml",
                    tofile=f"{new_edition}/{stem}.xml",
                )
            )
            # Limit large diffs
            if len(diff_lines) > 500:
                lines.extend(diff_lines[:500])
                lines.append(f"\n... ({len(diff_lines) - 500} more lines)\n")
            else:
                lines.extend(diff_lines)
            lines.append("```\n")

    if changed_count == 0:
        lines.append("## No changes found\n")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diff two editions of the Framework for Method Ringing"
    )
    parser.add_argument(
        "old_edition", help="Older edition (e.g. edition2)"
    )
    parser.add_argument(
        "new_edition", help="Newer edition (e.g. edition3)"
    )
    parser.add_argument(
        "--source-dir", default="xml-source",
        help="Source XML directory (default: xml-source)"
    )
    parser.add_argument(
        "--output", "-o", default="diff-report.md",
        help="Output file (default: diff-report.md)"
    )
    parser.add_argument(
        "--full-diff", action="store_true",
        help="Include full unified diff for every changed file"
    )
    args = parser.parse_args()

    base = Path(args.source_dir)
    old_dir = base / args.old_edition
    new_dir = base / args.new_edition

    if not old_dir.exists() and not new_dir.exists():
        print(f"Neither {old_dir} nor {new_dir} exist", file=sys.stderr)
        return 1

    report = produce_report(
        args.old_edition, args.new_edition,
        old_dir, new_dir,
        full_diff=args.full_diff,
    )

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8", newline="\n")
        print(f"Report written to {args.output}")
    else:
        print(report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
