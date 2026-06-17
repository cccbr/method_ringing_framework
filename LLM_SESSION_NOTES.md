# LLM Session Notes

This file captures repository details that are easy to lose across long Copilot sessions.

## Current repo direction

- The Framework is moving to an XML-led publishing workflow.
- Source HTML in `version1\`, `version2\`, and `version3\` is used to bootstrap XML.
- XML is the maintained source; HTML, TeX, and PDF are regenerated from it.
- Generated output lives under `generated\html\edition*\`, `generated\xml\edition*\`, `generated\tex\edition*\`, and `generated\pdf\edition*\`.

## Windows / tooling notes

- On Windows, use `py -3.14` for Python commands. Bare `python` can resolve to Inkscape’s bundled interpreter.
- There is no repo-wide generic lint/test suite. Validation is usually:
  - `py -3.14 -m py_compile scripts\convert_docbook_to_html.py scripts\convert_html_to_docbook.py`
  - `py -3.14 scripts\build.py --xml-only --no-cleanup`
  - `py -3.14 scripts\build.py --html-only --no-cleanup`

## XML -> HTML rendering conventions

- Ordered lists use the far-left number column.
- Nested ordered lists keep a smaller indent than top-level lists.
- Standalone body paragraphs, unordered lists, and tables should align to the standard text indent, not the ordered-list number column.
- If a page needs different spacing or layout, prefer a dedicated XML role/descriptor instead of special-casing the shared renderer.
- FAQ rows now use explicit `question` / `answer` XML blocks, and FAQ subitems keep their displayed row label on `mrf:label` so the renderer can place it in the left column.
- FAQ question blocks may include nested ordered lists when the source HTML places subpoints inside the question text; keep the nested list inside `mrf:question` rather than flattening it.

## Appendix and glossary notes

- Appendix headings should render with the appendix prefix, e.g. `Appendix A. Place Notation`.
- Appendix E (edition 1) and Appendix F (editions 2 and 3) suppress `glossterm` generation for the Rows/Places/Changes-style entries.
- Some ordered lists continue after glossary entries; the renderer may need `startingnumber` from the preceding `glossentry` count.
- Appendix H consultation submitter subheadings such as `Submitter #1` should be preserved.
- FAQ pages should keep the question/answer split explicit in XML rather than inferring it from plain paragraphs.

## Files worth checking first

- `scripts\convert_html_to_docbook.py`
- `scripts\convert_docbook_to_html.py`
- `scripts\render_docbook_tree.py`
- `scripts\build.py`
- `README.md`
