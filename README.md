# Stock and crypto datasets

The main pipeline is `market_data.py`. Daily history is stored in **data/market.sqlite** and exported to **data/exports/** as one CSV per symbol. No editor extensions are required.

## Web interface

Open **http://127.0.0.1:8765** while the dashboard is running. To launch it again:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Start-Dashboard.ps1
```

Search by company or ticker, filter stocks/crypto, save favorites, select date ranges, inspect the chart, page through daily records, and export the selected range. Favorites are stored in your browser. The refresh button reloads the local dataset; it does not start a market download. The website is served only on this computer and reads SQLite without changing prices. No internet connection or frontend dependencies are needed to view existing data. Company names are cached during S&P 500 universe refreshes.

To run in a terminal instead: `.\.venv\Scripts\python.exe dashboard.py` (Ctrl+C stops it). Browser smoke tests use the optional packages in `requirements-dev.txt` and your installed Microsoft Edge.

## Run

```powershell
.\.venv\Scripts\python.exe market_data.py sync
.\.venv\Scripts\python.exe market_data.py status
.\.venv\Scripts\python.exe market_data.py export
.\.venv\Scripts\python.exe market_data.py sync --symbols AAPL 2330.TW BTC-USD ETH-USD
.\.venv\Scripts\python.exe market_data.py sync --full
```

Edit `config.json` to add Yahoo Finance symbols or disable S&P 500 collection. Defaults are current S&P 500 constituents plus your existing Taiwan and crypto symbols. Share-class dots become Yahoo hyphens. A cached constituent list is used with a warning on source failure. Membership observations are saved from now onward; historical membership is not reconstructed. Previously tracked symbols continue after index removal.

## Reliability

- Initial downloads request maximum available daily history. Updates overlap the last 14 days. Complete history refreshes every 30 days and when recent corporate actions appear, to reconcile adjustments.
- Each symbol commits atomically. A `(symbol,date)` primary key prevents duplicates. Short provider responses do not delete existing history.
- Successful symbols are skipped on repeated runs on the same UTC date, unless a full refresh is due or `--full` is used. Failed symbols retry on the next run.
- Sequential requests, pauses, three attempts, and exponential retry delays reduce request pressure. An OS lock prevents simultaneous ingestion jobs.
- Current exchange-local dates are excluded. Entirely empty OHLC records are counted and omitted. Partial OHLC and invalid volume fail the symbol.
- `state` stores successful refresh timestamps and errors; `attempts` records results. Progress is in `data/ingestion.log`.
- CSV export streams from SQLite and replaces files atomically. Run `export` to regenerate CSVs after interruption.

The prices table includes OHLC, adjusted close, volume, dividends, splits, currency, exchange, timezone, source and fetch timestamp. Yahoo prices follow its adjustment conventions; `auto_adjust=False` preserves adjusted close separately. This is not a point-in-time vintage database.

## Daily schedule

`Install-Schedule.ps1` registers **MarketData-DailySync** at **09:00 computer-local time**, while the current user is logged in. Missed starts run when available. The computer must be on and connected. Check Windows Task Scheduler and the ingestion log for results.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\Install-Schedule.ps1
```

## Analyze

Open CSVs in `data/exports/` or query SQLite:

```python
import sqlite3
import pandas as pd
with sqlite3.connect('data/market.sqlite') as db:
    prices = pd.read_sql_query(
        'SELECT date, close, adjusted_close, volume FROM prices WHERE symbol=? ORDER BY date',
        db, params=('AAPL',))
print(prices.tail())
```

Use SQLite's backup API for backups while ingestion runs; copying only the database file can omit WAL transactions.

## Scope

All data means all available **daily OHLCV and corporate-action history for configured symbols**. It excludes intraday data, fundamentals, every global asset, and historical delisted index constituents. Yahoo/yfinance availability and completeness are not guaranteed. Successful ingestion verifies storage of valid returned records, not every expected trading session. Missing sessions and provider truncation require a separate exchange-calendar/provider audit for research requiring guaranteed completeness.

The old PowerShell downloaders and `data/*.csv` remain legacy files. Use this pipeline and `data/exports/` for ongoing data.

## Re-create environment

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m unittest -v
```

Sources: https://ranaroussi.github.io/yfinance/ and https://github.com/datasets/s-and-p-500-companies
