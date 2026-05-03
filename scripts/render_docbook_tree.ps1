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
    $pdfOutputDir = Join-Path $resolvedRepoRoot (Join-Path "generated\pdf" $versionName)

    New-Item -ItemType Directory -Force -Path $htmlOutputDir | Out-Null
    New-Item -ItemType Directory -Force -Path $texOutputDir | Out-Null
    New-Item -ItemType Directory -Force -Path $pdfOutputDir | Out-Null

    $xmlFiles = Get-ChildItem -Path $versionDir.FullName -Filter *.xml | Sort-Object Name
    $firstFile = $null
    $generatedTexFiles = @()

    foreach ($xmlFile in $xmlFiles) {
        $htmlPath = Join-Path $htmlOutputDir ($xmlFile.BaseName + ".html")
        $texPath = Join-Path $texOutputDir ($xmlFile.BaseName + ".tex")

        if ($firstFile -eq $null) {
            $firstFile = $xmlFile
        }

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

        $generatedTexFiles += $xmlFile.BaseName + ".tex"
    }

    # Extract metadata from XML files and generate master .tex
    if ($firstFile -ne $null) {
        Write-Host "Generating master LaTeX file for $versionName"
        $masterTexPath = Join-Path $texOutputDir "framework-$versionName.tex"

        python scripts\generate_master_latex.py `
            $versionName `
            $masterTexPath `
            --content-dir $texOutputDir `
            --xml-dir $versionDir.FullName

        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
}
