@echo off
setlocal enableDelayedExpansion

:: Define o caminho completo para o executavel do FFmpeg
set "FFMPEG_PATH=C:\FFmpeg\bin\ffmpeg.exe"
set "FFPROBE_PATH=C:\FFmpeg\bin\ffprobe.exe"

:: Define um arquivo temporario para a saida do ffprobe
set "TEMP_FPS_FILE=%TEMP%\ffprobe_fps_output.txt"

echo Verificando caminhos do FFmpeg e FFprobe...
pause

:: Verifica se o FFmpeg existe no caminho especificado
if not exist "%FFMPEG_PATH%" (
    echo Erro: FFmpeg nao encontrado em "%FFMPEG_PATH%".
    echo Por favor, verifique o caminho ou mova o ffmpeg.exe para este local.
    pause
    exit /b 1
)

echo FFmpeg encontrado.
pause

:: Verifica se o FFprobe existe no caminho especificado
if not exist "%FFPROBE_PATH%" (
    echo Erro: FFprobe nao encontrado em "%FFPROBE_PATH%".
    echo Por favor, verifique o caminho ou mova o ffprobe.exe para este local.
    pause
    exit /b 1
)

echo FFprobe encontrado.
pause

if "%~1"=="" (
    echo.
    echo Arraste e solte um arquivo MP4 sobre este script para extrair o audio.
    echo Exemplo: extrair_audio_e_verificar_cfr.bat "C:\Caminho\Para\Seu\Video.mp4"
    echo.
    pause
    exit /b 1
)

set "inputFile=%~1"
set "outputFile=%~dpn1_audio.m4a"

echo Arquivo de entrada: "%inputFile%"
echo Arquivo de saida: "%outputFile%"
pause

echo.
echo Verificando o Frame Rate do video...
pause

:: Executa ffprobe e redireciona a saida para um arquivo temporario
"%FFPROBE_PATH%" -v quiet -select_streams v:0 -show_entries stream=avg_frame_rate,r_frame_rate -of default=noprint_wrappers=1:nokey=1 "%inputFile%" > "%TEMP_FPS_FILE%" 2>nul

:: Le a saida do arquivo temporario
set "fps_info="
for /f "usebackq delims=" %%a in ("%TEMP_FPS_FILE%") do (
    set "fps_info=%%a"
)

:: Apaga o arquivo temporario
del "%TEMP_FPS_FILE%" 2>nul

echo Informacoes de FPS brutas: !fps_info!
pause

set "avg_frame_rate="
set "r_frame_rate="

:: Tenta extrair os dois valores de frame rate
for /f "tokens=1,2 delims= " %%b in ("!fps_info!") do (
    set "avg_frame_rate=%%b"
    set "r_frame_rate=%%c"
)

echo avg_frame_rate: !avg_frame_rate!
echo r_frame_rate: !r_frame_rate!
pause

echo Analisando o frame rate...
pause

:: Simplificando a verificacao - apenas mostra o frame rate detectado
echo Frame Rate detectado: !avg_frame_rate!
echo Prosseguindo com a extracao de audio...
pause

echo.
echo Extraindo audio de "%inputFile%" para "%outputFile%"...
pause

echo Executando comando FFmpeg...
pause

"%FFMPEG_PATH%" -i "%inputFile%" -vn -acodec copy "%outputFile%"

echo Comando FFmpeg executado. Verificando resultado...
pause

if %errorlevel% equ 0 (
    echo.
    echo Extracao de audio concluida com sucesso!
    echo O arquivo de audio esta em: "%outputFile%"
) else (
    echo.
    echo Ocorreu um erro durante a extracao de audio. Codigo de erro: %errorlevel%
)

pause
endlocal