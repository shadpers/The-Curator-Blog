@echo off
chcp 65001 >nul
python "%~dp0anchor_frame_sync.py" %*
pause
