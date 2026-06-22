@echo off
chcp 65001 >nul
title Release Renamer

:: ---------------------------------------------------------
::  Coloque este .bat na mesma pasta que release_renamer.py
::  Arraste um ou mais arquivos .mkv sobre ele para iniciar
:: ---------------------------------------------------------

set PYTHON="C:\Python313\python.exe"
set FFPROBE="C:\FFmpeg\bin\ffprobe.exe"

if "%~1"=="" (
    echo.
    echo  Uso: arraste um ou mais arquivos .mkv sobre este .bat
    echo.
    pause
    exit /b 0
)

if not exist %PYTHON% (
    echo.
    echo  ERRO: Python nao encontrado em %PYTHON%
    echo.
    pause
    exit /b 1
)

if not exist %FFPROBE% (
    echo.
    echo  ERRO: ffprobe nao encontrado em %FFPROBE%
    echo.
    pause
    exit /b 1
)

%PYTHON% "%~dp0release_renamer.py" %*

exit /b 0
