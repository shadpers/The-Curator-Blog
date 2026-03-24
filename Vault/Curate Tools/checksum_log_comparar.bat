@echo off
chcp 1252 >nul
setlocal EnableDelayedExpansion

:: Verificar se dois arquivos foram fornecidos via drag-and-drop
if "%~2"=="" (
    echo Arraste dois arquivos .txt sobre este script.
    pause
    exit /b
)

:: Definir os caminhos dos arquivos de checksum
set "file1=%~1"
set "file2=%~2"

:: Verificar se os arquivos existem
if not exist "%file1%" (
    echo ERRO: O arquivo "%file1%" nao existe.
    pause
    exit /b
)
if not exist "%file2%" (
    echo ERRO: O arquivo "%file2%" nao existe.
    pause
    exit /b
)

:: Verificar se os arquivos têm extensão .txt
if /i not "%~x1"==".txt" (
    echo ERRO: O primeiro arquivo nao e um .txt.
    pause
    exit /b
)
if /i not "%~x2"==".txt" (
    echo ERRO: O segundo arquivo nao e um .txt.
    pause
    exit /b
)

echo Comparando checksums entre:
echo "%file1%"
echo "%file2%"
echo.

:: Criar arquivos temporários para armazenar os pares arquivo:hash
set "temp1=%temp%\temp1_%random%.txt"
set "temp2=%temp%\temp2_%random%.txt"

:: Limpar arquivos temporários, se existirem
del "%temp1%" "%temp2%" 2>nul

:: Processar os arquivos de checksum com type para evitar problemas com caracteres especiais
type "%file1%" | findstr /r /c:".*:.*" > "%temp1%"
if errorlevel 1 (
    echo ERRO: Nao foi possivel processar o arquivo "%file1%".
    pause
    exit /b
)

type "%file2%" | findstr /r /c:".*:.*" > "%temp2%"
if errorlevel 1 (
    echo ERRO: Nao foi possivel processar o arquivo "%file2%".
    pause
    exit /b
)

:: Verificar se os arquivos temporários foram criados
if not exist "%temp1%" (
    echo ERRO: Arquivo temporario "%temp1%" nao foi criado.
    pause
    exit /b
)
if not exist "%temp2%" (
    echo ERRO: Arquivo temporario "%temp2%" nao foi criado.
    pause
    exit /b
)

:: Comparar os arquivos
set "differences=0"
for /f "tokens=1,* delims=:" %%a in (%temp1%) do (
    set "filename=%%a"
    set "hash1=%%b"
    :: Remover espaços extras
    for %%c in (!hash1!) do set "hash1=%%c"
    set "found=0"
    
    :: Procurar o mesmo arquivo no segundo arquivo
    for /f "tokens=1,* delims=:" %%d in (%temp2%) do (
        if "!filename!"=="%%d" (
            set "found=1"
            set "hash2=%%e"
            :: Remover espaços extras
            for %%f in (!hash2!) do set "hash2=%%f"
            if not "!hash1!"=="!hash2!" (
                echo Diferenca encontrada em: !filename!
                echo Hash em "%file1%": !hash1!
                echo Hash em "%file2%": !hash2!
                echo.
                set /a differences+=1
            )
        )
    )
    
    if !found! equ 0 (
        echo Arquivo "!filename!" encontrado apenas em "%file1%"
        echo.
        set /a differences+=1
    )
)

:: Verificar arquivos que estão apenas no segundo arquivo
for /f "tokens=1 delims=:" %%a in (%temp2%) do (
    set "filename=%%a"
    set "found=0"
    for /f "tokens=1 delims=:" %%b in (%temp1%) do (
        if "!filename!"=="%%b" set "found=1"
    )
    if !found! equ 0 (
        echo Arquivo "!filename!" encontrado apenas em "%file2%"
        echo.
        set /a differences+=1
    )
)

:: Resultado final
echo.
if %differences% equ 0 (
    echo Todos os arquivos correspondentes possuem hashes identicos!
) else (
    echo Foram encontradas %differences% diferencas.
)

:: Limpar arquivos temporários
del "%temp1%" "%temp2%" 2>nul

pause