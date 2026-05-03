param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$InputRoot = "generated\xml",
    [string]$HtmlOutputRoot = "generated\html",
    [string]$TexOutputRoot = "generated\tex",
    [string]$SwitchVersionHref = "../../../index.html"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$resolvedRepoRoot = (Resolve-Path $RepoRoot).Path
Set-Location $resolvedRepoRoot

$resolvedInputRoot = Join-Path $resolvedRepoRoot $InputRoot
if (-not (Test-Path $resolvedInputRoot -PathType Container)) {
    throw "Input XML root does not exist: $resolvedInputRoot"
}

$versionDirs = Get-ChildItem -Path $resolvedInputRoot -Directory | Sort-Object Name
foreach ($versionDir in $versionDirs) {
    $versionName = $versionDir.Name
    $assetPrefix = "../../../$versionName"
    $htmlOutputDir = Join-Path $resolvedRepoRoot (Join-Path $HtmlOutputRoot $versionName)
    $texOutputDir = Join-Path $resolvedRepoRoot (Join-Path $TexOutputRoot $versionName)

    New-Item -ItemType Directory -Force -Path $htmlOutputDir | Out-Null
    New-Item -ItemType Directory -Force -Path $texOutputDir | Out-Null

    $xmlFiles = Get-ChildItem -Path $versionDir.FullName -Filter *.xml | Sort-Object Name
    foreach ($xmlFile in $xmlFiles) {
        $htmlPath = Join-Path $htmlOutputDir ($xmlFile.BaseName + ".html")
        $texPath = Join-Path $texOutputDir ($xmlFile.BaseName + ".tex")

        Write-Host "Rendering $($xmlFile.FullName) -> HTML"
        python scripts\convert_docbook_to_html.py `
            $xmlFile.FullName `
            $htmlPath `
            --asset-prefix $assetPrefix `
            --switch-version-href $SwitchVersionHref

        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        Write-Host "Rendering $($xmlFile.FullName) -> LaTeX"
        python scripts\convert_docbook_to_latex.py `
            $xmlFile.FullName `
            $texPath `
            --asset-root $assetPrefix

        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}
