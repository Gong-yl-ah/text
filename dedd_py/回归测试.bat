@echo off
chcp 936 >nul
cd /d "%~dp0"
set "PYCMD=D:\users\anaconda3\envs\dedd\python.exe"
echo ============================================
echo   AI 牙位检测 回归测试
echo   照片请放入 样本库\口内\ 和 样本库\正面\
echo ============================================
echo.
"%PYCMD%" -X utf8 _regress.py
echo.
echo 结果已保存到 _regress_out\ 文件夹
explorer "%~dp0_regress_out"
pause
