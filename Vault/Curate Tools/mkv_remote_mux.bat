@echo off
chcp 65001 > nul

echo ============================================================
echo   MKV Remote Mux - Extracao de Faixas via CDN
echo ============================================================
echo.

REM Roda no diretorio atual (onde o .bat foi executado)
cd /d "%~dp0"

REM Chama o script Python
"C:\Python313\python.exe" "%~dp0mkv_remote_mux.py" %*

echo.
pause
