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

rem Ports. Defaults: desk 47317, comfy-api-proxy 8189. Set XENO_PORT or XENO_PROXY_PORT first to use others.
if not defined XENO_PORT set "XENO_PORT=47317"
rem A moved proxy port is passed to the desk as XENO_PROXY_URL. The default leaves comfy.proxy_url in charge.
if defined XENO_PROXY_PORT (set "XENO_PROXY_URL=http://127.0.0.1:%XENO_PROXY_PORT%") else (set "XENO_PROXY_PORT=8189")
set "DESK=http://127.0.0.1:%XENO_PORT%"

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
  echo The desk is already running. Opening %DESK%
  start "" "%DESK%/"
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
  >> "%~dp0xenoform_proxy.log" echo %DATE% %TIME% comfy-api-proxy.exe is missing from .venv. Run install.bat again.
  goto desk
)
echo Starting comfy-api-proxy on port %XENO_PROXY_PORT% in front of ComfyUI on 8188. Log: xenoform_proxy.log
>> "%~dp0xenoform_proxy.log" echo %DATE% %TIME% Starting comfy-api-proxy on port %XENO_PROXY_PORT%.
start "Xenoform proxy" /MIN cmd /c ""%~dp0.venv\Scripts\comfy-api-proxy.exe" run --comfyui http://127.0.0.1:8188 --port %XENO_PROXY_PORT% >> "%~dp0xenoform_proxy.log" 2>&1"
set /a TRIES=0
:proxywait
netstat -ano -p tcp | findstr /C:":%XENO_PROXY_PORT% " | findstr /I /C:"LISTENING" >nul
if not errorlevel 1 goto desk
set /a TRIES+=1
if %TRIES% GEQ 15 (
  echo comfy-api-proxy did not start. See xenoform_proxy.log. The desk still opens, and dry runs still work.
  goto desk
)
ping -n 2 127.0.0.1 >nul
goto proxywait

:desk
echo Starting the desk on %DESK%. The first start writes the demo files and takes about 15 seconds.
start "Xenoform" /MIN cmd /c ""%~dp0.venv\Scripts\python.exe" -m xenoform ui --host 127.0.0.1 --port %XENO_PORT% %XENO_CONFIG% >> "%~dp0xenoform_server.log" 2>&1"
set /a TRIES=0
:deskwait
ping -n 2 127.0.0.1 >nul
curl.exe -fsS -o NUL --max-time 2 %DESK%/api/v1/health 2>nul
if not errorlevel 1 goto open
set /a TRIES+=1
if %TRIES% GEQ 60 (
  echo The desk did not answer after a minute. See xenoform_server.log.
  pause
  exit /b 1
)
goto deskwait

:open
if defined XENO_NO_BROWSER exit /b 0
start "" "%DESK%/"