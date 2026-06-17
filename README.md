# Framework for Method Ringing Repository

This repository holds the documents that form the Central Council for Church Bell Ringer's Framework for Method Ringing.

The first version of the framework was approved by the Central Council Executive on 24 February 2019. It was issued to members and affiliated societies on 28 February 2019 giving notice of 1 June 2019 as its effective implementation date.

The principal branches are:

* `master` - Documents for downloading
* `gh-pages` - Public web pages of the framework accessible at https://cccbr.github.io/method_ringing_framework/

## XML-led publishing workflow

The repository is moving to XML as the maintained editorial source.

1. Bootstrap or refresh XML from the existing website HTML with `scripts\convert_html_tree_to_xml.py`.
2. Maintain the Framework in XML.
3. Regenerate website HTML from XML with `scripts\render_docbook_tree.py`.
4. Generate PDF document versions from XML with `scripts\generate_pdf.py`.
5. Regenerate the published outputs in CI when XML changes are pushed.

The existing `version1\`, `version2\` and `version3\` website trees remain the source material used to bootstrap the XML.

## Outputs

- `generated\xml\` - generated DocBook XML
- `generated\html\edition*\` - regenerated website HTML
- `generated\tex\edition*\` - generated LaTeX
- `generated\pdf\edition*\` - generated PDFs

The PDF outputs currently include:

- `framework-versionN-main.pdf` - main Framework volume without notes
- `framework-versionN-main-full.pdf` - main Framework volume with notes
- `framework-versionN-appendices.pdf` - appendices volume with notes

## Prerequisites for local generation

- Python 3.12+ with the packages in `requirements.txt`
- A LaTeX distribution with XeLaTeX available (MiKTeX or TeX Live)
- Inkscape for SVG-to-PDF conversion during PDF builds
- On Windows, use `py -3.14` to avoid accidentally invoking Inkscape's bundled `python.exe`
- For XeLaTeX output, Calibri/Consolas are used when installed; otherwise the templates fall back to Carlito and DejaVu Sans Mono

Install the Python dependencies with:

`py -3.14 -m pip install -r requirements.txt`

## Local commands

- Full build:
  - `powershell -ExecutionPolicy Bypass -File .\build.ps1`
- Rebuild one edition:
  - `powershell -ExecutionPolicy Bypass -File .\build.ps1 -Edition edition2`
- Regenerate XML only:
  - `py -3.14 scripts\build.py --edition edition2 --xml-only`
- Render committed XML to website HTML and LaTeX:
  - `py -3.14 scripts\render_docbook_tree.py --source-xml xml --metadata-xml xml`
- Compile PDFs from the rendered TeX:
  - `py -3.14 scripts\generate_pdf.py`

## Framework XML tags

The XML is DocBook 5 with a small `mrf:` metadata namespace. The main tags used are:

| Tag | Purpose |
| --- | --- |
| `article` | Root document element for each page |
| `info` | Document metadata container |
| `title` / `subtitle` | Page and section titles |
| `edition` | Framework edition number in metadata |
| `releaseinfo` | Status, authority, and date metadata |
| `uri` | Canonical source URL |
| `othermeta` | Source-path metadata |
| `glossary` | Glossary-oriented content container |
| `glossdiv` | Glossary or appendix subsection wrapper |
| `glossentry` | Individual glossary entry |
| `glossterm` | Term name in a glossary entry |
| `glossdef` | Definition text for a glossary entry |
| `section` | Narrative section or appendix section |
| `para` | Paragraph text |
| `orderedlist` | Ordered list |
| `itemizedlist` | Unordered list |
| `listitem` | List item |
| `question` | FAQ question block, including nested list content where needed |
| `answer` | FAQ answer block |
| `emphasis` | Bold, italic, underline, or other inline emphasis |
| `literal` | Literal or code-style inline text |
| `link` | Cross-reference or external link |
| `informaltable` | Tables without formal captions |
| `tgroup` | Table group and column definition container |
| `thead` / `tbody` | Table header and body |
| `row` / `entry` | Table rows and cells |
| `example` | Example block |
| `note` | Further explanation or technical comment block |
| `mediaobject` / `imageobject` / `imagedata` | Embedded images and diagrams |

The framework metadata attributes in the `mrf:` namespace are:

| Attribute | Purpose |
| --- | --- |
| `mrf:status` | Publication status such as historic, definitive, or draft |
| `mrf:authority` | Publishing authority, currently CCCBR |
| `mrf:framework-version` | Numeric framework edition version |
| `mrf:edition-label` | Display label such as Edition 1 |
| `mrf:source-title` | Original source title used for generated glossary content |
| `mrf:label` | Display label for structured list items such as FAQ subitems |

The generated XML also uses standard XML attributes such as `xml:id` and `xml:lang`.
