@echo off
setlocal

:: Verifica se arquivo foi arrastado
if "%~1"=="" (
    echo Drag and drop a file onto this .bat
    pause
    exit /b
)

:: Get the folder of the .bat / .ps1
set "ScriptDir=%~dp0"
set "PS1=%ScriptDir%DefenderScan.ps1"

:: Run PowerShell passing the file path as argument (PowerShell will handle the quotes)
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PS1%" -Arquivo %1

pause
endlocal