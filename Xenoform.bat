@echo off
setlocal
cd /d "%~dp0"
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Xenoform needs its own Python 3.12 environment.
  echo Double-click install.bat first. It does not install into ComfyUI's Python.
  pause
  exit /b 1
)
if exist "%USERPROFILE%\AI\ComfyUI\models" set "XENO_MODELS=%USERPROFILE%\AI\ComfyUI\models"
set "XENO_ADDONS=0"
set "XENO_CONFIG="
if exist "%~dp0configs\local.json" set "XENO_CONFIG=--config configs\local.json"

rem Is the desk already up? curl the health route, then netstat.
set "UP="
curl.exe -fsS -o NUL --max-time 2 http://127.0.0.1:47317/api/v1/health
if not errorlevel 1 set "UP=1"
if not defined UP (
  netstat -ano -p tcp | findstr /C:":47317" | findstr /I /C:"LISTENING" >nul
  if not errorlevel 1 set "UP=1"
)
if defined UP (
  >> "%~dp0xenoform_duplicate.log" echo %DATE% %TIME% Desk already listening on 47317. Left the running server in place.
  start "" "http://127.0.0.1:47317/"
  exit /b 0
)

start "Xenoform" /MIN cmd /c ""%~dp0.venv\Scripts\python.exe" -m xenoform ui --host 127.0.0.1 --port 47317 %XENO_CONFIG% >> "%~dp0xenoform_server.log" 2>&1"
ping -n 3 127.0.0.1 >nul
start "" "http://127.0.0.1:47317/"
