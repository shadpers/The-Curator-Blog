@echo off
setlocal

:: Codificação UTF-8
chcp 65001 >nul

set "LOG_FILE=%~dp0debug_log_v3.txt"
echo DEBUG: Iniciando script em %DATE% %TIME% > "%LOG_FILE%"

if "%~1"=="" (
    echo Arraste a Referencia e o Alvo para este .bat
    echo Arraste a Referencia e o Alvo para este .bat >> "%LOG_FILE%"
    pause
    exit /b 1
)
if "%~2"=="" (
    echo Arraste o Alvo tambem
    echo Arraste o Alvo tambem >> "%LOG_FILE%"
    pause
    exit /b 1
)

set "REF_ORIG=%~1"
set "ALV_ORIG=%~2"
set REF_ORIG=%REF_ORIG:"=%
set ALV_ORIG=%ALV_ORIG:"=%

echo Referencia: "%REF_ORIG%"
echo Referencia: "%REF_ORIG%" >> "%LOG_FILE%"
echo Alvo:       "%ALV_ORIG%"
echo Alvo:       "%ALV_ORIG%" >> "%LOG_FILE%"

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0calculate_subtitle_sync_v3.py"

echo Rodando Python...
echo Rodando Python... >> "%LOG_FILE%"
"%PYTHON_EXE%" -u "%SCRIPT_PY%" "%REF_ORIG%" "%ALV_ORIG%" 2>> "%LOG_FILE%"

if %ERRORLEVEL% NEQ 0 (
    echo Python retornou erro. Veja %LOG_FILE%
    echo Python retornou erro. Veja %LOG_FILE% >> "%LOG_FILE%"
    type "%LOG_FILE%"
    pause
    exit /b %ERRORLEVEL%
) else (
    echo Concluido com sucesso. Veja log em %LOG_FILE%
    echo Concluido com sucesso. Veja log em %LOG_FILE% >> "%LOG_FILE%"
)
pause
endlocal
