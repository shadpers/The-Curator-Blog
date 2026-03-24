@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: Caminho do mkvextract (sem aspas duplas extras!)
set MKVEXTRACT=C:\Program Files\MKVToolNix\mkvextract.exe

:: Verifica se um arquivo foi arrastado
if "%~1"=="" (
    echo Arraste um arquivo .mkv sobre este script para extrair os capítulos.
    pause
    exit /b
)

:: Caminho do arquivo MKV (entre aspas)
set "arquivo=%~1"
set "nome=%~n1"
set "saida=%~dp0%nome%_chapters.xml"

:: Extrai os capítulos usando o mkvextract
echo Extraindo capítulos de:
echo "%arquivo%"
"%MKVEXTRACT%" chapters "%arquivo%" -s > "%saida%"

:: Verifica se o arquivo foi criado
if exist "%saida%" (
    echo.
    echo Capítulos extraídos com sucesso para:
    echo "%saida%"
) else (
    echo Erro ao extrair os capítulos. Verifique o caminho do mkvextract.
)

echo.
pause
