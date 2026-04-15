DocBook notes and plan for converting the Framework for Method Ringing repository to DocBook 5 XML.

Decisions:
- DocBook 5 (RELAX NG) profile used.
- One DocBook file per logical HTML page (easier diffs and edits).
- Keep definitions inline in source context; annotate each definition with termmeta (xml:id, term, authority, status, version-id, canonical-uri, issued date, provenance).
- Do NOT create an editorial glossary; create a derived machine-readable terms index (xml/terms-index.xml) during conversion.

Next steps in branch xml-format:
1. implement-semantic-metadata: author termmeta schema and canonical URI rules.
2. implement-parser: build scripts/convert_html_to_docbook.py (prototype provided) and scripts/generate_term_index.py.
3. prototype-conversion-v2: convert representative pages and produce HTML+JSON-LD and PDF samples.

Provenance: This file is committed to the xml-format feature branch as the authoritative plan document.
