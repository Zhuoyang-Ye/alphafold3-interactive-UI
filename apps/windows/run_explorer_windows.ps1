# AlphaFold 3 Explorer - Zero-Dependency Windows PowerShell Launcher
# Runs out-of-the-box on any Windows 10/11 system even without Python installed.

$ErrorActionPreference = "Continue"

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "        AlphaFold 3 Explorer - Desktop Studio for Windows" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$WebDir = Join-Path $PSScriptRoot "web"
if (-not (Test-Path $WebDir)) {
    $AltDir = (Resolve-Path "$PSScriptRoot\..\..\explorer\static" -ErrorAction SilentlyContinue)
    if ($AltDir) { $WebDir = $AltDir.Path }
}

if (-not (Test-Path $WebDir)) {
    Write-Host "[ERROR] Could not find static web assets directory: $WebDir" -ForegroundColor Red
    Pause
    exit 1
}

$Port = 8765
$listener = New-Object System.Net.HttpListener
$bound = $false

while (-not $bound -and $Port -lt 8790) {
    $prefix = "http://127.0.0.1:$Port/"
    $listener.Prefixes.Clear()
    $listener.Prefixes.Add($prefix)
    try {
        $listener.Start()
        $bound = $true
    } catch {
        $Port++
    }
}

if (-not $bound) {
    Write-Host "[ERROR] Could not bind to an open loopback port." -ForegroundColor Red
    Pause
    exit 1
}

$appUrl = "http://127.0.0.1:$Port/?mode=explorer"
Write-Host "[1/2] Local desktop studio listening at $appUrl" -ForegroundColor Green
Write-Host "[2/2] Opening desktop application window..." -ForegroundColor Yellow

# Launch browser in app window mode
$EdgeCandidates = @(
    "$env:ProgramFiles(x86)\Microsoft\Edge\Application\msedge.exe",
    "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
    "$env:LocalAppData\Microsoft\Edge\Application\msedge.exe"
)
$launched = $false
foreach ($exe in $EdgeCandidates) {
    if (Test-Path $exe) {
        Start-Process $exe -ArgumentList "--app=$appUrl", "--window-size=1360,900"
        $launched = $true
        break
    }
}

if (-not $launched) {
    $ChromeCandidates = @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "$env:ProgramFiles(x86)\Google\Chrome\Application\chrome.exe",
        "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
    )
    foreach ($exe in $ChromeCandidates) {
        if (Test-Path $exe) {
            Start-Process $exe -ArgumentList "--app=$appUrl", "--window-size=1360,900"
            $launched = $true
            break
        }
    }
}

if (-not $launched) {
    Start-Process $appUrl
}

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host " AlphaFold 3 Explorer is running!" -ForegroundColor Green
Write-Host " Keep this window open while using the application." -ForegroundColor Yellow
Write-Host " To quit: Close this window or press Ctrl+C." -ForegroundColor Yellow
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host ""

try {
    while ($listener.IsListening) {
        $context = $listener.GetContext()
        $request = $context.Request
        $response = $context.Response

        $relPath = $request.Url.LocalPath.TrimStart('/')
        if ([string]::IsNullOrEmpty($relPath)) { $relPath = "index.html" }
        $relPath = $relPath.Replace('/', [System.IO.Path]::DirectorySeparatorChar)
        $filePath = Join-Path $WebDir $relPath

        if (Test-Path $filePath -PathType Leaf) {
            $bytes = [System.IO.File]::ReadAllBytes($filePath)
            $ext = [System.IO.Path]::GetExtension($filePath).ToLower()
            $mime = switch ($ext) {
                ".html" { "text/html; charset=utf-8" }
                ".css"  { "text/css; charset=utf-8" }
                ".js"   { "application/javascript; charset=utf-8" }
                ".json" { "application/json; charset=utf-8" }
                ".cif"  { "chemical/x-mmcif" }
                ".pdb"  { "chemical/x-pdb" }
                ".png"  { "image/png" }
                ".svg"  { "image/svg+xml" }
                default { "application/octet-stream" }
            }
            $response.ContentType = $mime
            $response.ContentLength64 = $bytes.Length
            $response.Headers.Add("Cache-Control", "no-cache")
            $response.OutputStream.Write($bytes, 0, $bytes.Length)
        } else {
            $response.StatusCode = 404
        }
        $response.Close()
    }
} finally {
    $listener.Stop()
}
