param(
    [Parameter(Mandatory = $true)][string]$Symbol,
    [datetime]$Start = [datetime]'1970-01-01',
    [datetime]$End = (Get-Date).Date.AddDays(-1),
    [string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
if (!$OutputDirectory) { $OutputDirectory = Join-Path $PSScriptRoot 'data' }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Symbol = $Symbol.Trim().ToUpperInvariant()
if ($Symbol -notmatch '^[A-Z0-9^][A-Z0-9.^=_-]*$') { throw 'Enter a valid Yahoo Finance ticker, such as AAPL or 2330.TW.' }
if ($Start.Date -gt $End.Date) { throw 'Start must be on or before End.' }
if ($End.Date -ge (Get-Date).Date) { throw 'End must be before today to avoid saving an unfinished trading day.' }

# Pad the UTC request window; filter by the exchange-local trading date below.
$epoch = [datetimeoffset]'1970-01-01T00:00:00Z'
$from = [datetimeoffset]::new([datetime]::SpecifyKind($Start.Date, [DateTimeKind]::Utc)).AddDays(-1).ToUnixTimeSeconds()
$until = [datetimeoffset]::new([datetime]::SpecifyKind($End.Date, [DateTimeKind]::Utc)).AddDays(2).ToUnixTimeSeconds()
$encoded = [uri]::EscapeDataString($Symbol)
$uri = "https://query1.finance.yahoo.com/v8/finance/chart/${encoded}?period1=$from&period2=$until&interval=1d"
$response = Invoke-RestMethod -Uri $uri -UserAgent 'Mozilla/5.0' -TimeoutSec 60
if ($response.chart.error) { throw ($response.chart.error | ConvertTo-Json -Compress) }
$result = $response.chart.result | Select-Object -First 1
if (!$result -or !$result.timestamp) { throw "No daily prices returned for $Symbol. No file was changed." }
$quotes = $result.indicators.quote[0]
$adjusted = $result.indicators.adjclose | Select-Object -First 1
$offset = [double]$result.meta.gmtoffset
$emptyDates = 0
$rows = @(
    for ($i = 0; $i -lt $result.timestamp.Count; $i++) {
        $date = $epoch.AddSeconds([double]$result.timestamp[$i] + $offset).ToString('yyyy-MM-dd')
        if ($date -lt $Start.ToString('yyyy-MM-dd') -or $date -gt $End.ToString('yyyy-MM-dd')) { continue }
        if ($null -eq $quotes.open[$i] -and $null -eq $quotes.high[$i] -and $null -eq $quotes.low[$i] -and $null -eq $quotes.close[$i]) {
            $emptyDates++
            continue
        }
        foreach ($field in @('open', 'high', 'low', 'close', 'volume')) {
            if ($null -eq $quotes.$field[$i]) { throw "Missing $field on $date. No file was changed." }
        }
        [pscustomobject][ordered]@{
            symbol = $Symbol
            date = $date
            open = $quotes.open[$i]
            high = $quotes.high[$i]
            low = $quotes.low[$i]
            close = $quotes.close[$i]
            adjusted_close = $(if ($adjusted) { $adjusted.adjclose[$i] } else { $null })
            volume = $quotes.volume[$i]
            currency = $result.meta.currency
            exchange = $result.meta.exchangeName
            source = 'Yahoo Finance'
        }
    }
)
if (!$rows.Count) { throw 'No prices in the requested date range. No file was changed.' }
if (@($rows.date | Select-Object -Unique).Count -ne $rows.Count) { throw 'Provider returned duplicate trading dates.' }
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$path = Join-Path $OutputDirectory "$Symbol.csv"
$temporary = "$path.$([guid]::NewGuid().ToString('N')).tmp"
try {
    $rows | Sort-Object date | Export-Csv -LiteralPath $temporary -NoTypeInformation -Encoding UTF8
    $saved = @(Import-Csv -LiteralPath $temporary)
    if ($saved.Count -ne $rows.Count) { throw 'Saved row count does not match downloaded row count.' }
    Move-Item -LiteralPath $temporary -Destination $path -Force
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary }
}
Write-Output "Saved $($saved.Count) daily prices for $Symbol, $($saved[0].date) through $($saved[-1].date), to $path"
if ($emptyDates) { Write-Warning "Provider returned $emptyDates dates with no OHLC prices; these were omitted, not filled with invented prices." }
Write-Output 'Verified: all returned rows in the requested range were saved. Provider completeness is not independently verified.'
