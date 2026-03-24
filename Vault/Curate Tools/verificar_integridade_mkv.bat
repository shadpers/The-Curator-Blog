@echo off
setlocal enabledelayedexpansion

:: Script para verificar integridade de arquivos .mkv usando FFmpeg
:: Uso: Arraste e solte arquivos .mkv sobre este script

:: Caminho do FFmpeg
set FFMPEG_PATH="C:\FFmpeg\bin\ffmpeg.exe"

:: Verifica se o FFmpeg existe
if not exist %FFMPEG_PATH% (
    echo ERRO: FFmpeg nao encontrado em %FFMPEG_PATH%
    echo Verifique se o caminho esta correto.
    pause
    exit /b 1
)

:: Verifica se algum arquivo foi arrastado
if "%~1"=="" (
    echo Este script deve ser usado arrastando arquivos .mkv sobre ele.
    echo.
    echo Como usar:
    echo 1. Selecione um ou mais arquivos .mkv
    echo 2. Arraste-os sobre este arquivo .bat
    echo 3. O script verificara a integridade de cada arquivo
    echo.
    pause
    exit /b 1
)

echo ========================================
echo  VERIFICADOR DE INTEGRIDADE MKV
echo ========================================
echo.

:: Contador de arquivos
set /a total_arquivos=0
set /a arquivos_ok=0
set /a arquivos_erro=0

:: Processa cada arquivo arrastado
:loop
if "%~1"=="" goto fim

set arquivo="%~1"
set /a total_arquivos+=1

echo [%total_arquivos%] Verificando: %~nx1
echo Caminho: %~1
echo.

:: Verifica se o arquivo existe
if not exist %arquivo% (
    echo ERRO: Arquivo nao encontrado!
    set /a arquivos_erro+=1
    echo.
    pause
    shift
    goto loop
)

:: Verifica se é um arquivo .mkv
echo %~x1 | findstr /i ".mkv" >nul
if errorlevel 1 (
    echo AVISO: Este arquivo nao possui extensao .mkv
    echo Continuando verificacao...
    echo.
)

:: Executa a verificação de integridade usando FFmpeg
echo Executando verificacao de integridade...
%FFMPEG_PATH% -v error -i %arquivo% -f null - 2>temp_error.log

:: Verifica o resultado
if errorlevel 1 (
    echo RESULTADO: ARQUIVO COM PROBLEMAS!
    echo.
    echo Detalhes dos erros encontrados:
    type temp_error.log
    set /a arquivos_erro+=1
) else (
    echo RESULTADO: ARQUIVO INTEGRO - OK!
    set /a arquivos_ok+=1
)

:: Limpa arquivo temporário
if exist temp_error.log del temp_error.log

echo.
echo ----------------------------------------
echo.
pause

shift
goto loop

:fim
echo ========================================
echo           RELATORIO FINAL
echo ========================================
echo Total de arquivos verificados: %total_arquivos%
echo Arquivos integros (OK): %arquivos_ok%
echo Arquivos com problemas: %arquivos_erro%
echo ========================================
echo.

if %arquivos_erro% gtr 0 (
    echo ATENCAO: Foram encontrados %arquivos_erro% arquivo(s) com problemas!
    echo Recomenda-se verificar ou reconverter estes arquivos.
) else (
    echo Todos os arquivos estao integros!
)

echo.
echo Pressione qualquer tecla para fechar...
pause >nul

