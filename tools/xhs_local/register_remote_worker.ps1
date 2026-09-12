#Requires -Version 5.1
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Worker = Join-Path $PSScriptRoot "remote_worker.py"
$TaskName = "TisoraRadar-RedNoteRemote"

if (-not (Test-Path $Python)) { throw "Không thấy Python tại $Python" }
$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Worker`"" -WorkingDirectory $ProjectRoot
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
Write-Host "Đã bật bộ nhận lệnh RedNote. Website sẽ được kiểm tra mỗi phút khi bạn đăng nhập Windows."
