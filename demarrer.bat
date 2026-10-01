@echo off
rem Atlas du tissu productif agricole du Togo - lanceur Windows (double-clic).
title Atlas agricole du Togo
chcp 65001 >nul
cd /d "%~dp0"

set "PY="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PY=py -3"
if not defined PY (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>nul && set "PY=python"
)

if not defined PY (
    echo.
    echo Python 3.10 ou plus recent est introuvable.
    echo Installer Python depuis https://www.python.org/downloads/
    echo en cochant "Add python.exe to PATH", puis relancer ce fichier.
    echo.
    pause
    exit /b 1
)

%PY% lancer.py %*
if errorlevel 1 (
    echo.
    pause
)
