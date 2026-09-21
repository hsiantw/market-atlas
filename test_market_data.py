import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from datetime import date
from pathlib import Path
import pandas as pd
from market_data import connect, normalize, persist, ingest

class StorageTests(unittest.TestCase):
    def test_resume_and_retry_failed_symbol(self):
        db = connect(':memory:')
        now = datetime.now(timezone.utc).isoformat()
        with db:
            db.execute('INSERT INTO state VALUES (?,?,?,?)', ('TEST', now, now, None))
        config = {'attempts': 2, 'full_refresh_days': 30, 'overlap_days': 14, 'request_pause_seconds': 0}
        with patch('yfinance.Ticker', side_effect=RuntimeError('provider offline')) as ticker, patch('market_data.time.sleep'):
            self.assertEqual(ingest(db, config, ['TEST']), [])
            ticker.assert_not_called()
            with db:
                db.execute("UPDATE state SET error='previous failure'")
            self.assertEqual(ingest(db, config, ['TEST']), ['TEST'])
            self.assertEqual(ticker.call_count, 2)
            self.assertEqual(db.execute('SELECT last_success,error FROM state').fetchone(), (now, 'provider offline'))
        db.close()

    def test_upsert_and_rollback(self):
        with tempfile.TemporaryDirectory() as folder:
            db = connect(Path(folder) / 'test.sqlite')
            row = ('TEST', '2026-01-01', 1., 2., 1., 2., 2., 10, 0., 0., 'USD', 'NMS', 'America/New_York', 'now')
            persist(db, 'TEST', [row], True, '2026-01-02T00:00:00+00:00', 0)
            updated = list(row)
            updated[6] = 1.5
            persist(db, 'TEST', [updated], False, '2026-01-03T00:00:00+00:00', 0)
            self.assertEqual(db.execute('SELECT COUNT(*),adjusted_close FROM prices').fetchone(), (1, 1.5))
            self.assertEqual(db.execute('SELECT last_full FROM state').fetchone()[0], '2026-01-02T00:00:00+00:00')
            bad = list(row)
            bad[0] = None
            with self.assertRaises(sqlite3.IntegrityError):
                persist(db, 'TEST', [row, bad], True, 'bad', 0)
            self.assertEqual(db.execute('SELECT adjusted_close FROM prices').fetchone()[0], 1.5)
            db.close()

    def test_current_and_missing_bars(self):
        frame = pd.DataFrame({'Open': [1, float('nan'), 3], 'High': [2, float('nan'), 4], 'Low': [1, float('nan'), 3], 'Close': [2, float('nan'), 4], 'Volume': [1, 0, 1]}, index=pd.date_range('2026-01-01', periods=3, tz='America/New_York'))
        rows, empty = normalize('TEST', frame, {}, date(2026, 1, 3))
        self.assertEqual((len(rows), empty), (1, 1))
        frame.iloc[0, 0] = float('nan')
        with self.assertRaises(ValueError):
            normalize('TEST', frame, {}, date(2026, 1, 3))

if __name__ == '__main__':
    unittest.main()
