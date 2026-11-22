@echo off
rem Double-click to read your Canon shutter count. Open this file in Notepad to see exactly what it does.
setlocal
cd /d "%~dp0"

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY (
  echo Python 3 isn't installed.
  echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH",
  echo or open a terminal and run:  winget install Python.Python.3.13
  echo Then double-click run.bat again.
  echo.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up a private Python environment in this folder. This takes a minute.
  %PY% -m venv .venv || goto :fail
  ".venv\Scripts\python.exe" -m pip install --quiet --disable-pip-version-check comtypes || goto :fail
  echo.
)

".venv\Scripts\python.exe" shutter_count.py
echo.
pause
exit /b 0

:fail
echo.
echo Setup failed. See the messages above.
pause
exit /b 1
