param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string[]]$SourceDirs = @("version1", "version2"),
    [string]$OutputRoot = "generated\xml",
    [string]$BaseUriRoot = "https://cccbr.github.io/method_ringing_framework"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedRepoRoot = (Resolve-Path $RepoRoot).Path
Set-Location $resolvedRepoRoot

foreach ($sourceDir in $SourceDirs) {
    $sourcePath = Join-Path $resolvedRepoRoot $sourceDir
    if (-not (Test-Path $sourcePath -PathType Container)) {
        Write-Warning "Skipping missing source directory: $sourceDir"
        continue
    }

    $leafName = Split-Path $sourcePath -Leaf
    $outputPath = Join-Path $resolvedRepoRoot (Join-Path $OutputRoot $leafName)
    $baseUri = ($BaseUriRoot.TrimEnd("/") + "/" + $leafName)

    Write-Host "Converting $leafName HTML -> DocBook XML"
    python scripts\convert_html_to_docbook.py `
        --input $sourcePath `
        --output $outputPath `
        --base-uri $baseUri

    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
