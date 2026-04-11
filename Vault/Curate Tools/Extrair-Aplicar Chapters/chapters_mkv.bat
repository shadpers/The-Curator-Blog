@echo off
set PYTHON_PATH=python
set SCRIPT_PATH=chapters_mkv.py

if "%~1"=="" (
    echo.
    echo  Uso:
    echo    Extracao:  arraste um ou mais MKVs para este .bat
    echo    Aplicacao: arraste MKVs + arquivo .chapters.txt para este .bat
    echo.
    pause
    exit
)

"%PYTHON_PATH%" "%SCRIPT_PATH%" %*
pause
