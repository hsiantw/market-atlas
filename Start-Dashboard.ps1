$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$address = 'http://127.0.0.1:8765'
try { $null = Invoke-WebRequest -Uri "$address/api/symbols" -UseBasicParsing -TimeoutSec 2 } catch {
    Start-Process -FilePath "$PSScriptRoot\.venv\Scripts\python.exe" -ArgumentList ('"' + "$PSScriptRoot\dashboard.py" + '"') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -RedirectStandardOutput "$PSScriptRoot\data\dashboard.log" -RedirectStandardError "$PSScriptRoot\data\dashboard-errors.log"
    Start-Sleep -Seconds 2
}
Start-Process $address
