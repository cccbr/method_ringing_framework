param(
    [Parameter(Mandatory=$true)][string]$InputDir,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [Parameter(Mandatory=$true)][string]$BaseUri,
    [string]$VersionId = 'v2',
    [string]$Status = 'definitive'
)

function Ensure-Dir($p){ if(-not (Test-Path $p)){ New-Item -ItemType Directory -Path $p | Out-Null } }

Ensure-Dir $OutputDir
Ensure-Dir (Join-Path $OutputDir 'assets')

Get-ChildItem -Path $InputDir -Filter *.html | ForEach-Object {
    $inPath = $_.FullName
    $html = Get-Content -Path $inPath -Raw -Encoding UTF8
    if($html -match '<title>(.*?)</title>'){ $title = $matches[1].Trim() } else { $title = [IO.Path]::GetFileNameWithoutExtension($_.Name) }
    if($html -match '(?s)<body.*?>(.*?)</body>'){ $body = $matches[1] } else { $body = $html }
    # simple conversions
    $body = $body -replace "\r?\n", ' '
    # lists
    $body = $body -replace '<li[^>]*>(.*?)</li>','<listitem><para>$1</para></listitem>'
    $body = $body -replace '<ul[^>]*>','<itemizedlist>'
    $body = $body -replace '</ul>','</itemizedlist>'
    $body = $body -replace '<ol[^>]*>','<orderedlist>'
    $body = $body -replace '</ol>','</orderedlist>'
    # paragraphs
    $body = $body -replace '<p[^>]*>(.*?)</p>','<para>$1</para>'
    # headings to titles (non-nested)
    $body = $body -replace '<h[1-6][^>]*>(.*?)</h[1-6]>','<title>$1</title>'
    # code blocks
    $body = $body -replace '<pre[^>]*>(.*?)</pre>','<programlisting>$1</programlisting>'
    $body = $body -replace '<code[^>]*>(.*?)</code>','<programlisting>$1</programlisting>'
    # images - copy local images into assets
    $body = [Regex]::Replace($body,'<img[^>]*src=["\'']([^"\'']+)["\''][^>]*>',{ param($m)
        $src = $m.Groups[1].Value
        if($src -notmatch '^https?://'){
            $srcPath = Join-Path (Get-Location) ($src -replace '/','\\')
            if(Test-Path $srcPath){ Copy-Item -Path $srcPath -Destination (Join-Path $OutputDir 'assets') -Force }
            $fileref = Join-Path 'assets' (Split-Path $srcPath -Leaf)
        } else { $fileref = $src }
        return "<mediaobject><imageobject><imagedata fileref='$fileref'/></imageobject></mediaobject>"
    })
    # definitions: convert <dfn> to glossentry with termmeta
    $body = [Regex]::Replace($body,'<dfn(?:[^>]*)>(.*?)</dfn>',{
        param($m)
        $term = $m.Groups[1].Value.Trim()
        $id = ([IO.Path]::GetFileNameWithoutExtension($_.Name) + '-' + ($term -replace '\\s+','-'))
        return "<glossentry><glossterm>$term</glossterm><termmeta xml:id='$id'><authority>CCCBR</authority><status>$Status</status><version-id>$VersionId</version-id><canonical-uri>$($BaseUri.TrimEnd('/'))/$(Split-Path $_ -Leaf)</canonical-uri><provenance>$($_.FullName)</provenance></termmeta></glossentry>"
    })

    $outFile = Join-Path $OutputDir ((Split-Path $_ -Leaf) -replace '\.html$','.xml')
    $xml = "<?xml version='1.0' encoding='utf-8'?>`n<article>`n  <info><title>$([System.Security.SecurityElement]::Escape($title))</title><othermeta>source=$inPath</othermeta></info>`n  <section>$body</section>`n</article>`n"
    Set-Content -Path $outFile -Value $xml -Encoding UTF8
    Write-Host "Wrote" $outFile
}
