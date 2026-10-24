@echo off
chcp 65001 >nul
cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo  [!] Nenhum arquivo foi arrastado.
    echo      Arraste o .ass, a fonte .ttf/.otf ^(opcional^) e os .mkv juntos.
    echo.
    pause
    exit /b
)

python "%~dp0srt_style_mux.py" %*

echo.
echo  Processo encerrado. Os MKVs estilizados estao na pasta styled\
echo.
pause
