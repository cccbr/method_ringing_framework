#!/usr/bin/env pwsh
<#
.SYNOPSIS
Build framework documentation: HTML → XML → HTML/LaTeX/PDF

.DESCRIPTION
Master build orchestrator. Calls scripts/build.py which handles all build phases.

.PARAMETER Edition
Edition(s) to build (e.g., edition1, edition2). Legacy version ids are also accepted. Defaults to all editions.

.PARAMETER XmlOnly
Only convert HTML to XML, skip outputs.

.PARAMETER HtmlOnly
Skip PDF generation (only HTML).

.PARAMETER PdfOnly
Only compile PDFs (assumes TeX files exist).

.PARAMETER NoCleanup
Keep build artifacts.

.EXAMPLE
./build.ps1                              # Full build (all editions)
./build.ps1 -Edition edition2            # Build only edition2
./build.ps1 -Edition edition2 -HtmlOnly  # Only HTML, no PDF
./build.ps1 -Edition edition2 -PdfOnly   # Only compile PDF
#>

param(
    [Alias("Version")]
    [string[]]$Edition = @(),
    [switch]$XmlOnly = $false,
    [switch]$HtmlOnly = $false,
    [switch]$PdfOnly = $false,
    [switch]$NoCleanup = $false
)

# Call the Python build script
$args = @("scripts/build.py")

# Add edition arguments
foreach ($v in $Edition) {
    $args += "--edition", $v
}

# Add flags
if ($XmlOnly) { $args += "--xml-only" }
if ($HtmlOnly) { $args += "--html-only" }
if ($PdfOnly) { $args += "--pdf-only" }
if ($NoCleanup) { $args += "--no-cleanup" }

# Run the build with the repository's Python launcher rather than any PATH-shadowed python.exe
py -3.14 $args
exit $LASTEXITCODE
