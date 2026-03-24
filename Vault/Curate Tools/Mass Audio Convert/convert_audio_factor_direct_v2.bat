@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

if "%~1"=="" (
    echo Arraste um ou mais arquivos de video para este .bat
    pause
    exit /b 1
)

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0convert_audio_direct_v2.py"

set "ARGS="
:loop
if "%~1"=="" goto run
set "ARGS=!ARGS! "%~1""
shift
goto loop

:run
"%PYTHON_EXE%" "%SCRIPT_PY%" %ARGS%

pause
endlocal