@echo off
chcp 936 >nul
cd /d "%~dp0"
set "PYCMD=python"
where python >nul 2>nul || set "PYCMD=C:\Users\Gong\AppData\Local\DoubaoWork\User Data\sandbox_runtime\bases\c98c5042338ed152c6f10ecd8591889f\python\python.exe"
"%PYCMD%" main.py
if errorlevel 1 (
    echo.
    echo 启动失败！请检查 Python 环境
    pause
)
