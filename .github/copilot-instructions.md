# Copilot instructions for `method_ringing_framework`

## Commands

There is no repo-wide build system, test runner, or linter. Validation in this repository is done by running the conversion scripts directly and syntax-checking individual Python files.

### Focused validation

- Syntax-check one Python script:
  - `python -m py_compile scripts\convert_docbook_to_html.py`
- Syntax-check the active Python converters together:
  - `python -m py_compile scripts\convert_html_to_docbook.py scripts\convert_docbook_to_html.py scripts\convert_docbook_to_latex.py`

### Conversion commands

- Convert the versioned HTML source trees into generated DocBook XML:
  - `powershell -ExecutionPolicy Bypass -File scripts\convert_html_tree_to_docbook.ps1`
- Render the generated DocBook XML tree back into HTML and LaTeX:
  - `powershell -ExecutionPolicy Bypass -File scripts\render_docbook_tree.ps1`
- Convert one HTML page into DocBook XML:
  - `python scripts\convert_html_to_docbook.py -i version2\fundamentals.html -o generated\xml\version2\fundamentals.xml --base-uri https://cccbr.github.io/method_ringing_framework/version2`
- Render one DocBook XML file back into HTML:
  - `python scripts\convert_docbook_to_html.py generated\xml\version2\fundamentals.xml generated\html\edition2\fundamentals.html --asset-prefix ../../../version2 --switch-version-href ../../../index.html`
- Render one DocBook XML file into LaTeX:
  - `python scripts\convert_docbook_to_latex.py generated\xml\version2\fundamentals.xml generated\tex\edition2\fundamentals.tex --asset-root ../../../version2`

## High-level architecture

- The repository is primarily a **versioned static website**, not an app with a build pipeline. `index.html` is the version picker; `version1\` and `version2\` are complete published site trees with their own HTML pages, assets, `mrf.css`, and `mrf.js`.
- `latest` is a **symbolic link to `version2`**. Treat `version2` as the source of truth and do not make parallel edits in both places.
- The site layout is hand-authored Bootstrap 4 HTML with a fixed header, left sidebar navigation, and content in `<main>`. Collapsible “notes” are part of the content model and are driven by `mrf.js` plus CSS classes in `mrf.css`.
- Generated artifacts live under the ignored `generated\` tree:
  - `generated\xml\version1\` and `generated\xml\version2\` for DocBook output from the source HTML
  - `generated\html\edition*\` for HTML rendered back from DocBook
  - `generated\tex\edition*\` for LaTeX rendered back from DocBook
- The active converters are:
  - `scripts\convert_html_to_docbook.py` converts source HTML pages into DocBook 5 XML with glossary-oriented structure and `mrf:` metadata.
  - `scripts\convert_docbook_to_html.py` renders DocBook back into pages that match the original site styling.
  - `scripts\convert_docbook_to_latex.py` renders the same DocBook into macro-based LaTeX for PDF generation.
  - `scripts\convert_html_tree_to_docbook.ps1` and `scripts\render_docbook_tree.ps1` are the bulk wrappers for the full version trees.

## Key conventions

- Prefer the **current Python conversion pipeline** over any older notes about prototype tooling. The old HTML-to-XML prototype scripts were removed and replaced by `scripts\convert_html_to_docbook.py` plus the PowerShell tree wrappers.
- When iterating on conversion quality, use the current `version2\fundamentals.html` source together with regenerated DocBook output under `generated\`.
- Keep authoritative definitions **in page context**. The current target DocBook shape is glossary-oriented (`article > info > glossary > glossdiv > glossentry > glossdef`) with CCCBR-specific metadata in the `mrf:` namespace, rather than extracting a separate editorial glossary.
- In the source HTML, note types are encoded by CSS classes and layout rather than semantic tags:
  - `text-danger` = example
  - `text-primary` = further explanation
  - `text-muted` = technical comment
  Future conversion work should preserve those distinctions.
- The static HTML pages use **site-relative asset paths**. Generated HTML and TeX live outside the versioned site trees, so use the existing `--asset-prefix` / `--asset-root` support or the supplied PowerShell wrappers rather than hard-coding source-tree-relative paths.
- Changes to shared presentation behavior often need attention in more than one place: root-level `mrf.css`/`mrf.js` exist alongside copies inside each versioned site tree.
- Keep generated artifacts out of `version1\` and `version2\`. Those trees are source material; generated output belongs under `generated\`.
- `.editorconfig` is minimal but does establish **spaces** as the indentation style.
