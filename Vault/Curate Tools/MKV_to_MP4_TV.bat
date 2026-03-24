@echo off
setlocal EnableDelayedExpansion
if "%~1"=="" (
    echo ERRO: Nenhum arquivo especificado. Arraste MKVs para o .bat.
    pause
    exit /b 1
)
set "IDX=0"
echo ========================================
echo ARQUIVOS PARA TRANSFORMAR:
echo ========================================
:loop_list
if "%~1"=="" goto end_list
set /a IDX+=1
set "FILES[!IDX!]=%~1"
echo !IDX!. %~nx1
shift
goto loop_list
:end_list
set "TOTAL=!IDX!"
echo ========================================
echo Total: !TOTAL! arquivo(s). Processando um por vez...
echo ========================================
set "SUC=0"
for /L %%i in (1,1,!TOTAL!) do (
    set "CUR_FILE=!FILES[%%i]!"
    echo.
    echo --- Processando: %%~nxi ---
    "C:\Python313\python.exe" "mkv_to_mp4_tv.py" "!CUR_FILE!"
    if !errorlevel! equ 0 (
        set /a SUC+=1
        echo Sucesso em %%~nxi!
    ) else (
        echo ERRO em %%~nxi. Continuando pro proximo...
    )
)
echo ========================================
echo TODOS CONCLUIDOS! (!SUC!/!TOTAL! processados)
echo ========================================
pause