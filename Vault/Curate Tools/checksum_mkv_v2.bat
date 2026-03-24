@echo off
setlocal enabledelayedexpansion

chcp 1252 >nul

echo Comparando os arquivos:
echo   Arquivo 1: %~nx1
echo   Arquivo 2: %~nx2
echo.

:: Verifica se dois arquivos foram fornecidos
if "%~2"=="" (
    echo ERRO: Arraste DOIS arquivos sobre este script.
    pause
    exit /b
)

echo Calculando o checksum SHA256 do primeiro arquivo...
certutil -hashfile "%~1" SHA256 > hash1.txt

echo Calculando o checksum SHA256 do segundo arquivo...
certutil -hashfile "%~2" SHA256 > hash2.txt

set "hash1="
set "hash2="

for /f "skip=1 tokens=*" %%a in (hash1.txt) do (
    if not defined hash1 set "hash1=%%a"
)

for /f "skip=1 tokens=*" %%b in (hash2.txt) do (
    if not defined hash2 set "hash2=%%b"
)

echo.
echo Checksum do Arquivo 1: !hash1!
echo Checksum do Arquivo 2: !hash2!
echo.

if /i "!hash1!"=="!hash2!" (
    echo RESULTADO: Os arquivos sao IDENTICOS.
) else (
    echo RESULTADO: Os arquivos sao DIFERENTES.
)

del hash1.txt >nul
del hash2.txt >nul

pause
