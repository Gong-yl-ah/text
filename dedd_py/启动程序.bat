@echo off
chcp 936 >nul
cd /d "%~dp0"
set "PYCMD=D:\users\anaconda3\envs\dedd\python.exe"
"%PYCMD%" main.py
if errorlevel 1 (
    echo.
    echo 启动失败！请检查 Python 环境
    pause
)
