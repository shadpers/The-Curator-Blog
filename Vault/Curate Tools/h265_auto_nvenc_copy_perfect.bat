@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

if "%~1"=="" (
    echo ERRO: Nenhum arquivo especificado.
    pause
    exit /b 1
)

set "IDX=0"

echo ========================================
echo ARQUIVOS PARA CONVERSAO H265 (NVENC)
echo COPIA PERFEITA - PRESERVA TUDO
echo ========================================

:loop
if "%~1"=="" goto run
set /a IDX+=1
set "FILES[!IDX!]=%~1"
echo !IDX!. %~nx1
shift
goto loop

:run
set "TOTAL=!IDX!"
echo ========================================
echo Total: !TOTAL!
echo ========================================
echo.

REM Monta a lista de todos os arquivos
set "ALL_FILES="
for /L %%i in (1,1,!TOTAL!) do (
    set "ALL_FILES=!ALL_FILES! "!FILES[%%i]!""
)

REM Chama o Python UMA VEZ com todos os arquivos
"C:\Python313\python.exe" "%~dp0mkv_to_h265_auto_copy_perfect.py" !ALL_FILES!
if errorlevel 1 (
    echo ERRO no processamento
    pause
)

echo.
echo FINALIZADO
pause