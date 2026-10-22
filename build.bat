@echo off
REM 桌面划词翻译 — 一键打包脚本（onedir 单目录，无控制台）
setlocal
set VENV_PY=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe
set PIP=%VENV_PY% -m pip

echo [1/2] 安装 PyInstaller ...
%PIP% install pyinstaller
if errorlevel 1 (echo 安装 PyInstaller 失败 & exit /b 1)

echo [2/2] 打包中（onedir / 无控制台 / 中文名=划词翻译）...
%VENV_PY% -m PyInstaller --noconsole --onedir -y --name 划词翻译 ^
  --add-data "assets;assets" ^
  --icon "assets\app_icon.ico" ^
  --hidden-import=pynput.keyboard._win32 ^
  --hidden-import=pynput.mouse._win32 ^
  --hidden-import=keyboard ^
  main.pyw
if errorlevel 1 (echo 打包失败 & exit /b 1)

echo 完成！产物位于 dist\划词翻译\划词翻译.exe
endlocal
