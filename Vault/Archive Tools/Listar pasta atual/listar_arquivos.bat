@echo off
setlocal enabledelayedexpansion

rem ======= CONFIG =======
set "PYTHON_PATH=C:\Python313\python.exe"
set "FFPROBE_PATH=C:\FFmpeg\bin\ffprobe.exe"
set "SCRIPT_NAME=listar_arquivos.py"
rem ======================

set "SCRIPT_PATH=%~dp0%SCRIPT_NAME%"

"%PYTHON_PATH%" "%SCRIPT_PATH%" "%FFPROBE_PATH%"
pause
