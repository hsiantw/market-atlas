"""Resumable daily Yahoo Finance ingestion. Run --help for commands."""
import argparse
import csv
import io
import json
import logging
import math
import sqlite3
import sys
import time
import urllib.request
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
SOURCE = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'


def connect(path):
    db = sqlite3.connect(path, timeout=60)
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
      CREATE TABLE IF NOT EXISTS prices (
        symbol TEXT NOT NULL, date TEXT NOT NULL, open REAL, high REAL, low REAL,
        close REAL, adjusted_close REAL, volume INTEGER, dividends REAL, splits REAL,
        currency TEXT, exchange TEXT, timezone TEXT, fetched_at TEXT,
        source TEXT NOT NULL DEFAULT 'Yahoo Finance', PRIMARY KEY(symbol,date));
      CREATE INDEX IF NOT EXISTS prices_date ON prices(date);
      CREATE TABLE IF NOT EXISTS state (
        symbol TEXT PRIMARY KEY, last_success TEXT, last_full TEXT, error TEXT);
      CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY, symbol TEXT, started TEXT, mode TEXT,
        status TEXT, rows INTEGER, empty_rows INTEGER, error TEXT);
      CREATE TABLE IF NOT EXISTS membership (
        observed_date TEXT, symbol TEXT, PRIMARY KEY(observed_date,symbol));
    ''')
    return db


@contextmanager
def process_lock(path):
    # OS releases the byte lock even after a crash; an existing file is harmless.
    import msvcrt
    with open(path, 'a+b') as lock:
        lock.seek(0, 2)
        if not lock.tell():
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError('Another ingestion process is already running') from exc
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def universe(db, config):
    symbols = set(config['symbols'])
    if config['sp500']:
        cache = DATA / 'sp500.json'
        try:
            request = urllib.request.Request(SOURCE, headers={'User-Agent': 'market-data/1.0'})
            with urllib.request.urlopen(request, timeout=30) as response:
                source_csv = response.read().decode('utf-8-sig')
                entries = list(csv.DictReader(io.StringIO(source_csv)))
            members = sorted({row['Symbol'].replace('.', '-') for row in entries})
            if not 450 <= len(members) <= 550:
                raise ValueError('Unexpected constituent count')
            names_temp = DATA / 'constituents.tmp'
            names_temp.write_text(source_csv, encoding='utf-8')
            names_temp.replace(DATA / 'constituents.csv')
            snapshot = {'observed_at': datetime.now(timezone.utc).isoformat(), 'source': SOURCE, 'symbols': members}
            temporary = cache.with_suffix('.tmp')
            temporary.write_text(json.dumps(snapshot, indent=2), encoding='utf-8')
            temporary.replace(cache)
            with db:
                db.executemany('INSERT OR IGNORE INTO membership VALUES (?,?)',
                               [(date.today().isoformat(), s) for s in members])
        except Exception:
            if not cache.exists():
                raise
            snapshot = json.loads(cache.read_text(encoding='utf-8'))
            members = snapshot['symbols']
            logging.warning('Universe refresh failed; using snapshot from %s', snapshot['observed_at'], exc_info=True)
        symbols.update(members)
    # Continue tracking previously downloaded symbols after index removal.
    symbols.update(row[0] for row in db.execute('SELECT symbol FROM state'))
    return sorted(symbols)


def normalize(symbol, frame, meta, today):
    rows, empty = [], 0
    seen = set()
    for stamp, item in frame.iterrows():
        day = stamp.date()
        if day >= today:
            continue
        values = [item.get(name) for name in ('Open', 'High', 'Low', 'Close')]
        if all(value is None or math.isnan(float(value)) for value in values):
            empty += 1
            continue
        if any(value is None or not math.isfinite(float(value)) for value in values):
            raise ValueError(f'{symbol}: partial OHLC on {day}')
        volume = float(item['Volume'])
        if not math.isfinite(volume) or volume < 0 or not volume.is_integer():
            raise ValueError(f'{symbol}: invalid volume on {day}')
        if day in seen:
            raise ValueError(f'{symbol}: duplicate date {day}')
        seen.add(day)
        def optional(name):
            value = item.get(name)
            return float(value) if value is not None and math.isfinite(float(value)) else None
        rows.append((symbol, day.isoformat(), *map(float, values), optional('Adj Close'),
                     int(volume), optional('Dividends'), optional('Stock Splits'),
                     meta.get('currency'), meta.get('exchangeName'), meta.get('exchangeTimezoneName'),
                     datetime.now(timezone.utc).isoformat()))
    return rows, empty


def persist(db, symbol, rows, full, started, empty):
    if not rows:
        raise ValueError(f'{symbol}: no completed daily bars returned')
    with db:
        db.executemany('''INSERT INTO prices
          (symbol,date,open,high,low,close,adjusted_close,volume,dividends,splits,currency,exchange,timezone,fetched_at)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(symbol,date) DO UPDATE SET
          open=excluded.open, high=excluded.high, low=excluded.low, close=excluded.close,
          adjusted_close=excluded.adjusted_close, volume=excluded.volume, dividends=excluded.dividends,
          splits=excluded.splits, currency=excluded.currency, exchange=excluded.exchange,
          timezone=excluded.timezone, fetched_at=excluded.fetched_at''', rows)
        db.execute('''INSERT INTO state VALUES (?,?,?,NULL) ON CONFLICT(symbol) DO UPDATE SET
          last_success=excluded.last_success, last_full=COALESCE(excluded.last_full,state.last_full), error=NULL''',
                   (symbol, started, started if full else None))
        db.execute('INSERT INTO attempts(symbol,started,mode,status,rows,empty_rows) VALUES (?,?,?,?,?,?)',
                   (symbol, started, 'full' if full else 'incremental', 'ok', len(rows), empty))


def ingest(db, config, symbols, force=False):
    import yfinance as yf
    failed = []
    for number, symbol in enumerate(symbols, 1):
        started = datetime.now(timezone.utc).isoformat()
        state = db.execute('SELECT last_full,last_success,error FROM state WHERE symbol=?', (symbol,)).fetchone()
        full = force or not state or not state[0] or (datetime.now(timezone.utc) - datetime.fromisoformat(state[0])).days >= config['full_refresh_days']
        latest = db.execute('SELECT MAX(date) FROM prices WHERE symbol=?', (symbol,)).fetchone()[0]
        if not force and state and state[1] and not state[2] and datetime.fromisoformat(state[1]).date() == datetime.now(timezone.utc).date() and not full:
            continue
        for attempt in range(config['attempts']):
            try:
                ticker = yf.Ticker(symbol)
                kwargs = dict(interval='1d', auto_adjust=False, actions=True, keepna=True, raise_errors=True, timeout=30)
                if full or not latest:
                    kwargs['period'] = 'max'
                else:
                    kwargs['start'] = (date.fromisoformat(latest) - timedelta(days=config['overlap_days'])).isoformat()
                frame = ticker.history(**kwargs)
                meta = ticker.get_history_metadata()
                zone = meta.get('exchangeTimezoneName')
                if not zone:
                    raise ValueError('Provider did not supply exchange timezone')
                rows, empty = normalize(symbol, frame, meta, datetime.now(ZoneInfo(zone)).date())
                # New corporate actions can revise the entire adjusted history.
                if not full and any(row[8] or row[9] for row in rows):
                    full = True
                    frame = ticker.history(period='max', **{k: v for k, v in kwargs.items() if k not in ('start', 'period')})
                    rows, empty = normalize(symbol, frame, meta, datetime.now(ZoneInfo(zone)).date())
                persist(db, symbol, rows, full, started, empty)
                logging.info('[%s/%s] %s: %s rows, %s empty records, %s', number, len(symbols), symbol, len(rows), empty, 'full' if full else 'incremental')
                break
            except Exception as exc:
                if attempt + 1 < config['attempts']:
                    delay = 10 * 2 ** attempt
                    logging.warning('%s attempt %s failed: %s; retry in %ss', symbol, attempt + 1, exc, delay)
                    time.sleep(delay)
                else:
                    failed.append(symbol)
                    with db:
                        db.execute('INSERT INTO state(symbol,error) VALUES (?,?) ON CONFLICT(symbol) DO UPDATE SET error=excluded.error', (symbol, str(exc)))
                        db.execute('INSERT INTO attempts(symbol,started,mode,status,error) VALUES (?,?,?,?,?)', (symbol, started, 'full' if full else 'incremental', 'failed', str(exc)))
                    logging.error('%s failed: %s', symbol, exc)
        time.sleep(config['request_pause_seconds'])
    return failed


def export(db):
    folder = DATA / 'exports'
    folder.mkdir(exist_ok=True)
    for (symbol,) in db.execute('SELECT DISTINCT symbol FROM prices'):
        # Quote punctuation for Windows-safe filenames.
        from urllib.parse import quote
        path = folder / (quote(symbol, safe='-._') + '.csv')
        temporary = path.with_suffix('.tmp')
        cursor = db.execute('SELECT * FROM prices WHERE symbol=? ORDER BY date', (symbol,))
        with temporary.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.writer(handle)
            writer.writerow([column[0] for column in cursor.description])
            writer.writerows(cursor)
        temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['sync', 'status', 'export'])
    parser.add_argument('--symbols', nargs='+', help='Override configured universe for this run')
    parser.add_argument('--full', action='store_true', help='Force complete history refresh')
    args = parser.parse_args()
    DATA.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), RotatingFileHandler(DATA / 'ingestion.log', maxBytes=10_000_000, backupCount=5, encoding='utf-8')])
    config = json.loads((ROOT / 'config.json').read_text())
    with connect(DATA / 'market.sqlite') as db:
        if args.command == 'status':
            print('symbols, rows, earliest, latest:', db.execute('SELECT COUNT(DISTINCT symbol),COUNT(*),MIN(date),MAX(date) FROM prices').fetchone())
            print('Integrity:', db.execute('PRAGMA quick_check').fetchone()[0])
            print('Failed symbols:', db.execute('SELECT symbol,error FROM state WHERE error IS NOT NULL').fetchall())
            return 0
        with process_lock(DATA / 'ingestion.lock'):
            if args.command == 'export':
                export(db)
                return 0
            symbols = sorted(set(args.symbols)) if args.symbols else universe(db, config)
            logging.info('Starting sync for %s symbols', len(symbols))
            failed = ingest(db, config, symbols, args.full)
            export(db)
            logging.info('Sync finished: %s failed symbols: %s', len(failed), failed)
            if (ROOT / 'deployment.json').exists():
                from publish_site import publish
                publish()
            return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
