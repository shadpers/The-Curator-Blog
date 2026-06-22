@echo off
setlocal enabledelayedexpansion

set "LOG_FILE=%~dp0sync_video_log.txt"

echo.
echo ===============================================================
echo    SYNC DETECTOR VISUAL - Analise de Delay por Frame
echo ===============================================================
echo.

echo =============================================================== > "%LOG_FILE%"
echo SYNC DETECTOR VISUAL - LOG de Execucao >> "%LOG_FILE%"
echo Data/Hora: %DATE% %TIME% >> "%LOG_FILE%"
echo =============================================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

if "%~1"=="" (
    echo ERRO: Nenhum arquivo fornecido.
    echo.
    echo Como usar:
    echo   Arraste DOIS arquivos de video para este .bat
    echo   1. Arquivo BD
    echo   2. Arquivo WEB
    echo.
    echo ===============================================================
    pause
    exit /b 1
)

if "%~2"=="" (
    echo ERRO: Faltou o segundo arquivo.
    echo.
    echo Arraste AMBOS os arquivos juntos:
    echo   1. Arquivo BD
    echo   2. Arquivo WEB
    echo.
    echo ===============================================================
    pause
    exit /b 1
)

set "BD_PATH=%~1"
set "WEB_PATH=%~2"

echo BD:  %~nx1
echo WEB: %~nx2
echo.

echo Arquivo BD:  %~1 >> "%LOG_FILE%"
echo Arquivo WEB: %~2 >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0calculate_video_delay.py"

if not exist "%PYTHON_EXE%" (
    echo ERRO: Python nao encontrado em %PYTHON_EXE%
    echo.
    echo Solucao: edite este .bat e corrija o caminho PYTHON_EXE
    echo.
    pause
    exit /b 1
)

if not exist "%SCRIPT_PY%" (
    echo ERRO: Script Python nao encontrado.
    echo Procurando em: %SCRIPT_PY%
    echo.
    echo Certifique-se que calculate_video_delay.py esta na mesma pasta.
    echo Pasta atual: %~dp0
    echo.
    pause
    exit /b 1
)

echo Verificando dependencias Python...
"%PYTHON_EXE%" -c "import cv2, scipy, numpy, win32com" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Dependencias faltando. Instalando...
    echo.
    "%PYTHON_EXE%" -m pip install opencv-python pywin32 scipy numpy
    echo.
)

echo.
echo Iniciando analise visual...
echo.
echo ---------------------------------------------------------------
echo  Esta analise extrai e compara frames dos videos.
echo  Tempo estimado: 30 a 90 segundos dependendo do hardware.
echo ---------------------------------------------------------------
echo.

echo =============================================================== >> "%LOG_FILE%"
echo EXECUTANDO ANALISE... >> "%LOG_FILE%"
echo =============================================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

"%PYTHON_EXE%" -u "%SCRIPT_PY%" "%BD_PATH%" "%WEB_PATH%" 2>> "%LOG_FILE%"

set ERROR_CODE=%ERRORLEVEL%

echo. >> "%LOG_FILE%"
echo =============================================================== >> "%LOG_FILE%"

if %ERROR_CODE% NEQ 0 (
    echo ERRO - Codigo de saida: %ERROR_CODE% >> "%LOG_FILE%"
    echo.
    echo ===============================================================
    echo ERRO durante a execucao - Codigo %ERROR_CODE%
    echo ===============================================================
    echo.
    echo Log completo:
    echo ---------------------------------------------------------------
    type "%LOG_FILE%"
    echo ---------------------------------------------------------------
) else (
    echo SUCESSO - Analise concluida >> "%LOG_FILE%"
    echo.
    echo Log salvo em: %LOG_FILE%
)

echo =============================================================== >> "%LOG_FILE%"
echo.
pause
endlocal
