@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

:: srt_style_mux.bat
:: Arraste qualquer combinacao de .mkv / .ass / .ttf (ou .otf) neste .bat.
:: A ordem dos arquivos nao importa -- o script detecta cada um pela extensao.
:: O .ttf/.otf e opcional (fonte sera embedada se fornecida).

set "MKV="
set "REF="
set "TTF="

:parse
if "%~1"=="" goto done
set "EXT=%~x1"
if /I "!EXT!"==".mkv" set "MKV=%~1"
if /I "!EXT!"==".ass" set "REF=%~1"
if /I "!EXT!"==".ttf" set "TTF=%~1"
if /I "!EXT!"==".otf" set "TTF=%~1"
shift
goto parse
:done

if "%MKV%"=="" set "MKV=entrada.mkv"
if "%REF%"=="" set "REF=estilo_referencia.ass"

echo.
echo  MKV    : "%MKV%"
echo  Estilo : "%REF%"
if not "%TTF%"=="" echo  Fonte  : "%TTF%"
echo.

if "%TTF%"=="" (
    python srt_style_mux.py "%MKV%" "%REF%"
) else (
    python srt_style_mux.py "%MKV%" "%REF%" "%TTF%"
)

echo.
pause
