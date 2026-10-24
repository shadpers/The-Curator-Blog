@echo off

echo ========================================
echo  MKV Cover - Drag and Drop
echo ========================================
echo.

REM Verifica se ha arquivos arrastados
if "%~1"=="" (
    echo [ERRO] Nenhum arquivo foi arrastado!
    echo.
    echo Como usar:
    echo 1. ADICIONAR capa: arraste MKVs + uma imagem sobre este .bat
    echo 2. EXTRAIR capas: arraste so MKVs ^(ou uma pasta de MKVs^)
    echo 3. Siga as instrucoes no console
    pause
    exit /b
)

REM Chama o script Python passando todos os argumentos
"C:\Python313\python.exe" "%~dp0mkv_cover.py" %*

pause
