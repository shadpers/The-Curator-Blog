@echo off
setlocal enabledelayedexpansion

:: Caminho para o ffprobe.exe - AJUSTE se necessário
set "FFPROBE=C:\FFmpeg\bin\ffprobe.exe"

:: Verifica se um arquivo foi arrastado
if "%~1"=="" (
    echo.
    echo Arraste um arquivo MKV sobre este arquivo .bat
    pause
    exit /b
)

:: Caminhos
set "INPUT=%~1"
set "BASENAME=%~n1"
set "FOLDER=%~dp1"
set "OUTPUT=%FOLDER%%BASENAME%.txt"

:: Executa ffprobe com saída completa e salva no txt
"%FFPROBE%" -i "%INPUT%" -hide_banner > "%OUTPUT%" 2>&1

echo.
echo ================= RELATÓRIO FFPROBE =================
type "%OUTPUT%"
echo ====================================================
echo.
echo Relatório completo salvo como: %OUTPUT%
pause
