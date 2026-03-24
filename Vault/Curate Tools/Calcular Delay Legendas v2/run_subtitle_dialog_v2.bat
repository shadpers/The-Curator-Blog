@echo off
setlocal

:: Define codificação UTF-8 para o console
chcp 65001 >nul

set "LOG_FILE=%~dp0debug_log.txt"
echo DEBUG: Iniciando script em %DATE% %TIME% > "%LOG_FILE%"

if "%~1"=="" (
    echo Arraste o BD e o WEB para este .bat
    echo Arraste o BD e o WEB para este .bat >> "%LOG_FILE%"
    pause
    exit /b 1
)
if "%~2"=="" (
    echo Arraste o WEB tambem
 ECHO Arraste o WEB tambem >> "%LOG_FILE%"
    pause
    exit /b 1
)

rem Remove aspas extras
set "BD_ORIG=%~1"
set "WEB_ORIG=%~2"
set BD_ORIG=%BD_ORIG:"=%
set WEB_ORIG=%WEB_ORIG:"=%

echo BD original: "%BD_ORIG%"
echo BD original: "%BD_ORIG%" >> "%LOG_FILE%"
echo WEB original: "%WEB_ORIG%"
echo WEB original: "%WEB_ORIG%" >> "%LOG_FILE%"

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0calculate_subtitle_dialog_v2.py"

echo Rodando Python...
echo Rodando Python... >> "%LOG_FILE%"
:: Usa -u para desativar buffering e executa sem redirecionar stdout
"%PYTHON_EXE%" -u "%SCRIPT_PY%" "%BD_ORIG%" "%WEB_ORIG%" 2>> "%LOG_FILE%"

if %ERRORLEVEL% NEQ 0 (
    echo Python retornou erro. Veja %LOG_FILE%
    echo Python retornou erro. Veja %LOG_FILE% >> "%LOG_FILE%"
    type "%LOG_FILE%"
    pause
    exit /b %ERRORLEVEL%
) else (
    echo Python executado com sucesso. Veja log em %LOG_FILE%
    echo Python executado com sucesso. Veja log em %LOG_FILE% >> "%LOG_FILE%"
)
pause
endlocal