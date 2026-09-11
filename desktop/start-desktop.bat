@echo off
setlocal
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Chua co moi truong Python. Chay:
  echo   py -3.11 -m venv .venv
  echo   .venv\Scripts\pip.exe install -r requirements.txt
  pause
  exit /b 1
)
where npm >nul 2>nul
if errorlevel 1 (
  echo Can cai Node.js de chay Electron: https://nodejs.org
  pause
  exit /b 1
)
if not exist "node_modules\electron" (
  call npm install
)
call npm start
