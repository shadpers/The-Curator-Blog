@echo off
setlocal enabledelayedexpansion

:: Configura codificação UTF-8
chcp 65001 >nul

:: Caminho do Python e do script
set PYTHON_SCRIPT=%~dp0testar_videos.py
set FILELIST=%~dp0filelist.txt

:: Verifica se o Python está instalado
where python >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Erro: Python não encontrado. Instale o Python e tente novamente.
    pause
    exit /b
)

:: Verifica e instala dependências (tqdm, colorama, tabulate)
python -m pip show tqdm >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Instalando módulo tqdm...
    python -m pip install tqdm
)

python -m pip show colorama >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Instalando módulo colorama...
    python -m pip install colorama
)

python -m pip show tabulate >nul 2>nul
if %ERRORLEVEL% neq 0 (
    echo Instalando módulo tabulate...
    python -m pip install tabulate
)

:: Cria lista de vídeos na pasta atual
del "%FILELIST%" 2>nul
for %%f in (*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm) do (
    echo %%f >> "%FILELIST%"
)

:: Chama o Python (com opção --only-failures e --workers opcional)
python "%PYTHON_SCRIPT%" "%FILELIST%" %*

pause