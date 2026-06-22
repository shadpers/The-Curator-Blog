@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ====================================================================
::               SYNC DETECTOR MASS - Analise em Lote
:: ====================================================================

set "LOG_FILE=%~dp0sync_mass_log.txt"

echo.
echo ===================================================================
echo    SYNC DETECTOR MASS - Analise de Delay em Lote
echo ===================================================================
echo.

echo =================================================================== > "%LOG_FILE%"
echo SYNC DETECTOR MASS - LOG >> "%LOG_FILE%"
echo Data/Hora: %DATE% %TIME% >> "%LOG_FILE%"
echo =================================================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

:: Verifica argumentos
if "%~1"=="" (
    echo ERRO: Nenhuma pasta fornecida
    echo.
    echo Como usar:
    echo    Arraste DUAS PASTAS para este .bat:
    echo    1a - Pasta com episodios BD
    echo    2a - Pasta com episodios WEB
    echo.
    echo Ou via linha de comando:
    echo    run_mass_audio_delay.bat "C:\pasta_BD" "C:\pasta_WEB"
    echo.
    echo ===================================================================
    pause
    exit /b 1
)

if "%~2"=="" (
    echo ERRO: Faltou a segunda pasta
    echo.
    echo Voce precisa arrastar AMBAS as pastas juntas
    echo.
    echo ===================================================================
    pause
    exit /b 1
)

:: %~1 e %~2 ja removem as aspas externas
set "BD_PATH=%~1"
set "WEB_PATH=%~2"

:: Verifica se sao pastas (trailing backslash e mais robusto que \* com colchetes)
if not exist "!BD_PATH!\" (
    echo ERRO: O primeiro argumento nao e uma pasta valida:
    echo    !BD_PATH!
    echo.
    echo ===================================================================
    pause
    exit /b 1
)

if not exist "!WEB_PATH!\" (
    echo ERRO: O segundo argumento nao e uma pasta valida:
    echo    !WEB_PATH!
    echo.
    echo ===================================================================
    pause
    exit /b 1
)

echo Pasta BD:  !BD_PATH!
echo Pasta WEB: !WEB_PATH!
echo.

echo Pasta BD:  !BD_PATH! >> "%LOG_FILE%"
echo Pasta WEB: !WEB_PATH! >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

:: Configuracoes
set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0mass_calculate_audio_delay.py"

:: Verifica Python
if not exist "!PYTHON_EXE!" (
    echo ERRO: Python nao encontrado em !PYTHON_EXE!
    echo.
    echo Solucao:
    echo    1. Instale Python 3.x de https://python.org
    echo    2. Ou edite este .bat e corrija o caminho PYTHON_EXE
    echo.
    echo ===================================================================
    pause
    exit /b 1
)

:: Verifica script Python
if not exist "!SCRIPT_PY!" (
    echo ERRO: Script Python nao encontrado
    echo.
    echo Procurando: !SCRIPT_PY!
    echo.
    echo Certifique-se que mass_calculate_audio_delay.py esta na mesma pasta.
    echo.
    echo ===================================================================
    pause
    exit /b 1
)

echo Iniciando analise em lote...
echo =================================================================== >> "%LOG_FILE%"
echo EXECUTANDO... >> "%LOG_FILE%"
echo =================================================================== >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

"!PYTHON_EXE!" -u "!SCRIPT_PY!" "!BD_PATH!" "!WEB_PATH!" 2>> "%LOG_FILE%"

set ERROR_CODE=!ERRORLEVEL!

echo. >> "%LOG_FILE%"
echo =================================================================== >> "%LOG_FILE%"

if !ERROR_CODE! NEQ 0 (
    echo ERRO - Codigo: !ERROR_CODE! >> "%LOG_FILE%"
    echo.
    echo ===================================================================
    echo ERRO durante a execucao - Codigo !ERROR_CODE!
    echo ===================================================================
    echo.
    echo Verifique o log para mais detalhes:
    echo    !LOG_FILE!
    echo.
    echo -------------------------------------------------------------------
    type "!LOG_FILE!"
    echo -------------------------------------------------------------------
) else (
    echo SUCESSO >> "%LOG_FILE%"
    echo.
    echo Log salvo em: !LOG_FILE!
)

echo =================================================================== >> "%LOG_FILE%"
echo.
pause
endlocal
