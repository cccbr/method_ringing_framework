DocBook notes and plan for converting the Framework for Method Ringing repository to DocBook 5 XML.

Decisions:
- DocBook 5 (RELAX NG) profile used.
- One DocBook file per logical HTML page (easier diffs and edits).
- Keep definitions inline in source context; represent them as glossary-oriented DocBook (`article > info > glossary > glossdiv > glossentry > glossdef`) with CCCBR-specific metadata in the `mrf:` namespace.
- Do not keep generated artifacts beside source HTML; write them under the ignored `generated/` tree.

Current workflow:
1. `scripts/convert_html_to_docbook.py` converts `version1/` and `version2/` source HTML pages into DocBook XML.
2. `scripts/convert_docbook_to_html.py` renders that DocBook XML back into Bootstrap-styled HTML for review.
3. `scripts/convert_docbook_to_latex.py` renders the same XML into macro-based LaTeX for PDF generation.
4. `scripts/convert_html_tree_to_docbook.ps1` and `scripts/render_docbook_tree.ps1` run those conversions across the full version trees.

Current state:
- The old prototype HTML-to-DocBook scripts and preview XML outputs have been removed.
- `xml/version2/fundamentals-sample.xml` is the hand-authored benchmark for conversion quality.
- Generated pipeline output now targets `generated/xml/`, `generated/html/`, and `generated/tex/`.

Provenance: This file is committed to the xml-format feature branch as the authoritative plan document.
