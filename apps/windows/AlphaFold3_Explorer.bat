@echo off
title AlphaFold 3 Explorer - Interaction Studio
color 0A
cls

echo =====================================================================
echo                ALPHAFOLD 3  INTERACTION STUDIO
echo               Local Desktop Explorer for Windows
echo =====================================================================
echo.
echo [1/3] Checking environment...

cd /d "%~dp0\..\.."

where uv >nul 2>nul
if %errorlevel% equ 0 (
    echo [OK] Found uv package manager.
    set PY_CMD=uv run python
    goto START_SERVER
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    echo [OK] Found Python.
    set PY_CMD=python
    goto START_SERVER
)

echo [!] Python or uv was not found on your system.
echo     Starting automated setup for Windows...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_windows.ps1"
if %errorlevel% neq 0 (
    echo [ERROR] Setup failed. Please check your internet connection.
    pause
    exit /b 1
)
set PY_CMD=uv run python

:START_SERVER
echo.
echo [2/3] Starting local AlphaFold 3 Explorer server...
echo       Address: http://127.0.0.1:8765
echo.

start "" /B %PY_CMD% -m explorer.app

echo [3/3] Opening application window...
timeout /t 2 /nobreak >nul

where msedge >nul 2>nul
if %errorlevel% equ 0 (
    start msedge --app=http://127.0.0.1:8765 --window-size=1360,900
    goto RUNNING
)

where chrome >nul 2>nul
if %errorlevel% equ 0 (
    start chrome --app=http://127.0.0.1:8765 --window-size=1360,900
    goto RUNNING
)

start http://127.0.0.1:8765

:RUNNING
echo.
echo =====================================================================
echo  AlphaFold 3 Explorer is running!
echo  Keep this window open while using the application.
echo  To quit: Close this window or press Ctrl+C.
echo =====================================================================
echo.

%PY_CMD% -m explorer.app
