@echo off
setlocal EnableDelayedExpansion

:: Define o caminho completo para o executável do FFmpeg
set "FFMPEG_PATH=C:\FFmpeg\bin\ffmpeg.exe"

:: Verifica se o arquivo FFmpeg existe no caminho especificado
if not exist "%FFMPEG_PATH%" (
    echo Erro: FFmpeg nao encontrado em "%FFMPEG_PATH%".
    echo Por favor, verifique o caminho ou mova o ffmpeg.exe para este local.
    pause
    exit /b 1
)

:: Verifica se um arquivo de entrada foi fornecido
if "%~1"=="" (
    echo.
    echo Arraste e solte um arquivo de video sobre este script para remover um trecho.
    echo Exemplo: remover_trecho.bat "C:\Caminho\Para\Seu\Video.mkv"
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
set /p "startTime=Digite o tempo de inicio do trecho a remover (HH:MM:SS.ms, ex: 00:06:22.715): "
if "%startTime%"=="" (
    echo O tempo de inicio nao pode ser vazio. Tente novamente.
    goto ask_start_time
)

:ask_end_time
set /p "endTime=Digite o tempo final do trecho a remover (HH:MM:SS.ms, ex: 00:07:53.055): "
if "%endTime%"=="" (
    echo O tempo final nao pode ser vazio. Tente novamente.
    goto ask_end_time
)

set "outputFile=%~dp1%outputName%"
set "tempDir=%TEMP%\ffmpeg_split"
set "listFile=%tempDir%\concat_list.txt"

:: Cria um diretorio temporario
if not exist "%tempDir%" mkdir "%tempDir%"

:: Gera os segmentos: inicio ate startTime e endTime ate o fim
echo.
echo Gerando segmentos temporarios...

:: Segmento 1: do inicio ate startTime
"%FFMPEG_PATH%" -i "%inputFile%" -to %startTime% -map 0 -c copy "%tempDir%\segment1.mkv"
if %errorlevel% neq 0 (
    echo Erro ao gerar o primeiro segmento.
    goto cleanup
)

:: Segmento 2: de endTime ate o final (usa -ss para pular ate endTime)
"%FFMPEG_PATH%" -i "%inputFile%" -ss %endTime% -map 0 -c copy "%tempDir%\segment2.mkv"
if %errorlevel% neq 0 (
    echo Erro ao gerar o segundo segmento.
    goto cleanup
)

:: Cria a lista de concatenacao
echo file 'segment1.mkv' > "%listFile%"
echo file 'segment2.mkv' >> "%listFile%"

echo.
echo Concatenando segmentos para "%outputFile%"...

:: Concatena os segmentos preservando todas as faixas
"%FFMPEG_PATH%" -f concat -safe 0 -i "%listFile%" -map 0 -c copy "%outputFile%"
if %errorlevel% equ 0 (
    echo.
    echo Remocao do trecho concluida com sucesso!
) else (
    echo.
    echo Ocorreu um erro durante a concatenacao.
)

:cleanup
:: Remove arquivos temporarios
if exist "%tempDir%" (
    echo.
    echo Removendo arquivos temporarios...
    rmdir /s /q "%tempDir%"
)

pause
endlocal
exit /b
