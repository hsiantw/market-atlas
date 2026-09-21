import csv
import io
import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import dashboard
from market_data import connect, persist


class DashboardTests(unittest.TestCase):
    def test_api_filters_exports_and_rejects_invalid_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'market.sqlite'
            db = connect(path)
            rows = [('TEST', d, 1., 2., 1., c, c, 10, 0., 0., 'USD', 'NMS', 'America/New_York', 'now') for d,c in [('2026-01-01',1.),('2026-01-02',2.)]]
            persist(db, 'TEST', rows, True, 'now', 0)
            db.close()
            with patch.object(dashboard, 'DATABASE', path):
                server = ThreadingHTTPServer(('127.0.0.1', 0), dashboard.Handler)
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                base = f'http://127.0.0.1:{server.server_port}'
                def get(route):
                    with urllib.request.urlopen(base + route) as response:
                        return response.read().decode()
                try:
                    catalog = json.loads(get('/api/symbols'))
                    self.assertEqual(catalog[0]['change'], 100)
                    prices = json.loads(get('/api/history?symbol=TEST&start=2026-01-02'))
                    self.assertEqual(len(prices), 1)
                    self.assertEqual(prices[0]['close'], 2)
                    exported = list(csv.DictReader(io.StringIO(get('/api/export?symbol=TEST&end=2026-01-01'))))
                    self.assertEqual(len(exported), 1)
                    self.assertEqual(exported[0]['symbol'], 'TEST')
                    self.assertEqual(json.loads(get('/api/history?symbol=%27%20OR%201%3D1--')), [])
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        get('/api/history?start=2026-02-01&end=2026-01-01')
                    self.assertEqual(error.exception.code, 400)
                    with self.assertRaises(urllib.error.HTTPError):
                        get('/../config.json')
                finally:
                    server.shutdown()
                    server.server_close()
                    worker.join()


if __name__ == '__main__':
    unittest.main()
