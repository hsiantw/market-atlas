"""Local market dashboard. Run with .venv/Scripts/python.exe dashboard.py."""
import argparse
import csv
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / 'data' / 'market.sqlite'


@contextmanager
def database():
    connection = sqlite3.connect(DATABASE.as_uri() + '?mode=ro', uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def catalog():
    names = {'2330.TW': 'Taiwan Semiconductor', 'BTC-USD': 'Bitcoin', 'ETH-USD': 'Ethereum'}
    source = ROOT / 'data' / 'constituents.csv'
    if source.exists():
        with source.open(encoding='utf-8-sig') as handle:
            names.update({r['Symbol'].replace('.', '-'): r['Security'] for r in csv.DictReader(handle)})
    with database() as db:
        symbols = db.execute('SELECT symbol,last_success,error FROM state ORDER BY symbol').fetchall()
        result = []
        for symbol in symbols:
            latest = db.execute('SELECT date,close,currency,exchange FROM prices WHERE symbol=? ORDER BY date DESC LIMIT 2', (symbol['symbol'],)).fetchall()
            if not latest:
                continue
            latest, previous = latest[0], latest[1] if len(latest) > 1 else None
            change = (latest['close'] / previous['close'] - 1) * 100 if previous and previous['close'] else None
            result.append(dict(symbol=symbol['symbol'], name=names.get(symbol['symbol'], symbol['symbol']),
                               **dict(latest), change=change, kind='Crypto' if symbol['symbol'] in ('BTC-USD', 'ETH-USD') else 'Stocks',
                               updated=symbol['last_success'], error=symbol['error']))
    return result


def history(query):
    symbol = query.get('symbol', ['AAPL'])[0]
    start, end = query.get('start', ['0001-01-01'])[0], query.get('end', ['9999-12-31'])[0]
    date.fromisoformat(start)
    date.fromisoformat(end)
    if start > end:
        raise ValueError('Start date must be before the end date.')
    with database() as db:
        rows = db.execute('''SELECT date,open,high,low,close,adjusted_close,volume,dividends,splits
          FROM prices WHERE symbol=? AND date>=? AND date<=? ORDER BY date''', (symbol, start, end)).fetchall()
    return [dict(row) for row in rows]


class Handler(BaseHTTPRequestHandler):
    def send(self, status, content, mime, attachment=False):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if attachment:
            self.send_header('Content-Disposition', 'attachment; filename="prices.csv"')
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        url = urlparse(self.path)
        try:
            if url.path == '/api/symbols':
                value = catalog()
            elif url.path in ('/api/history', '/api/export'):
                value = history(parse_qs(url.query))
                if url.path == '/api/export':
                    output = io.StringIO(newline='')
                    fields = ['symbol', 'date', 'open', 'high', 'low', 'close', 'adjusted_close', 'volume', 'dividends', 'splits']
                    writer = csv.DictWriter(output, fieldnames=fields)
                    writer.writeheader()
                    symbol = parse_qs(url.query).get('symbol', ['AAPL'])[0]
                    for row in value:
                        writer.writerow({'symbol': symbol, **row})
                    self.send(200, output.getvalue().encode(), 'text/csv; charset=utf-8', True)
                    return
            else:
                files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
                if url.path not in files:
                    self.send(404, b'Not found', 'text/plain')
                    return
                filename, mime = files[url.path]
                self.send(200, (ROOT / 'web' / filename).read_bytes(), mime + '; charset=utf-8')
                return
            self.send(200, json.dumps(value, allow_nan=False).encode(), 'application/json')
        except ValueError as exc:
            self.send(400, json.dumps({'error': str(exc)}).encode(), 'application/json')
        except Exception:
            self.send(500, b'{"error":"Could not read the local dataset. Check that the database exists."}', 'application/json')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    print(f'Market Atlas is running at http://127.0.0.1:{args.port}', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
