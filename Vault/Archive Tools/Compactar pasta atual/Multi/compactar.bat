@echo off
setlocal enabledelayedexpansion

set PYTHON_PATH=C:\Python313\python.exe
set FFPROBE_PATH=C:\FFmpeg\bin\ffprobe.exe
set SEVENZIP_PATH=C:\Program Files\7-Zip\7z.exe

"%PYTHON_PATH%" "%~dp0compactar.py" "%FFPROBE_PATH%" "%SEVENZIP_PATH%"
pause
