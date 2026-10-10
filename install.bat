@echo off
setlocal
cd /d "%~dp0"
title ShadeGunner - Abhaengigkeiten installieren

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo.
    echo   Python 3 wurde nicht gefunden.
    echo   Bitte von https://www.python.org/downloads/ installieren
    echo   und beim Setup "Add python.exe to PATH" ankreuzen.
    echo.
    pause
    exit /b 1
)

echo Installiere mit "%PY%" ...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo   Installation fehlgeschlagen.
    pause
    exit /b 1
)
echo.
echo   Fertig. Spiel starten:
echo     tools\run.bat      (oder: %PY% -m shadegunner)
echo.
pause
