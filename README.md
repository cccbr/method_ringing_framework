# Method Ringing Framework

This branch is establishing an XML-led publishing workflow for the Framework.

The existing `version1\` and `version2\` website trees remain the published source material used to bootstrap the XML, but the goal of this work is to make the XML the maintained editorial source going forward. From that XML, the repository can regenerate both website HTML and PDF document outputs.

## Workflow

1. **Bootstrap or refresh XML from the existing website HTML**
   - `scripts\convert_html_to_docbook.py` converts a single HTML page into DocBook XML.
   - `scripts\convert_html_tree_to_xml.py` converts a whole versioned HTML tree into XML.
   - This step is used to capture the current website content in structured XML form.

2. **Maintain the Framework in XML**
   - The intention of this branch is that future content maintenance happens in XML rather than by hand-editing the published HTML trees.
   - The checked-in XML under `xml\` is the long-term source to edit and review.

3. **Regenerate website HTML from XML**
   - `scripts\convert_docbook_to_html.py` renders a single XML file back to website HTML.
   - `scripts\render_docbook_tree.py` renders a whole XML tree to HTML and LaTeX.

4. **Generate PDF document versions from XML**
   - `scripts\convert_docbook_to_latex.py` renders a single XML file to LaTeX.
   - `scripts\generate_master_latex.py` assembles volume-level LaTeX documents.
   - `scripts\generate_pdf.py` compiles the generated LaTeX into PDFs.

5. **Automate regeneration in CI**
   - The intended end state is a CI workflow that runs whenever XML changes are pushed.
   - That workflow should regenerate the HTML and PDF outputs from the XML, so the published website and document versions are reproducible from the maintained XML source.

## Local orchestration

- `build.ps1` is the Windows entry point for local builds.
- `scripts\build.py` orchestrates the full pipeline:
  - HTML -> XML
  - XML -> HTML / LaTeX
  - LaTeX -> PDF

Typical local commands:

- Full build:
  - `powershell -ExecutionPolicy Bypass -File .\build.ps1`
- Rebuild one version:
  - `powershell -ExecutionPolicy Bypass -File .\build.ps1 -Version edition2`
- Regenerate XML only:
  - `python scripts\build.py --version edition2 --xml-only`

## Output locations

- Maintained XML source: `xml\`
- Intermediate/generated XML: `generated\xml\`
- Regenerated HTML: `generated\html\edition*\`
- Generated LaTeX: `generated\tex\edition*\`
- Generated PDFs: `generated\pdf\edition*\`

The `generated\` tree is build output and is ignored by git.
