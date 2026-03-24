@echo off
setlocal EnableDelayedExpansion

set "LOG_FILE=%~dp0sync_audio_log.txt"

echo DEBUG: Iniciando script >> "%LOG_FILE%"
echo.
echo ========================================
echo   SINCRONIZAR AUDIO POR DURACAO
echo ========================================
echo.

if "%~1"=="" (
    echo ERRO: Nenhum arquivo informado
    echo.
    echo Uso: Arraste dois arquivos para este .bat
    echo   1. Arquivo de REFERENCIA
    echo   2. Arquivo ALVO
    echo.
    pause
    exit /b 1
)

if "%~2"=="" (
    echo ERRO: Faltou o segundo arquivo
    echo.
    echo Arraste DOIS arquivos juntos:
    echo   1. Arquivo de REFERENCIA
    echo   2. Arquivo ALVO
    echo.
    pause
    exit /b 1
)

:: Resolve .lnk para REFERENCIA
set "input_file=%~f1"
set "ext=%~x1"
if /I "!ext!"==".lnk" (
    set "escaped_path=!input_file:'=''!"
    for /f "usebackq delims=" %%R in (`powershell -NoProfile -Command "(New-Object -ComObject WScript.Shell).CreateShortcut('!escaped_path!').TargetPath"`) do set "REF_FILE=%%R"
) else (
    set "REF_FILE=!input_file!"
)

:: Resolve .lnk para ALVO
set "input_file=%~f2"
set "ext=%~x2"
if /I "!ext!"==".lnk" (
    set "escaped_path=!input_file:'=''!"
    for /f "usebackq delims=" %%R in (`powershell -NoProfile -Command "(New-Object -ComObject WScript.Shell).CreateShortcut('!escaped_path!').TargetPath"`) do set "TARGET_FILE=%%R"
) else (
    set "TARGET_FILE=!input_file!"
)

if not exist "!REF_FILE!" (
    echo ERRO: Arquivo de REFERENCIA nao encontrado
    echo !REF_FILE!
    pause
    exit /b 1
)

if not exist "!TARGET_FILE!" (
    echo ERRO: Arquivo ALVO nao encontrado
    echo !TARGET_FILE!
    pause
    exit /b 1
)

echo REFERENCIA: !REF_FILE!
echo ALVO......: !TARGET_FILE!
echo.
echo REFERENCIA: !REF_FILE! >> "%LOG_FILE%"
echo ALVO: !TARGET_FILE! >> "%LOG_FILE%"

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0sync_audio_duration.py"

if not exist "!PYTHON_EXE!" (
    echo ERRO: Python nao encontrado em !PYTHON_EXE!
    pause
    exit /b 1
)

if not exist "!SCRIPT_PY!" (
    echo ERRO: Script Python nao encontrado em !SCRIPT_PY!
    pause
    exit /b 1
)

echo Iniciando conversao...
echo.

"!PYTHON_EXE!" -u "!SCRIPT_PY!" "!REF_FILE!" "!TARGET_FILE!" 2>> "%LOG_FILE%"

if !ERRORLEVEL! NEQ 0 (
    echo.
    echo ========================================
    echo ERRO na conversao. Veja %LOG_FILE%
    echo ========================================
    type "%LOG_FILE%"
    pause
    exit /b !ERRORLEVEL!
) else (
    echo.
    echo ========================================
    echo Conversao concluida!
    echo ========================================
)
pause
endlocal