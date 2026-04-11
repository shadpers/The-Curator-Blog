@echo off
setlocal EnableDelayedExpansion
title EYEPATCH - Eyecatch-Aware Patch and Correction Helper

set "PYTHON=C:\Python313\python.exe"

echo.
echo ================================================================
echo   EYEPATCH  ^|  Eyecatch-Aware Patch ^& Correction Helper
echo ================================================================
echo.
echo   Arraste: [REFERENCIA.mkv] [ALVO.mkv]
echo   O primeiro e a referencia, o segundo recebe os ajustes.
echo.

if "%~1"=="" (
    echo   ERRO: nenhum arquivo recebido.
    pause & exit /b
)
if "%~2"=="" (
    echo   ERRO: necessario informar DOIS arquivos.
    pause & exit /b
)

call :resolve "%~f1" REF_FILE
call :resolve "%~f2" TGT_FILE

if not exist "!REF_FILE!" (
    echo   ERRO: referencia nao encontrada: !REF_FILE!
    pause & exit /b
)
if not exist "!TGT_FILE!" (
    echo   ERRO: alvo nao encontrado: !TGT_FILE!
    pause & exit /b
)

echo   REF : !REF_FILE!
echo   ALVO: !TGT_FILE!
echo.

"%PYTHON%" "%~dp0eyepatch.py" "!REF_FILE!" "!TGT_FILE!"

echo.
pause
exit /b

:: ── Resolve .lnk ────────────────────────────────────────────────────────────
:resolve
set "input_file=%~f1"
set "ext=%~x1"
if /I "!ext!"==".lnk" (
    set "esc=!input_file:'=''!"
    for /f "usebackq delims=" %%R in (
        `powershell -NoProfile -Command "(New-Object -ComObject WScript.Shell).CreateShortcut('!esc!').TargetPath"`
    ) do set "%2=%%R"
) else (
    set "%2=!input_file!"
)
exit /b
