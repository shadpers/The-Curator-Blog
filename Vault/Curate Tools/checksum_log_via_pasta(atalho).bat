@echo off
chcp 1252 >nul
setlocal EnableDelayedExpansion

if "%~1"=="" (
    echo Arraste um atalho .lnk sobre este script.
    pause
    exit /b
)

set "lnk_path=%~1"

echo Resolvendo o atalho para a pasta...

:: Obter caminho real da pasta via PowerShell
for /f "delims=" %%a in (
    'powershell -nologo -command "(New-Object -ComObject WScript.Shell).CreateShortcut('%lnk_path%').TargetPath"'
) do set "target_folder=%%a"

if not exist "%target_folder%" (
    echo ERRO: A pasta de destino nao existe: %target_folder%
    pause
    exit /b
)

:: Extrair apenas o nome da pasta final para nomear o log
for %%b in ("%target_folder%") do set "folder_name=%%~nxb"
set "log_file=checksum_!folder_name!.txt"

echo Gerando log de checksums para arquivos em: %target_folder%

:: Limpa o arquivo de log se ele existir
del "!log_file!" 2>nul

:: Itera sobre todos os arquivos na pasta de destino e calcula o SHA256
for /r "%target_folder%" %%f in (*) do (
    set "file_path=%%f"
    set "file_name=%%~nxf"
    echo Processando: !file_name!

    for /f "delims=" %%h in (
        'certutil -hashfile "!file_path!" SHA256 ^| find /i /v "hash"'
    ) do set "file_hash=%%h"

    echo !file_name!: !file_hash! >> "!log_file!"
)

echo.
echo Processo concluido. O log foi salvo em: !log_file!
pause
