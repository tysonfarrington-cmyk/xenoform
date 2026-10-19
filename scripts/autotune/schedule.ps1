# Registers the one-off overnight auto-tune task (interactive user, no stored password).
# Start 23:00 tonight; the runner stops itself at 06:30 and Task Scheduler kills it at 06:40 at the latest.
param([string]$Date = (Get-Date).ToString("yyyy-MM-dd"))
$name = "XenoformAutotune"
$bat = "C:\Projects\xenoform-judge-test\scripts\autotune\run_overnight.bat"
$start = [datetime]::ParseExact("$Date 23:00", "yyyy-MM-dd HH:mm", $null)
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`"" -WorkingDirectory "C:\Projects\xenoform-judge-test"
$trigger = New-ScheduledTaskTrigger -Once -At $start
$trigger.EndBoundary = $start.AddHours(7).AddMinutes(40).ToString("s")
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 7 -Minutes 40) `
  -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew `
  -DeleteExpiredTaskAfter (New-TimeSpan -Days 2)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
  -Description "Xenoform morph auto-tune (scripts/autotune). Hard stop 06:30." -Force | Out-Null
Get-ScheduledTask -TaskName $name | Get-ScheduledTaskInfo | Select-Object TaskName, NextRunTime | Format-List
