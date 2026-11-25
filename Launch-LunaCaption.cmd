@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Please run Setup-Windows.ps1 first. See README.md for instructions.
    pause
    exit /b 1
)
set "LUNACAPTION_CACHE=%~dp0.cache\models"
".venv\Scripts\python.exe" -m lunacaption %*
if errorlevel 1 (
    echo.
    echo LunaCaption could not start. See the message above.
    pause
)
