@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

:: Caminho fixo do Python
set PYTHON_EXE="C:\Python313\python.exe"

:: Caminho fixo do script
set SCRIPT_PY="compactar.py"

%PYTHON_EXE% %SCRIPT_PY%
pause
