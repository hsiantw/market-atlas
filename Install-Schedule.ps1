$ErrorActionPreference = 'Stop'
$action = New-ScheduledTaskAction -Execute "$PSScriptRoot\.venv\Scripts\python.exe" -Argument ('"' + "$PSScriptRoot\market_data.py" + '" sync') -WorkingDirectory $PSScriptRoot
$trigger = New-ScheduledTaskTrigger -Daily -At '09:00'
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 12) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'MarketData-DailySync' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Update local stock and crypto daily datasets at 09:00 local time.' -Force
