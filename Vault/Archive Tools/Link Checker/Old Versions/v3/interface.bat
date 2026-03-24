@echo off
title Verificador de Links - Manus AI
color 0A

:: Define o caminho do Python
set PY="C:\Program Files\Python314\python.exe"

:: Verifica se existe
if not exist %PY% (
    color 0C
    echo ERRO: Python nao encontrado em %PY%
    pause
    exit
)

:menu
cls
echo ==========================================
echo       VERIFICADOR DE LINKS ONLINE
echo ==========================================
echo.
echo 1. Iniciar Verificacao
echo 2. Ver Historico
echo 3. Sair
echo.
set /p opt=Escolha: 

if "%opt%"=="1" goto run
if "%opt%"=="2" goto history
if "%opt%"=="3" exit
goto menu

:run
cls
echo Instalando dependencias...
%PY% -m pip install requests beautifulsoup4 cloudscraper --quiet
echo.
echo Iniciando verificacao...
echo.
%PY% checker.py
echo.
pause
goto menu

:history
cls
if exist history.json (
    notepad history.json
) else (
    echo Historico nao encontrado.
    pause
)
goto menu