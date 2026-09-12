#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Script = Join-Path $PSScriptRoot "run_xhs.ps1"
$TaskName = "ChinaDressRadar-XhsWeekly"

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`"" -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 9:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "Da tao lich '$TaskName': Chu nhat 09:00, chay bu neu may tat, khong chay song song."
Write-Host "Kiem tra: Get-ScheduledTask -TaskName $TaskName"
