@echo off
title Verificador de Links - Sistema Modular
color 0A

:: Caminho do Python (ajuste se necessÃ¡rio)
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
echo ============================================================
echo            VERIFICADOR DE LINKS - SISTEMA MODULAR
echo ============================================================
echo.

:: Atualiza/instala dependencias de forma silenciosa
echo Instalando/verificando dependencias...
"%PY%" -m pip install --quiet requests beautifulsoup4 cloudscraper

echo.
echo Iniciando verificador...
echo.
"%PY%" -B checker.py

echo.
echo Programa finalizado.
pause
