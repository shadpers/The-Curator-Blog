@echo off
setlocal

set "LOG_FILE=%~dp0convert_fps_log.txt"
echo DEBUG: Iniciando script em %DATE% %TIME% > "%LOG_FILE%"

if "%~1"=="" (
    echo Arraste o arquivo de video para este .bat
    echo Arraste o arquivo de video para este .bat >> "%LOG_FILE%"
    pause
    exit /b 1
)

set "VIDEO_FILE=%~1"

echo Arquivo de video: "%VIDEO_FILE%"
echo Arquivo de video: "%VIDEO_FILE%" >> "%LOG_FILE%"

if not exist "%VIDEO_FILE%" (
    echo ERRO: Arquivo nao encontrado: "%VIDEO_FILE%"
    echo ERRO: Arquivo nao encontrado: "%VIDEO_FILE%" >> "%LOG_FILE%"
    pause
    exit /b 1
)

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0convert_audio_fps.py"

if not exist "%PYTHON_EXE%" (
    echo ERRO: Python nao encontrado em: "%PYTHON_EXE%"
    echo ERRO: Python nao encontrado em: "%PYTHON_EXE%" >> "%LOG_FILE%"
    pause
    exit /b 1
)

if not exist "%SCRIPT_PY%" (
    echo ERRO: Script Python nao encontrado em: "%SCRIPT_PY%"
    echo ERRO: Script Python nao encontrado em: "%SCRIPT_PY%" >> "%LOG_FILE%"
    pause
    exit /b 1
)

echo Rodando Python...
echo Rodando Python... >> "%LOG_FILE%"

"%PYTHON_EXE%" -u "%SCRIPT_PY%" "%VIDEO_FILE%" 2>> "%LOG_FILE%"

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Python retornou erro. Veja %LOG_FILE%
    echo Python retornou erro. >> "%LOG_FILE%"
    echo.
    echo Conteudo do log:
    type "%LOG_FILE%"
    pause
    exit /b %ERRORLEVEL%
) else (
    echo.
    echo Python executado com sucesso!
    echo Python executado com sucesso! >> "%LOG_FILE%"
)
pause
endlocal