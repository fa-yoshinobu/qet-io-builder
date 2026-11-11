@echo off
cd /d "%~dp0"
python runtime_check.py
if errorlevel 1 (
  pause
  exit /b 1
)
python -c "import webview" 2>nul
if errorlevel 1 (
  echo Installing pywebview ^(first time only^)...
  python -m pip install pywebview
)
python gui_web.py
if errorlevel 1 pause
