@echo off
title Verificador de Links
color 0A

:: Caminho do Python (ajuste se necessário)
set "PY=C:\Program Files\Python314\python.exe"

if not exist "%PY%" (
    color 0C
    echo.
    echo ERRO: Python nao encontrado em %PY%
    echo.
    pause
    exit
)

cls
echo.
echo Iniciando verificador...
echo.

:: Atualiza/instala dependências de forma silenciosa
"%PY%" -m pip install --quiet requests beautifulsoup4 cloudscraper

echo.
"%PY%" checker.py

echo.
echo Programa finalizado.
pause