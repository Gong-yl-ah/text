@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动 数字化美学牙科分析与设计 ...
python main.py
if errorlevel 1 (
  echo.
  echo 启动失败！请先安装依赖：python -m pip install -r requirements.txt
  pause
)
