param(
    [string[]]$Symbols = @('AAPL', '2330.TW', 'BTC-USD', 'ETH-USD')
)

$ErrorActionPreference = 'Stop'
$failed = @()
foreach ($ticker in $Symbols) {
    try {
        & (Join-Path $PSScriptRoot 'Download-Stock.ps1') -Symbol $ticker
    } catch {
        Write-Warning "$ticker failed: $_"
        $failed += $ticker
    }
}
if ($failed.Count) { throw "Downloads failed for: $($failed -join ', '). Successful downloads were saved." }
