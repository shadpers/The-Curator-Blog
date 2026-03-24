@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ====================================================================
::                    SYNC DETECTOR - Audio Delay Analyzer
:: ====================================================================

set "LOG_FILE=%~dp0sync_log.txt"

:: Banner
echo.
echo ═══════════════════════════════════════════════════════════════
echo    🎬 SYNC DETECTOR - Análise de Delay de Áudio
echo ═══════════════════════════════════════════════════════════════
echo.

:: Inicia log
echo ═══════════════════════════════════════════════════════════════ > "%LOG_FILE%"
echo SYNC DETECTOR - LOG de Execução >> "%LOG_FILE%"
echo Data/Hora: %DATE% %TIME% >> "%LOG_FILE%"
echo ═══════════════════════════════════════════════════════════════ >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

:: Verifica argumentos
if "%~1"=="" (
    echo ❌ Erro: Nenhum arquivo fornecido
    echo.
    echo 📖 Como usar:
    echo    Arraste DOIS arquivos para este .bat:
    echo    1º - Arquivo BD
    echo    2º - Arquivo WEB
    echo.
    echo    Ou execute via linha de comando:
    echo    sync_detector.bat "arquivo_BD.mkv" "arquivo_WEB.mkv"
    echo.
    echo ═══════════════════════════════════════════════════════════════
    pause
    exit /b 1
)

if "%~2"=="" (
    echo ❌ Erro: Faltou o segundo arquivo
    echo.
    echo Você precisa arrastar AMBOS os arquivos juntos:
    echo    1º - Arquivo BD
    echo    2º - Arquivo WEB
    echo.
    echo ═══════════════════════════════════════════════════════════════
    pause
    exit /b 1
)

:: Remove aspas extras e armazena
set "BD_PATH=%~1"
set "WEB_PATH=%~2"
set BD_PATH=!BD_PATH:"=!
set WEB_PATH=!WEB_PATH:"=!

:: Exibe arquivos
echo 📀 BD:  %~nx1
echo 🌐 WEB: %~nx2
echo.

:: Log
echo Arquivo BD:  !BD_PATH! >> "%LOG_FILE%"
echo Arquivo WEB: !WEB_PATH! >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

:: Configurações
set "PYTHON_EXE=C:\Python313\python.exe"
set "SCRIPT_PY=%~dp0calculate_audio_delay.py"

:: Verifica Python
if not exist "!PYTHON_EXE!" (
    echo ❌ ERRO: Python não encontrado em !PYTHON_EXE!
    echo.
    echo 🔧 Solução:
    echo    1. Instale Python 3.x de https://python.org
    echo    2. Ou edite este .bat e corrija o caminho PYTHON_EXE
    echo.
    echo Caminho atual configurado: !PYTHON_EXE!
    echo.
    echo ═══════════════════════════════════════════════════════════════
    pause
    exit /b 1
)

:: Verifica script Python
if not exist "!SCRIPT_PY!" (
    echo ❌ ERRO: Script Python não encontrado
    echo.
    echo Procurando: !SCRIPT_PY!
    echo.
    echo 🔧 Solução:
    echo    Certifique-se que calculate_audio_delay.py está na mesma pasta que este .bat
    echo.
    echo Pasta atual: %~dp0
    echo.
    echo ═══════════════════════════════════════════════════════════════
    pause
    exit /b 1
)

:: Executa análise
echo ⏳ Iniciando análise...
echo ═══════════════════════════════════════════════════════════════ >> "%LOG_FILE%"
echo EXECUTANDO ANÁLISE... >> "%LOG_FILE%"
echo ═══════════════════════════════════════════════════════════════ >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"

"!PYTHON_EXE!" -u "!SCRIPT_PY!" "!BD_PATH!" "!WEB_PATH!" 2>> "%LOG_FILE%"

set ERROR_CODE=!ERRORLEVEL!

:: Verifica resultado
echo. >> "%LOG_FILE%"
echo ═══════════════════════════════════════════════════════════════ >> "%LOG_FILE%"
if !ERROR_CODE! NEQ 0 (
    echo ERRO - Código de saída: !ERROR_CODE! >> "%LOG_FILE%"
    echo.
    echo ═══════════════════════════════════════════════════════════════
    echo ❌ ERRO durante a execução - Código !ERROR_CODE!
    echo ═══════════════════════════════════════════════════════════════
    echo.
    echo 📄 Verifique o log para mais detalhes:
    echo    !LOG_FILE!
    echo.
    echo ═══════════════════════════════════════════════════════════════
    echo.
    echo 📋 Conteúdo do log:
    echo ───────────────────────────────────────────────────────────────
    type "!LOG_FILE!"
    echo ───────────────────────────────────────────────────────────────
) else (
    echo SUCESSO - Análise concluída >> "%LOG_FILE%"
    echo.
    echo 💾 Log salvo em: !LOG_FILE!
)

echo ═══════════════════════════════════════════════════════════════ >> "%LOG_FILE%"

echo.
pause
endlocal