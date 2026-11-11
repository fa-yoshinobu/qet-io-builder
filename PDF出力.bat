@echo off
rem JSON/QET to A3 PDF, or --manufacturer NAME --output-dir DIR.
cd /d "%~dp0"
python -c "import pypdf" 2>nul || python -m pip install --user pypdf
if "%~1"=="" (
  echo Drop a .json or .qet file here, or specify --manufacturer NAME.
  pause
  exit /b 1
)
python tools\qet_export_pdf.py %*
set result=%errorlevel%
if not "%result%"=="0" pause
exit /b %result%
