<#
.SYNOPSIS
    Bootstrap DocBook XML from the original version HTML source.
    This is a one-off conversion — after reviewing, copy output to xml-source/.
.PARAMETER Edition
    Edition to build (e.g. edition2). Omit to build all editions.
#>
param(
    [string]$Edition = ""
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $ScriptDir "..")

if ($Edition) {
    $versions = @($Edition)
} else {
    $xmlRoot = "generated\xml"
    $metaXml = "xml"
    $versions = @()
    if (Test-Path $xmlRoot) {
        Get-ChildItem "$xmlRoot\edition*" | ForEach-Object { $versions += "edition$($_.Name -replace 'edition','')" }
    }
    if (-not $versions) {
        Get-ChildItem "version*" -Directory | ForEach-Object { $versions += $_.Name }
    }
}

if (-not $versions) {
    Write-Host "No editions found"
    exit 1
}

Write-Host "Building XML for: $($versions -join ', ')"
foreach ($v in $versions) {
    if ($v -match '^edition(\d+)$') {
        $htmlDir = "version$($Matches[1])"
        $outDir = "generated\xml\edition$($Matches[1])"
    } elseif ($v -match '^version(\d+)$') {
        $htmlDir = "version$($Matches[1])"
        $outDir = "generated\xml\edition$($Matches[1])"
    } else {
        Write-Host "  [SKIP] Unknown version: $v"
        continue
    }
    if (-not (Test-Path $htmlDir)) {
        Write-Host "  [SKIP] Source not found: $htmlDir"
        continue
    }
    Write-Host "  $htmlDir -> $outDir"
    py -3.14 scripts\convert_html_tree_to_xml.py $htmlDir $outDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAILED]"
        exit 1
    }
}

Write-Host "XML build complete"
