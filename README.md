# Framework for Method Ringing Repository

This repository holds the documents that form the Central Council for Church Bell Ringer's Framework for Method Ringing.

The first version of the framework was approved by the Central Council Executive on 24 February 2019. It was issued to members and affiliated societies on 28 February 2019 giving notice of 1 June 2019 as its effective implementation date.

The principal branches are:

* `master` - Documents for downloading
* `gh-pages` - Public web pages of the framework accessible at [framework.cccbr.org.uk](https://framework.cccbr.org.uk/) or https://cccbr.github.io/method_ringing_framework/

## XML-led publishing workflow

The repository has moved to XML as the maintained editorial source.

1. Bootstrap or refresh XML from the existing website HTML with `scripts\build-xml.ps1`.
2. Maintain the Framework in XML in the folder `xml-source\editionN`.
3. Regenerate website HTML from XML with `scripts\build-web.ps1`.
4. Generate PDF document versions from XML with `scripts\build-pdf.ps1`.
5. Regenerate the published outputs in `gh-pages` using continuous integration when XML changes are pushed to `master`.

The existing `version1\`, `version2\` and `version3\` website trees remain the source material used to bootstrap the XML.
The `xml-source\edition1\`, `xml-source\edition2\` and `xml-source\edition3\` now contain the framework source material in XML.

## Local Outputs

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

Three PowerShell scripts build the outputs independently. Each accepts `-Edition edition2` for a single edition, or no parameter for all editions:

- Build XML from HTML source:
  - All editions: `powershell -ExecutionPolicy Bypass -File scripts\build-xml.ps1`
  - One edition: `powershell -ExecutionPolicy Bypass -File scripts\build-xml.ps1 -Edition edition2`
- Build website HTML:
  - All editions: `powershell -ExecutionPolicy Bypass -File scripts\build-web.ps1`
  - One edition: `powershell -ExecutionPolicy Bypass -File scripts\build-web.ps1 -Edition edition2`
- Build PDFs (generates LaTeX then compiles):
  - All editions: `powershell -ExecutionPolicy Bypass -File scripts\build-pdf.ps1`
  - One edition: `powershell -ExecutionPolicy Bypass -File scripts\build-pdf.ps1 -Edition edition2`

Full pipeline: run `build-xml.ps1`, then `build-web.ps1`, then `build-pdf.ps1` in sequence.

## Comparing editions

`scripts\diff-editions.py` produces a markdown report of structural differences between two editions:

- `py -3.14 scripts\diff-editions.py edition2 edition3` — writes to `diff-report.md`
- `py -3.14 scripts\diff-editions.py edition2 edition3 --full-diff` — includes full XML diffs
- `py -3.14 scripts\diff-editions.py edition2 edition3 -o my-report.md` — custom output path

The report shows pages added/removed, glossary term changes, synonym changes, and section heading changes, with a new heading per changed page.

## XML validation

`scripts\validate-xml.py` checks the XML source files for structural problems before building:

- `py -3.14 scripts\validate-xml.py` — validates all editions in `xml-source/`
- `py -3.14 scripts\validate-xml.py xml-source\edition3` — validate a single edition

The validator catches:

<br>• `<glossentry>` elements placed directly in `<glossary>` without a `<glossdiv>` wrapper — these are **silently dropped** by the renderers
<br>• `<glossdiv>` elements missing a `<title>` — renders incorrectly
<br>• Non-glossdiv content placed directly in `<glossary>` — silently dropped
<br>• `<glossentry>` elements missing `<glossterm>` or `<glossdef>`
<br>• `<section>` or `<glossdiv>` inside `<listitem>` — silently dropped
<br>• XML syntax errors with file and line number

The web and PDF build scripts run validation automatically before rendering. Warnings are also emitted at render time for unrecognised elements that would be silently dropped from the output.

## Source XML workflow

The XML source directories live under `xml-source/edition1`, `xml-source/edition2`, and `xml-source/edition3`. These are the canonical sources for the web and PDF builds.

The `build-xml.ps1` step converts the original versioned HTML (`version1/`, `version2/`, `version3/`) to XML in `generated/xml/`. This conversion is a one-off bootstrap — it brought the HTML content into XML. Once the XML is created and reviewed, that output should be copied to `xml-source/`:

    Copy-Item generated\xml\editionN xml-source\editionN -Recurse

After that, any fixes, additions, or changes to the framework text should be made directly in `xml-source/editionN/` — that directory is now the editorial source for future versions. If the XML bootstrap is ever re-run from HTML, the new output in `generated/xml/` must be copied over to `xml-source/` before running `build-web.ps1` and `build-pdf.ps1`.

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
| `orderedlist` | Ordered list (`numeration="arabic"`, `numeration="loweralpha"`, or `numeration="lowerroman"`) |
| `itemizedlist` | Unordered list |
| `listitem` | List item |
| `question` | FAQ question block, including nested list content where needed |
| `answer` | FAQ answer block |
| `emphasis` | Bold, italic, underline, or other inline emphasis |
| `literal` | Literal or code-style inline text |
| `link` | Cross-reference or external link |
| `nolink` | Inline wrapper that suppresses automatic cross-reference and glossary autolinking |
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

## Layout roles and modifiers

Both renderers (XML→HTML and XML→LaTeX/PDF) are driven by tags plus generic
`role` modifiers rather than page-specific code. The `role` vocabulary is the
single source of truth for layout decisions:

| Element | `role` value | Effect |
| --- | --- | --- |
| `emphasis` | `bold` / `italic` / `underline` | Inline emphasis style |
| `orderedlist` | `glossary-style` | Numbered rows aligned like glossary entries |
| `itemizedlist` / `orderedlist` | `compact` | Tight list spacing |
| `note` | `technical-comment` | Renders as a "Technical comment" (otherwise "Further explanation") |
| `informaltable` | `leadhead-codes` | Compact monospace lead-head code table |
| `informaltable` | `leadhead-code-pair` | Two side-by-side code tables |
| `informaltable` | `amended-method-titles` / `amended-method-titles-summary` | Borderless 3-column amendment tables |
| `informaltable` | `related-material` | Appendix G related-material 3-column layout |

FAQ/consultation question and answer text uses the `question` / `answer`
elements; answers render in a grey, page-breakable box that starts at the text
left margin. The older `mrf:separator="hr"` modifier on `answer` is deprecated:
horizontal rules around notes are now emitted automatically by the renderers as
a single rule before and after each contiguous run of `example`/`note` blocks.

In the source HTML, ordered-list markers are typically `1.` / `1)` for numeric lists, `a)` for lower-alpha lists, and `i)` / `(i)` for roman lists.
