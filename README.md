# Method Ringing Framework

This branch is establishing an XML-led publishing workflow for the Framework.

The existing `version1\`, `version2\` and `version3\` website trees remain the published source material used to bootstrap the XML, but the goal of this work is to make the XML the maintained editorial source going forward. From that XML, the repository can regenerate both website HTML and PDF document outputs.

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
   - Edition folders are discovered automatically, so additional `versionN\` / `editionN\` XML folders are picked up without hard-coded script updates.

4. **Generate PDF document versions from XML**
   - `scripts\convert_docbook_to_latex.py` renders a single XML file to LaTeX.
   - `scripts\generate_master_latex.py` assembles volume-level LaTeX documents.
   - `scripts\generate_pdf.py` compiles the generated LaTeX into PDFs.
   - The PDF outputs currently include:
     - `framework-versionN-main.pdf` - main Framework volume without notes
     - `framework-versionN-main-full.pdf` - main Framework volume with notes
     - `framework-versionN-appendices.pdf` - appendices volume with notes

5. **Automate regeneration in CI**
   - `.github\workflows\ci.yml` is intended to run on pushes to `main` that change `xml\**`, and can also be run manually.
   - The workflow regenerates the HTML and PDF outputs from committed XML and publishes them to the `gh-pages` branch.

## Prerequisites for local generation

- Python 3.12+ with the packages in `requirements.txt`
- A LaTeX distribution with XeLaTeX available (MiKTeX or TeX Live)
- Inkscape for SVG-to-PDF conversion during PDF builds
- On Windows, use `py -3.14` to avoid accidentally invoking Inkscape's bundled `python.exe`
- For XeLaTeX output, Calibri/Consolas are used when installed; otherwise the templates fall back to Carlito and DejaVu Sans Mono

Install the Python dependencies with:

- `py -3.14 -m pip install -r requirements.txt`

## Local orchestration

- `build.ps1` is the Windows entry point for local builds.
- `scripts\build.py` orchestrates the full pipeline:
  - HTML -> XML
  - XML -> HTML / LaTeX
  - LaTeX -> PDF

Typical local commands:

- Full build:
  - `powershell -ExecutionPolicy Bypass -File .\build.ps1`
- Rebuild one edition:
  - `powershell -ExecutionPolicy Bypass -File .\build.ps1 -Edition edition2`
- Regenerate XML only:
  - `py -3.14 scripts\build.py --edition edition2 --xml-only`
- Render committed XML to website HTML/LaTeX:
  - `py -3.14 scripts\render_docbook_tree.py --source-xml xml --metadata-xml xml`
- Compile PDFs from the rendered TeX:
  - `py -3.14 scripts\generate_pdf.py`

## Output locations

- Maintained XML source: `xml\`
- Intermediate/generated XML: `generated\xml\`
- Regenerated HTML: `generated\html\edition*\`
- Generated LaTeX: `generated\tex\edition*\`
- Generated PDFs: `generated\pdf\edition*\`

The `generated\` tree is build output and is ignored by git.
