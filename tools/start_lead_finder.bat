@echo off
REM Lead Finder - double-click to start. The app opens in your web browser.
cd /d "%~dp0"
if not exist "python\python.exe" (
  echo This folder is missing its "python" subfolder.
  echo Download the full LeadFinder-Windows.zip again and unzip all of it.
  pause
  exit /b 1
)
echo Starting Lead Finder... your browser will open in a moment.
echo Keep this window open while you use the tool. Close it to stop Lead Finder.
echo.
"python\python.exe" -m streamlit run streamlit_app.py --server.headless false --browser.gatherUsageStats false --server.fileWatcherType none
pause
