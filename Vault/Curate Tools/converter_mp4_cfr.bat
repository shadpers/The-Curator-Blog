@echo off
setlocal

:: Define o caminho completo para o executavel do FFmpeg
set "FFMPEG_PATH=C:\FFmpeg\bin\ffmpeg.exe"

:: Verifica se o arquivo FFmpeg existe no caminho especificado
if not exist "%FFMPEG_PATH%" (
    echo Erro: FFmpeg nao encontrado em "%FFMPEG_PATH%".
    echo Por favor, verifique o caminho ou mova o ffmpeg.exe para este local.
    pause
    exit /b 1
)

if "%~1"=="" (
    echo.
    echo Arraste e solte um arquivo MP4 sobre este script para converter para CFR.
    echo Exemplo: converter_mp4_cfr.bat "C:\Caminho\Para\Seu\Video_VFR.mp4"
    echo.
    pause
    exit /b 1
)

set "inputFile=%~1"
set "outputFile=%~dpn1_CFR.mp4"

echo.
echo Convertendo "%inputFile%" de VFR para CFR (23.976 fps) para "%outputFile%"...

:: Ajustado para qualidade de video menor (CRF 30) e preset mais rapido (ultrafast)
"%FFMPEG_PATH%" -i "%inputFile%" -r 23.976 -vsync cfr -c:v libx264 -preset ultrafast -crf 30 -c:a copy "%outputFile%"

if %errorlevel% equ 0 (
    echo.
    echo Conversao para CFR concluida com sucesso!
    echo O novo arquivo esta em: "%outputFile%"
) else (
    echo.
    echo Ocorreu um erro durante a conversao.
)

pause
endlocal

