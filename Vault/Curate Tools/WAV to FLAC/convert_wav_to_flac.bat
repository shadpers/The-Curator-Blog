@echo off
setlocal enabledelayedexpansion

:: Define codificacao UTF-8 para o console
chcp 65001 >nul

set "LOG_FILE=%~dp0conversion_log.txt"
echo ========================================== > "%LOG_FILE%"
echo CONVERSAO WAV PARA FLAC - v1.1
echo Iniciando em %DATE% %TIME% >> "%LOG_FILE%"
echo ========================================== >> "%LOG_FILE%"

:: Verifica se algum argumento foi passado
if "%~1" == "" (
    echo.
    echo ========================================================
    echo    CONVERSOR WAV PARA FLAC COM METADADOS
    echo ========================================================
    echo.
    echo INSTRUCOES:
    echo   1. Arraste a PASTA contendo os arquivos WAV para este .bat
    echo   2. A pasta deve conter:
    echo      - Arquivos WAV
    echo      - gabarito.txt
    echo      - cover.jpg ou cover.png
    echo.
    pause
    exit /b 1
)

:: Pega o primeiro argumento de forma segura
:: %~1 remove aspas externas se existirem
set "INPUT_FOLDER=%~1"

:: Remove barra invertida final se existir (evita problemas de escape no Python)
if "!INPUT_FOLDER:~-1!"=="\" set "INPUT_FOLDER=!INPUT_FOLDER:~0,-1!"

echo Pasta de entrada: "!INPUT_FOLDER!"
echo Pasta de entrada: "!INPUT_FOLDER!" >> "%LOG_FILE%"

if not exist "!INPUT_FOLDER!" (
    echo.
    echo ERRO: Pasta nao encontrada!
    echo Verifique se o caminho esta correto: "!INPUT_FOLDER!"
    echo ERRO: Pasta nao encontrada: "!INPUT_FOLDER!" >> "%LOG_FILE%"
    pause
    exit /b 1
)

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0convert_wav_to_flac.py"

:: Se o script corrigido existir, usa ele, senao usa o original
if exist "%~dp0convert_wav_to_flac_fixed.py" (
    set "SCRIPT_PY=%~dp0convert_wav_to_flac_fixed.py"
)

if not exist "%PYTHON_EXE%" (
    echo ERRO: Python nao encontrado em %PYTHON_EXE%
    pause
    exit /b 1
)

if not exist "%SCRIPT_PY%" (
    echo ERRO: Script Python nao encontrado: %SCRIPT_PY%
    pause
    exit /b 1
)

echo.
echo Iniciando conversao...
echo.

:: Executa o Python passando o argumento entre aspas
:: O script Python agora tambem trata a barra invertida final
"%PYTHON_EXE%" -u "%SCRIPT_PY%" "!INPUT_FOLDER!"

set PYTHON_EXIT=%ERRORLEVEL%

if %PYTHON_EXIT% NEQ 0 (
    echo.
    echo ========================================================
    echo    ERRO NA CONVERSAO (Codigo: %PYTHON_EXIT%)
    echo ========================================================
    echo.
    pause
    exit /b %PYTHON_EXIT%
) else (
    echo.
    echo ========================================================
    echo    CONVERSAO CONCLUIDA COM SUCESSO!
    echo ========================================================
    echo.
)

pause
endlocal
