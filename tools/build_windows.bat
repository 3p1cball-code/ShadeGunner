@echo off
setlocal
cd /d "%~dp0.."
title ShadeGunner - Windows-Build (PyInstaller)

set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
    echo Python 3 nicht gefunden. Erst install.bat ausfuehren.
    pause
    exit /b 1
)

echo Installiere Build-Werkzeuge ...
%PY% -m pip install --upgrade pip pyinstaller
if errorlevel 1 ( pause & exit /b 1 )

echo Baue die .exe (kann 1-2 Minuten dauern) ...
%PY% -m PyInstaller --noconfirm --clean shadegunner.spec
if errorlevel 1 ( pause & exit /b 1 )

echo.
echo   Fertig:  dist\ShadeGunner\ShadeGunner.exe
echo   Diesen kompletten Ordner dist\ShadeGunner\ an Steam ausliefern.
echo.
pause
