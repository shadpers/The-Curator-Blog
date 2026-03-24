@echo off
setlocal EnableDelayedExpansion
title SYNC DETECTOR TURBO - Drift Analyzer

:: Caminho do ffprobe
set "FFPROBE=C:\FFmpeg\bin\ffprobe.exe"

:: Caminho do Python
set "PYTHON=C:\Python313\python.exe"

echo.
echo ===============================================================
echo    SYNC DETECTOR TURBO - Analise de Drift de Audio
echo ===============================================================
echo.

if "%~1"=="" (
    echo Uso:
    echo   Arraste o BD e depois o WEB para este .bat
    echo.
    pause
    exit /b
)

if "%~2"=="" (
    echo ERRO: e necessario informar DOIS arquivos.
    echo.
    pause
    exit /b
)

:: Resolver .lnk para BD
set "input_file=%~f1"
set "ext=%~x1"
if /I "!ext!"==".lnk" (
    set "escaped_path=!input_file:'=''!"
    for /f "usebackq delims=" %%R in (`powershell -NoProfile -Command "(New-Object -ComObject WScript.Shell).CreateShortcut('!escaped_path!').TargetPath"`) do (
        set "BD_FILE=%%R"
    )
) else (
    set "BD_FILE=!input_file!"
)

:: Resolver .lnk para WEB
set "input_file=%~f2"
set "ext=%~x2"
if /I "!ext!"==".lnk" (
    set "escaped_path=!input_file:'=''!"
    for /f "usebackq delims=" %%R in (`powershell -NoProfile -Command "(New-Object -ComObject WScript.Shell).CreateShortcut('!escaped_path!').TargetPath"`) do (
        set "WEB_FILE=%%R"
    )
) else (
    set "WEB_FILE=!input_file!"
)

if not exist "!BD_FILE!" (
    echo ERRO: Nao foi possivel resolver o caminho do BD: !BD_FILE!
    pause
    exit /b
)

if not exist "!WEB_FILE!" (
    echo ERRO: Nao foi possivel resolver o caminho do WEB: !WEB_FILE!
    pause
    exit /b
)

echo BD:  !BD_FILE!
echo WEB: !WEB_FILE!
echo.

echo ---------------------------------------------------------------
echo Streams de audio (BD)
echo ---------------------------------------------------------------
call "%FFPROBE%" -v error -analyzeduration 10M -probesize 10M -select_streams a -show_entries stream=index,codec_name,channels,sample_rate:stream_tags=language,title -of default=noprint_wrappers=1 "!BD_FILE!" 2>nul

echo.
echo ---------------------------------------------------------------
echo Streams de audio (WEB)
echo ---------------------------------------------------------------
call "%FFPROBE%" -v error -analyzeduration 10M -probesize 10M -select_streams a -show_entries stream=index,codec_name,channels,sample_rate:stream_tags=language,title -of default=noprint_wrappers=1 "!WEB_FILE!" 2>nul

echo.
set /p BD_IDX=Digite o indice do audio do BD: 
set /p WEB_IDX=Digite o indice do audio do WEB: 

echo.
echo ---------------------------------------------------------------
echo Iniciando analise de drift COMPLETA...
echo ---------------------------------------------------------------
echo.

"%PYTHON%" "%~dp0sync_detector_turbo.py" "!BD_FILE!" "!WEB_FILE!" %BD_IDX% %WEB_IDX%

echo.
echo ===============================================================
echo Analise finalizada
echo ===============================================================
echo.
pause
