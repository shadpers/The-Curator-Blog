@echo off
set PYTHON_PATH=python
set SCRIPT_PATH=cut_mkv.py

if "%~1"=="" (
    echo Arraste um ou mais arquivos MKV para este .bat
    pause
    exit
)

"%PYTHON_PATH%" "%SCRIPT_PATH%" %*
pause
