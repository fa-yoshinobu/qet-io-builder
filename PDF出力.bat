@echo off
rem .qet を QElectroTech で開いて PDF に書き出し、A3 横にそろえる。
rem 使い方: この .bat に .qet ファイルをドラッグ&ドロップする(または PDF出力.bat 図面.qet)
rem 実行中の数十秒は QElectroTech が画面に出るので、終わるまで操作しないこと。
cd /d "%~dp0"
python -c "import pywinauto, pypdf" 2>nul || python -m pip install --user pywinauto pypdf
if "%~1"=="" (
  echo .qet ファイルをこの .bat にドラッグしてください。
  pause
  exit /b 1
)
python tools\qet_export_pdf.py "%~1" %2
if errorlevel 1 pause
