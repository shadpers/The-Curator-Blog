@echo off
REM ====================================================================
REM  HASH CHECKER - Launcher
REM  Drag and drop a file over this .bat to verify MD5 and SHA256 hashes
REM ====================================================================

SETLOCAL EnableDelayedExpansion

REM Check if a file was provided
if "%~1"=="" (
    echo.
    echo  ========================================================
    echo   HASH CHECKER - MD5 and SHA256
    echo  ========================================================
    echo.
    echo  HOW TO USE:
    echo  Drag and drop a file over this .bat script
    echo.
    echo  The script will calculate MD5 and SHA256 hashes
    echo  and save the result to a text file.
    echo.
    echo  ========================================================
    echo.
    pause
    exit /b
)

REM Get the directory where this .bat is located
set "SCRIPT_DIR=%~dp0"
set "PS1_SCRIPT=%SCRIPT_DIR%Hash_Checker.ps1"

REM Check if the PowerShell script exists
if not exist "!PS1_SCRIPT!" (
    echo.
    echo  ========================================================
    echo   ERROR
    echo  ========================================================
    echo.
    echo  PowerShell script not found:
    echo  !PS1_SCRIPT!
    echo.
    echo  Make sure Hash_Checker.ps1 is in the same folder as this .bat
    echo.
    echo  ========================================================
    echo.
    pause
    exit /b
)

REM Execute PowerShell script with the file path
powershell -NoProfile -ExecutionPolicy Bypass -File "!PS1_SCRIPT!" -FilePath "%~1"

REM Keep window open if there was an error
if !errorlevel! neq 0 (
    echo.
    echo An error occurred. Press any key to close...
    pause > nul
)