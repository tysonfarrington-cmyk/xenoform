@echo off
rem Overnight morph auto-tune: 23:00 start (scheduled task), hard stop 06:30. Resumable.
cd /d C:\Projects\xenoform-judge-test
if not exist judge_logs\autotune\night mkdir judge_logs\autotune\night
echo %DATE% %TIME% runner start >> judge_logs\autotune\night\runner.log
set COMFY_API_KEY=
set HF_TOKEN=
set HF_HUB_OFFLINE=1
C:\Projects\xenoform-judge-test\.venv\Scripts\python.exe scripts\autotune\autotune.py --until 06:30 --out judge_logs\autotune\night >> judge_logs\autotune\night\runner.log 2>&1
echo %DATE% %TIME% runner exit %ERRORLEVEL% >> judge_logs\autotune\night\runner.log
