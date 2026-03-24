@echo off
setlocal
chcp 65001 >nul

if "%~1"=="" (
    echo Arraste o arquivo de video para este .bat
    pause
    exit /b 1
)

set "VIDEO_FILE=%~1"
set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0convert_audio_direct.py"

"%PYTHON_EXE%" "%SCRIPT_PY%" "%VIDEO_FILE%"

pause
endlocal