@echo off
chcp 65001 >nul
echo ========================================
echo  Chapter Fix - Correcao de Capitulos
echo ========================================
echo.

REM Se um arquivo/pasta for arrastado, usa como diretorio; senao usa a pasta atual
if "%~1"=="" (
    set "TARGET=%~dp0"
) else (
    if exist "%~1\" (
        set "TARGET=%~1"
    ) else (
        set "TARGET=%~dp1"
    )
)

echo Pasta alvo: %TARGET%
echo.

REM Usa pasta TEMP do sistema (sem espacos no path do arquivo temporario)
set "TMPFILE=%TEMP%\chfix_expected.tmp"
if exist "%TMPFILE%" del "%TMPFILE%" >nul 2>&1

REM Dry-run: analisa e salva o numero de capitulos escolhido
echo [1/2] Analisando arquivos...
"C:\Python313\python.exe" "%~dp0chapter_fix.py" "%TARGET%" --dry-run --save-expected %TMPFILE%

REM Verifica se o usuario definiu um padrao
if not exist "%TMPFILE%" (
    echo.
    echo Operacao cancelada ou erro na analise.
    pause
    exit /b
)

set /p EXPECTED=<"%TMPFILE%"
del "%TMPFILE%" >nul 2>&1

echo.
set /p CONFIRM="Deseja aplicar as correcoes? (s/n): "
if /i "%CONFIRM%"=="s" (
    echo.
    echo [2/2] Aplicando correcoes...
    "C:\Python313\python.exe" "%~dp0chapter_fix.py" "%TARGET%" -e %EXPECTED%
) else (
    echo Operacao cancelada.
)

echo.
pause
