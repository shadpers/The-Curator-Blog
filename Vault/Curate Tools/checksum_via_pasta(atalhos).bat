@echo off
chcp 1252 >nul
setlocal EnableDelayedExpansion

if "%~2"=="" (
    echo Arraste dois atalhos .lnk sobre este script.
    pause
    exit /b
)

echo Resolvido os atalhos para pastas...

:: Obter caminhos reais das pastas via PowerShell
for /f "delims=" %%a in ('powershell -nologo -command "(New-Object -ComObject WScript.Shell).CreateShortcut('%~1').TargetPath"') do set "pasta1=%%a"
for /f "delims=" %%b in ('powershell -nologo -command "(New-Object -ComObject WScript.Shell).CreateShortcut('%~2').TargetPath"') do set "pasta2=%%b"

if not exist "!pasta1!" (
    echo ERRO: Pasta 1 nao existe: !pasta1!
    pause
    exit /b
)
if not exist "!pasta2!" (
    echo ERRO: Pasta 2 nao existe: !pasta2!
    pause
    exit /b
)

echo.
echo Comparando arquivos .MKV com nomes iguais...
echo.

set "erros=0"
for %%f in ("!pasta1!\*.mkv") do (
    set "arquivo=%%~nxf"
    if exist "!pasta2!\!arquivo!" (
        echo Comparando: !arquivo!

        for /f "delims=" %%h in ('certutil -hashfile "!pasta1!\!arquivo!" SHA256 ^| find /i /v "hash"') do set "hash1=%%h"
        for /f "delims=" %%h in ('certutil -hashfile "!pasta2!\!arquivo!" SHA256 ^| find /i /v "hash"') do set "hash2=%%h"

        if /i "!hash1!"=="!hash2!" (
            echo OK: Os arquivos sao IDENTICOS.
        ) else (
            echo ERRO: Os arquivos sao DIFERENTES!
            set /a erros+=1
        )
        echo.
    ) else (
        echo Aviso: Arquivo !arquivo! nao existe na pasta 2.
        echo.
    )
)

echo ===============================
if "!erros!"=="0" (
    echo ✅ Todos os arquivos coincidem!
) else (
    echo ⚠ Foram encontrados !erros! arquivos diferentes.
)
echo ===============================
pause
