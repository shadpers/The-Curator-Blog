@echo off
chcp 65001 > nul 2>&1

echo ========================================
echo  Mass Mux - Batch MKV Processing
echo ========================================
echo.

REM Verifica se ha pastas/atalhos arrastados
if "%~1"=="" (
    echo [ERRO] Nenhuma pasta foi arrastada!
    echo.
    echo Como usar:
    echo 1. Arraste uma ou mais PASTAS sobre este .bat
    echo 2. Cada pasta deve conter episodios MKV
    echo 3. Todas as pastas devem ter a mesma quantidade de episodios
    echo 4. Siga as instrucoes no console
    pause
    exit /b
)

REM Chama o script Python passando todos os argumentos
"C:\Python313\python.exe" "%~dp0mass_mux.py" %*

pause
