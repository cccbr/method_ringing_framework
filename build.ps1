#!/usr/bin/env pwsh
<#
.SYNOPSIS
Build framework documentation: HTML → XML → HTML/LaTeX/PDF

.DESCRIPTION
Master build orchestrator. Calls scripts/build.py which handles all build phases.

.PARAMETER Version
Version(s) to build (e.g., version1, version2). Defaults to all versions.

.PARAMETER XmlOnly
Only convert HTML to XML, skip outputs.

.PARAMETER HtmlOnly
Skip PDF generation (only HTML).

.PARAMETER PdfOnly
Only compile PDFs (assumes TeX files exist).

.PARAMETER NoCleanup
Keep build artifacts.

.EXAMPLE
./build.ps1                              # Full build (all versions)
./build.ps1 -Version version2            # Build only version2
./build.ps1 -Version version2 -HtmlOnly  # Only HTML, no PDF
./build.ps1 -Version version2 -PdfOnly   # Only compile PDF
#>

param(
    [string[]]$Version = @(),
    [switch]$XmlOnly = $false,
    [switch]$HtmlOnly = $false,
    [switch]$PdfOnly = $false,
    [switch]$NoCleanup = $false
)

# Call the Python build script
$args = @("scripts/build.py")

# Add version arguments
foreach ($v in $Version) {
    $args += "--version", $v
}

# Add flags
if ($XmlOnly) { $args += "--xml-only" }
if ($HtmlOnly) { $args += "--html-only" }
if ($PdfOnly) { $args += "--pdf-only" }
if ($NoCleanup) { $args += "--no-cleanup" }

# Run the build
python $args
exit $LASTEXITCODE
