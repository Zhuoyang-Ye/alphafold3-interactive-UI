@echo off
setlocal
title AlphaFold 3 Explorer - Desktop Studio
cls

echo =====================================================================
echo                ALPHAFOLD 3  INTERACTION STUDIO
echo               Local Desktop Explorer for Windows
echo =====================================================================
echo.
echo [1/2] Checking launch environment...

cd /d "%~dp0"

set PY_CMD=

:: 1. Check for uv
where uv >nul 2>nul
if %errorlevel% equ 0 (
    uv run python -c "import sys; sys.exit(0)" >nul 2>nul
    if %errorlevel% equ 0 (
        set PY_CMD=uv run python
        goto LAUNCH_PY
    )
)

:: 2. Check for standard python
where python >nul 2>nul
if %errorlevel% equ 0 (
    python -c "import sys; sys.exit(0)" >nul 2>nul
    if %errorlevel% equ 0 (
        set PY_CMD=python
        goto LAUNCH_PY
    )
)

:: 3. Check for py launcher
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 -c "import sys; sys.exit(0)" >nul 2>nul
    if %errorlevel% equ 0 (
        set PY_CMD=py -3
        goto LAUNCH_PY
    )
)

:: 4. If Python is not installed, use built-in Windows PowerShell launcher
echo [OK] Launching via built-in Windows engine...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_explorer_windows.ps1"
goto EXIT

:LAUNCH_PY
echo [OK] Found Python runtime (%PY_CMD%).
echo [2/2] Launching AlphaFold 3 Explorer...
%PY_CMD% "%~dp0run_explorer_windows.py"

:EXIT
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with code %errorlevel%.
    pause
)
