@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
  echo.
  echo The installer stopped. The message above is the reason.
  pause
  exit /b 1
)
echo.
if defined XENO_NO_LAUNCH exit /b 0
if defined XENO_YES goto launch
choice /C YN /T 15 /D Y /M "Setup done. Start Xenoform now? (starts by itself in 15 seconds)"
if errorlevel 2 exit /b 0
:launch
call "%~dp0Xenoform.bat"
