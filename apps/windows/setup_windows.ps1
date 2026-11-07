# AlphaFold 3 Explorer - Windows Automated Setup Script
# Installs uv, configures Python 3.12, downloads dependencies, and creates Desktop shortcut.

Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host "           AlphaFold 3 Explorer - Windows Environment Setup" -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Cyan
Write-Host ""

$ErrorActionPreference = "Stop"

# 1. Check/Install uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[1/4] Installing 'uv' fast package manager..." -ForegroundColor Yellow
    try {
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path","User") + ";" + [System.Environment]::GetEnvironmentVariable("Path","Machine")
    } catch {
        Write-Host "Failed to automatically install uv. Trying winget..." -ForegroundColor Yellow
        winget install --id=astral-sh.uv -e --accept-source-agreements --accept-package-agreements
    }
} else {
    Write-Host "[1/4] 'uv' is already installed." -ForegroundColor Green
}

# 2. Sync dependencies
$RepoRoot = Resolve-Path "$PSScriptRoot\..\.."
Set-Location $RepoRoot

Write-Host "[2/4] Setting up Python 3.12 and dependencies via uv sync..." -ForegroundColor Yellow
& uv sync

# 3. Build chemistry dictionary
Write-Host "[3/4] Preparing chemistry components dictionary (build_data)..." -ForegroundColor Yellow
& uv run build_data

# 4. Create Desktop Shortcut
Write-Host "[4/4] Creating Desktop Shortcut..." -ForegroundColor Yellow
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$ShortcutPath = Join-Path $DesktopPath "AlphaFold 3 Explorer.lnk"
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = (Join-Path $PSScriptRoot "AlphaFold3_Explorer.bat")
$Shortcut.WorkingDirectory = $PSScriptRoot
$Shortcut.Description = "AlphaFold 3 Interactive Studio"
$Shortcut.Save()

Write-Host ""
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host "Setup Complete! Shortcut created on your Desktop." -ForegroundColor Green
Write-Host "Double-click 'AlphaFold 3 Explorer' on your Desktop to start." -ForegroundColor Green
Write-Host "=====================================================================" -ForegroundColor Green
Write-Host ""
