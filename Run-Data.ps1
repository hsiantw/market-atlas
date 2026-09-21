param([ValidateSet('sync','status','export')][string]$Command = 'sync')
$ErrorActionPreference = 'Stop'
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\market_data.py" $Command
exit $LASTEXITCODE
