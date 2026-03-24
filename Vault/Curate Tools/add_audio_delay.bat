@echo off
setlocal

:: Define codificação UTF-8 para o console
chcp 65001 >nul

set "LOG_FILE=%~dp0convert_log.txt"
echo DEBUG: Iniciando script em %DATE% %TIME% > "%LOG_FILE%"

if "%~1"=="" (
    echo Arraste o arquivo de vídeo para este .bat
    echo Arraste o arquivo de vídeo para este .bat >> "%LOG_FILE%"
    pause
    exit /b 1
)

rem Remove aspas extras
set "VIDEO_FILE=%~1"
set VIDEO_FILE=%VIDEO_FILE:"=%

echo Arquivo de vídeo: "%VIDEO_FILE%"
echo Arquivo de vídeo: "%VIDEO_FILE%" >> "%LOG_FILE%"

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0add_audio_delay.py"

echo Rodando Python...
echo Rodando Python... >> "%LOG_FILE%"
:: Usa -u para desativar buffering e executa sem redirecionar stdout
"%PYTHON_EXE%" -u "%SCRIPT_PY%" "%VIDEO_FILE%" 2>> "%LOG_FILE%"

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