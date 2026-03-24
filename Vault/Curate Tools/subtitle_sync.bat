@echo off

echo ========================================
echo  Subtitle Sync - Drag and Drop
echo ========================================
echo.

REM Verifica se há arquivos arrastados
if "%~1"=="" (
    echo [ERRO] Nenhum arquivo foi arrastado!
    echo.
    echo Como usar:
    echo 1. Arraste um ou mais arquivos MKV sobre este .bat
    echo 2. Siga as instrucoes no console
    pause
    exit /b
)

REM Chama o script Python passando todos os argumentos
"C:\Python313\python.exe" "%~dp0subtitle_sync.py" %*

pause