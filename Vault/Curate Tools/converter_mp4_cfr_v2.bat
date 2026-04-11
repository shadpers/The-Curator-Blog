@echo off
setlocal

set "FFMPEG_PATH=C:\FFmpeg\bin\ffmpeg.exe"

if not exist "%FFMPEG_PATH%" (
    echo Erro: FFmpeg nao encontrado em "%FFMPEG_PATH%".
    pause
    exit /b 1
)

if "%~1"=="" (
    echo.
    echo Arraste e solte um arquivo sobre este script para converter para CFR.
    echo.
    pause
    exit /b 1
)

set "inputFile=%~1"
set "outputFile=%~dpn1_CFR.mp4"

echo.
echo ============================================================
echo  Converter VFR para CFR v3 - NVENC + 10bit fix + All audio
echo ============================================================
echo.
echo Arquivo de entrada : "%inputFile%"
echo Arquivo de saida   : "%outputFile%"
echo.

echo Verificando suporte a NVENC...
"%FFMPEG_PATH%" -f lavfi -i nullsrc -t 1 -c:v h264_nvenc -f null - >nul 2>&1

if %errorlevel% neq 0 (
    echo [AVISO] NVENC nao disponivel. Usando fallback para libx264...
    echo.
    "%FFMPEG_PATH%" -i "%inputFile%" ^
        -map 0:v:0 ^
        -map 0:a ^
        -r 23.976 -fps_mode cfr ^
        -c:v libx264 -preset ultrafast -crf 30 ^
        -pix_fmt yuv420p ^
        -c:a copy ^
        "%outputFile%"
) else (
    echo [OK] NVENC detectado. Usando aceleracao por GPU.
    echo.
    "%FFMPEG_PATH%" -i "%inputFile%" ^
        -map 0:v:0 ^
        -map 0:a ^
        -r 23.976 -fps_mode cfr ^
        -c:v h264_nvenc -preset p4 -rc vbr -cq 30 -b:v 0 ^
        -pix_fmt yuv420p ^
        -c:a copy ^
        "%outputFile%"
)

if %errorlevel% equ 0 (
    echo.
    echo [SUCESSO] Conversao para CFR concluida!
    echo O novo arquivo esta em: "%outputFile%"
) else (
    echo.
    echo [ERRO] Ocorreu um erro durante a conversao.
)

echo.
pause
endlocal