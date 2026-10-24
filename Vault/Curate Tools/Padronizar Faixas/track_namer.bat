@echo off
chcp 65001 > nul 2>&1

echo ========================================
echo  Track Namer - Padronizacao de Faixas
echo ========================================
echo.
echo  Ordem ja correta: edita o MKV in-place (sem remux).
echo  Ordem diferente: pergunta se remuxa ou so renomeia in-place.
echo.

if "%~1"=="" (
    echo [ERRO] Nenhum arquivo ou pasta foi arrastado!
    echo.
    echo Como usar:
    echo   1. Arraste um ou mais arquivos .mkv sobre este .bat
    echo   2. Ou arraste pastas contendo arquivos .mkv
    echo   3. Siga as instrucoes no console
    echo.
    pause
    exit /b
)

"C:\Python313\python.exe" "%~dp0track_namer.py" %*
