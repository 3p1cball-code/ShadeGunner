@echo off
setlocal
cd /d "%~dp0.."
set "PY="
where py >nul 2>nul && set "PY=py"
if not defined PY set "PY=python"
%PY% -m shadegunner %*
