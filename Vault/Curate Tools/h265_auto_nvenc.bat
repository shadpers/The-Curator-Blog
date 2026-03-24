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

for /L %%i in (1,1,!TOTAL!) do (
    echo.
    echo ========================================
    echo Processando %%~nxi
    echo ========================================
    "C:\Python313\python.exe" "%~dp0mkv_to_h265_auto.py" "!FILES[%%i]!"
    if errorlevel 1 (
        echo ERRO no arquivo %%~nxi
        pause
    )
)

echo.
echo FINALIZADO
pause
