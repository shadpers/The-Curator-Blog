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
    echo Arraste e solte um arquivo de video sobre este script para cortar.
    echo Exemplo: cortar_video.bat "C:\Caminho\Para\Seu\Video.mkv"
    echo.
    pause
    exit /b 1
)

set "inputFile=%~1"
set "outputName="

:ask_output_name
set /p "outputName=Digite o nome do arquivo de saida (ex: episodio_1.mkv): "
if "%outputName%"=="" (
    echo O nome do arquivo de saida nao pode ser vazio. Tente novamente.
    goto ask_output_name
)

:ask_start_time
set /p "startTime=Digite o tempo de inicio do corte (HH:MM:SS.ms, ex: 00:00:00.000): "
if "%startTime%"=="" (
    echo O tempo de inicio nao pode ser vazio. Tente novamente.
    goto ask_start_time
)

:ask_end_time
set /p "endTime=Digite o tempo final do corte (HH:MM:SS.ms, ex: 00:23:45.500): "
if "%endTime%"=="" (
    echo O tempo final nao pode ser vazio. Tente novamente.
    goto ask_end_time
)

set "outputFile=%~dp1%outputName%"

echo.
echo Cortando "%inputFile%" de %startTime% ate %endTime% para "%outputFile%"...

"%FFMPEG_PATH%" -i "%inputFile%" -ss %startTime% -to %endTime% -map 0 -c copy "%outputFile%"

if %errorlevel% equ 0 (
    echo.
    echo Corte concluido com sucesso!
) else (
    echo.
    echo Ocorreu um erro durante o corte.
)

pause
endlocal

