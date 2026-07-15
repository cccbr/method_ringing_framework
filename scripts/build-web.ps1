<#
.SYNOPSIS
    Render DocBook XML to website HTML for one or all editions.
    This step also updates cross-reference data used by the PDF build.
.PARAMETER Edition
    Edition to build (e.g. edition2). Omit to build all editions.
#>
param(
    [string]$Edition = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

$xmlRoot = "xml-source"

if ($Edition) {
    $versions = @($Edition)
} else {
    $versions = @()
    if (Test-Path $xmlRoot) {
        Get-ChildItem "$xmlRoot\edition*" | ForEach-Object { $versions += "edition$($_.Name -replace 'edition','')" }
    }
}

if (-not $versions) {
    Write-Host "No editions found"
    exit 1
}

Write-Host "Building web output for: $($versions -join ', ')"
Write-Host "`nValidating XML..."
& py -3.14 scripts\validate-xml.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "[WARNING] XML validation found issues - review before continuing"
}
$editionArgs = @()
foreach ($v in $versions) {
    $editionArgs += "--edition", $v
}
$allArgs = @("-3.14", "scripts\render_docbook_tree.py", "--html-only", "--source-xml", $xmlRoot) + $editionArgs
& py @allArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAILED]"
    exit 1
}

Write-Host "Web build complete"
