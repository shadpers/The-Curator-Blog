@echo off
chcp 65001 >nul
title Audio Stretch Auto - BD x WEB

if "%~2"=="" (
    echo Arraste DOIS arquivos sobre este .bat:
    echo  1º BD
    echo  2º WEB
    pause
    exit /b
)

C:\venvs\torch313\Scripts\python.exe "%~dp0audio_stretch_from_pairs_auto.py" %*

pause