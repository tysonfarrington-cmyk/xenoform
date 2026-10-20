@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" goto ready
echo.
echo  First run: Xenoform needs its own Python 3.12 environment (.venv in this folder).
echo  Setup takes about 5 minutes. It does not touch ComfyUI's Python or your models.
echo.
if defined XENO_YES goto setup
choice /C YN /T 30 /D Y /M "Set it up now? (starts by itself in 30 seconds)"
if errorlevel 2 (
  echo OK. Run install.bat or this file again when you are ready.
  pause
  exit /b 1
)
:setup
echo Running the installer...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo The installer stopped. The message above is the reason. Fix it and run Xenoform.bat again.
  pause
  exit /b 1
)
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo The installer finished but .venv is missing. See the messages above.
  pause
  exit /b 1
)
echo Setup done. Starting Xenoform.
:ready
if exist "%USERPROFILE%\AI\ComfyUI\models" set "XENO_MODELS=%USERPROFILE%\AI\ComfyUI\models"
set "XENO_ADDONS=0"
set "XENO_CONFIG="
if exist "%~dp0configs\local.json" set "XENO_CONFIG=--config configs\local.json"

rem Ports. Defaults: desk 47317, comfy-api-proxy 8189. Set XENO_PORT or XENO_PROXY_PORT first to use others.
if not defined XENO_PORT set "XENO_PORT=47317"
rem A moved proxy port is passed to the desk as XENO_PROXY_URL. The default leaves comfy.proxy_url in charge.
if defined XENO_PROXY_PORT (set "XENO_PROXY_URL=http://127.0.0.1:%XENO_PROXY_PORT%") else (set "XENO_PROXY_PORT=8189")
set "DESK=http://127.0.0.1:%XENO_PORT%"
rem Each running server holds its log open, so a desk or proxy on a moved port gets its own log.
set "SERVER_LOG=xenoform_server.log"
if not "%XENO_PORT%"=="47317" set "SERVER_LOG=xenoform_server_%XENO_PORT%.log"
set "PROXY_LOG=xenoform_proxy.log"
if not "%XENO_PROXY_PORT%"=="8189" set "PROXY_LOG=xenoform_proxy_%XENO_PROXY_PORT%.log"

rem Is the desk already up? curl the health route, then netstat.
set "UP="
curl.exe -fsS -o NUL --max-time 2 %DESK%/api/v1/health 2>nul
if not errorlevel 1 set "UP=1"
if not defined UP (
  netstat -ano -p tcp | findstr /C:":%XENO_PORT% " | findstr /I /C:"LISTENING" >nul
  if not errorlevel 1 set "UP=1"
)
if defined UP (
  >> "%~dp0xenoform_duplicate.log" echo %DATE% %TIME% Desk already listening on %XENO_PORT%. Left the running server in place.
  echo The desk is already running on %DESK%. Left it in place.
  if not defined XENO_NO_BROWSER start "" "%DESK%/"
  exit /b 0
)

rem Live renders go through comfy-sdk to comfy-api-proxy. Start it if it is not up.
netstat -ano -p tcp | findstr /C:":%XENO_PROXY_PORT% " | findstr /I /C:"LISTENING" >nul
if not errorlevel 1 (
  echo comfy-api-proxy is already running on port %XENO_PROXY_PORT%.
  goto desk
)
if not exist "%~dp0.venv\Scripts\comfy-api-proxy.exe" (
  echo comfy-api-proxy is not installed. Run install.bat again. The desk still opens, and dry runs still work.
  >> "%~dp0%PROXY_LOG%" echo %DATE% %TIME% comfy-api-proxy.exe is missing from .venv. Run install.bat again.
  goto desk
)
echo Starting comfy-api-proxy on port %XENO_PROXY_PORT% in front of ComfyUI on 8188. Log: %PROXY_LOG%
>> "%~dp0%PROXY_LOG%" echo %DATE% %TIME% Starting comfy-api-proxy on port %XENO_PROXY_PORT%.
start "Xenoform proxy" /MIN cmd /c ""%~dp0.venv\Scripts\comfy-api-proxy.exe" run --comfyui http://127.0.0.1:8188 --port %XENO_PROXY_PORT% >> "%~dp0%PROXY_LOG%" 2>&1"
set /a TRIES=0
:proxywait
netstat -ano -p tcp | findstr /C:":%XENO_PROXY_PORT% " | findstr /I /C:"LISTENING" >nul
if not errorlevel 1 goto desk
set /a TRIES+=1
if %TRIES% GEQ 15 (
  echo comfy-api-proxy did not start. See %PROXY_LOG%. The desk still opens, and dry runs still work.
  goto desk
)
ping -n 2 127.0.0.1 >nul
goto proxywait

:desk
echo Starting the desk on %DESK%. The first start writes the demo files and takes about 15 seconds.
start "Xenoform" /MIN cmd /c ""%~dp0.venv\Scripts\python.exe" -m xenoform ui --host 127.0.0.1 --port %XENO_PORT% %XENO_CONFIG% >> "%~dp0%SERVER_LOG%" 2>&1"
set /a TRIES=0
:deskwait
ping -n 2 127.0.0.1 >nul
curl.exe -fsS -o NUL --max-time 2 %DESK%/api/v1/health 2>nul
if not errorlevel 1 goto open
set /a TRIES+=1
if %TRIES% GEQ 30 (
  echo The desk did not answer after about 90 seconds. See %SERVER_LOG%.
  if not defined XENO_NO_BROWSER pause
  exit /b 1
)
goto deskwait

:open
if defined XENO_NO_BROWSER exit /b 0
start "" "%DESK%/"