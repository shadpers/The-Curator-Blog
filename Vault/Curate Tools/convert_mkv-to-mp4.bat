@echo off
SETLOCAL EnableDelayedExpansion

:: Define a codificação do console para ANSI (CP1252)
chcp 1252 >nul

:: Define caminhos
SET PYTHON_PATH=C:\Python313\python.exe
SET FFMPEG_PATH=C:\FFmpeg\bin\ffmpeg.exe
SET SCRIPT_PATH=%~dp0mkv-to-mp4.py

:: Verifica se o Python existe
IF NOT EXIST "%PYTHON_PATH%" (
    ECHO Erro: Python nao encontrado em %PYTHON_PATH%. Instale o Python 3.13 ou ajuste o caminho.
    PAUSE
    GOTO :EOF
)

:: Verifica se o FFmpeg existe
IF NOT EXIST "%FFMPEG_PATH%" (
    ECHO Erro: FFmpeg nao encontrado em %FFMPEG_PATH%. Instale o FFmpeg ou ajuste o caminho.
    PAUSE
    GOTO :EOF
)

:: Verifica se um arquivo foi fornecido
IF "%~1"=="" (
    ECHO Por favor, arraste e solte um arquivo MKV neste script.
    PAUSE
    GOTO :EOF
)

:: Escapa o & para exibição
SET "DISPLAY_PATH=%~1"
SET "DISPLAY_PATH=%DISPLAY_PATH:&=^&%"
ECHO Processando arquivo: !DISPLAY_PATH!

:: Cria um nome temporário para o arquivo, substituindo & por _
SET "FILE_PATH=%~1"
SET "TEMP_FILE_PATH=%~dpn1_tmp%~x1"
SET "TEMP_FILE_PATH=%TEMP_FILE_PATH:&=_%"

:: Copia o arquivo para o nome temporário, suprimindo a saída
COPY "%FILE_PATH%" "%TEMP_FILE_PATH%" >nul
IF ERRORLEVEL 1 (
    ECHO Erro: Falha ao copiar o arquivo para %TEMP_FILE_PATH%.
    PAUSE
    GOTO :EOF
)

:: Verifica se o arquivo temporário foi criado
IF NOT EXIST "%TEMP_FILE_PATH%" (
    ECHO Erro: Arquivo temporário %TEMP_FILE_PATH% não foi criado.
    PAUSE
    GOTO :EOF
)

:: Executa o Python com o arquivo temporário
ECHO Executando Python com arquivo temporário: %TEMP_FILE_PATH%
"%PYTHON_PATH%" "%SCRIPT_PATH%" "%TEMP_FILE_PATH%"

IF ERRORLEVEL 1 (
    ECHO Erro: Falha ao executar o script Python.
    DEL "%TEMP_FILE_PATH%" >nul
    PAUSE
    GOTO :EOF
)

:: Remove o arquivo temporário
DEL "%TEMP_FILE_PATH%" >nul

ECHO Processamento concluido.
PAUSE
ENDLOCAL