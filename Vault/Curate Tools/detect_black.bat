@echo off
REM Arquivo .bat para drag-and-drop de vídeos MKV no script Python de detecção de tela preta

REM Verifica se um arquivo foi arrastado
if "%~1"=="" (
    echo Arraste um arquivo MKV para este .bat!
    pause
    exit /b
)

REM Define o caminho do Python
set PYTHON=C:\Python313\python.exe

REM Define o caminho do FFmpeg
set FFMPEG=C:\FFmpeg\bin\ffmpeg.exe

REM Define o caminho do script Python (assumindo que está na mesma pasta do .bat)
set SCRIPT=detect_black.py

REM Chama o script Python com o arquivo arrastado como argumento
"%PYTHON%" %SCRIPT% "%~1"

REM Pausa para ver o resultado
pause