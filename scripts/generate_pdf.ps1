#!/usr/bin/env pwsh
param(
    [string]$Version = "all",
    [string]$OutputDir = "generated/pdf",
    [string]$SourceXmlDir = "generated/xml",
    [string]$TexDir = "generated/tex",
    [switch]$NoClean = $false
)

$ErrorActionPreference = "Stop"

# Determine which versions to process
$versions = @()
if ($Version -eq "all") {
    $versions = @("version1", "version2")
} else {
    $versions = @($Version)
}

Write-Host "Setting up output directories..."
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}
foreach ($v in $versions) {
    $versionPdfDir = Join-Path $OutputDir $v
    if (-not (Test-Path $versionPdfDir)) {
        New-Item -ItemType Directory -Path $versionPdfDir -Force | Out-Null
    }
}

Write-Host "Checking for pdflatex..."
if (-not (Get-Command pdflatex -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: pdflatex not found"
    exit 1
}
Write-Host "[OK] pdflatex found"

Write-Host ""
Write-Host "Verifying XML files..."
foreach ($v in $versions) {
    $xmlDir = Join-Path $SourceXmlDir $v
    if (-not (Test-Path $xmlDir)) {
        Write-Host "ERROR: XML directory not found: $xmlDir"
        exit 1
    }
    $xmlCount = (Get-ChildItem $xmlDir -Filter *.xml | Measure-Object).Count
    Write-Host "  ${v}: $xmlCount XML files"
}

Write-Host ""
Write-Host "Rendering TeX files..."
foreach ($v in $versions) {
    Write-Host "Processing $v..."
    
    $versionXmlDir = Join-Path $SourceXmlDir $v
    $versionTexDir = Join-Path $TexDir $v
    
    if (-not (Test-Path $versionTexDir)) {
        New-Item -ItemType Directory -Path $versionTexDir -Force | Out-Null
    }
    
    Get-ChildItem $versionXmlDir -Filter *.xml | ForEach-Object {
        $xmlFile = $_.FullName
        $texFile = Join-Path $versionTexDir "$($_.BaseName).tex"
        
        Write-Host "  Converting $($_.Name)..."
        python scripts/convert_docbook_to_latex.py $xmlFile $texFile
        
        if ($LASTEXITCODE -ne 0) {
            Write-Host "ERROR: Failed to convert $($_.Name)"
            exit 1
        }
    }
    
    Write-Host "  Generating master TeX..."
    $masterTexPath = Join-Path $versionTexDir "framework-$v.tex"
    python scripts/generate_master_latex.py $v $masterTexPath --content-dir $versionTexDir --xml-dir $versionXmlDir
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to generate master TeX"
        exit 1
    }
}

Write-Host ""
Write-Host "Compiling PDFs..."
foreach ($v in $versions) {
    Write-Host "Compiling $v..."
    
    $versionTexDir = Join-Path $TexDir $v
    $masterTexPath = Join-Path $versionTexDir "framework-$v.tex"
    $versionPdfDir = Join-Path $OutputDir $v
    
    if (-not (Test-Path $masterTexPath)) {
        Write-Host "ERROR: Master TeX not found: $masterTexPath"
        exit 1
    }
    
    $auxDir = Join-Path $versionTexDir ".build-aux"
    if (-not (Test-Path $auxDir)) {
        New-Item -ItemType Directory -Path $auxDir -Force | Out-Null
    }
    
    Write-Host "  Preparing build directory..."
    $absVersionTexDir = (Resolve-Path $versionTexDir).Path
    $absAuxDir = (Resolve-Path $auxDir).Path
    
    # Copy master file
    Copy-Item (Join-Path $absVersionTexDir "framework-$v.tex") (Join-Path $absAuxDir "framework-$v.tex") -Force
    # Copy preamble
    Copy-Item (Resolve-Path "scripts/templates/docbook-preamble.tex").Path (Join-Path $absAuxDir "docbook-preamble.tex") -Force
    
    # Copy all content TeX files using a for loop
    foreach ($texFile in (Get-ChildItem "$absVersionTexDir/*.tex")) {
        if ($texFile.Name -notmatch "^framework-") {
            Copy-Item $texFile.FullName (Join-Path $absAuxDir $texFile.Name) -Force
        }
    }
    
    # Update the include path in the copied master file
    $masterTexCopy = Join-Path $absAuxDir "framework-$v.tex"
    $masterContent = Get-Content $masterTexCopy -Raw
    $masterContent = $masterContent -replace '\\input\{[^}]*docbook-preamble\.tex\}', '\input{docbook-preamble.tex}'
    Set-Content $masterTexCopy $masterContent -Encoding UTF8
    
    Push-Location $auxDir
    try {
        Write-Host "  First pass..."
        $oldEap = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & pdflatex -interaction=nonstopmode "framework-$v.tex" *>$null
        $ErrorActionPreference = $oldEap
        
        Write-Host "  Second pass..."
        $ErrorActionPreference = "Continue"
        & pdflatex -interaction=nonstopmode "framework-$v.tex" *>$null
        $ErrorActionPreference = $oldEap
    } finally {
        Pop-Location
    }
    
    $pdfSource = Join-Path (Join-Path $versionTexDir ".build-aux") "framework-$v.pdf"
    $pdfDest = Join-Path $versionPdfDir "framework-$v.pdf"
    
    if (Test-Path $pdfSource) {
        Copy-Item $pdfSource $pdfDest -Force
        Write-Host "  [OK] PDF created: $pdfDest"
    } else {
        Write-Host "ERROR: PDF not created"
        exit 1
    }
}

# Cleanup
if (-not $NoClean) {
    Write-Host ""
    Write-Host "Cleaning up..."
    foreach ($v in $versions) {
        $versionTexDir = Join-Path $TexDir $v
        $auxDir = Join-Path $versionTexDir ".build-aux"
        if (Test-Path $auxDir) {
            Remove-Item $auxDir -Recurse -Force
        }
    }
}

Write-Host ""
Write-Host "====================================================="
Write-Host "PDF Generation Complete!"
Write-Host "====================================================="
foreach ($v in $versions) {
    $pdfPath = Join-Path (Join-Path $OutputDir $v) "framework-$v.pdf"
    if (Test-Path $pdfPath) {
        Write-Host "[OK] $pdfPath"
    }
}
