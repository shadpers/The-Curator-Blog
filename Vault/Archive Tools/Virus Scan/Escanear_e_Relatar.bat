@echo off
CHCP 65001 > nul

REM -----------------------------------------------------------------
REM Diretório do script e paths
REM -----------------------------------------------------------------
set SCRIPT_DIR=%~dp0
set PYTHON_EXE="C:\Python313\python.exe"
set PYTHON_SCRIPT="%SCRIPT_DIR%gerador_relatorio.py"

REM -----------------------------------------------------------------
REM Arquivo alvo
REM -----------------------------------------------------------------
set TARGET_FILE=%~1

if not defined TARGET_FILE (
    echo.
    echo  Por favor, arraste e solte um arquivo sobre este script para iniciar a verificacao.
    echo.
    pause
    exit /b
)

echo ======================================================
echo      INICIANDO VERIFICACAO DE SEGURANCA
echo ======================================================
echo.
echo Arquivo a ser verificado: %TARGET_FILE%
echo.

%PYTHON_EXE% %PYTHON_SCRIPT% "%TARGET_FILE%"

echo.
echo ======================================================
echo      PROCESSO CONCLUIDO
echo ======================================================
echo.
echo Pressione qualquer tecla para fechar esta janela...
pause > nul
