"""Build a portable static dashboard from the local database."""
import gzip
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from dashboard import ROOT, catalog, database

OUTPUT = ROOT / 'site'
FIELDS = ['date', 'open', 'high', 'low', 'close', 'adjusted_close', 'volume', 'dividends', 'splits']


def build():
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT / 'prices').mkdir(exist_ok=True)
    for name in ('index.html', 'style.css', 'app.js', 'static-data.js'):
        shutil.copyfile(ROOT / 'web' / name, OUTPUT / name)
    index = (OUTPUT / 'index.html').read_text(encoding='utf-8-sig')
    index = index.replace('href="/style.css"', 'href="./style.css"').replace('href="/"', 'href="./"')
    index = index.replace('src="/app.js"', 'src="./app.js"')
    index = index.replace('<script src="./app.js">', '<script src="./static-data.js"></script><script src="./app.js">')
    index = index.replace('Daily updates scheduled for 09:00 local time while logged in.',
                          'Daily snapshots published from the data collector. Check each asset for its latest date.')
    (OUTPUT / 'index.html').write_text(index, encoding='utf-8')
    (OUTPUT / '.nojekyll').touch()
    symbols = catalog()
    # A manifest restricts deployment to files from this build, excluding old symbols.
    files = ['index.html', 'style.css', 'app.js', 'static-data.js', '.nojekyll', 'symbols.json', 'snapshot.json']
    (OUTPUT / 'symbols.json').write_text(json.dumps(symbols, separators=(',', ':'), allow_nan=False), encoding='utf-8')
    count = 0
    with database() as db:
        for asset in symbols:
            rows = db.execute('SELECT ' + ','.join(FIELDS) + ' FROM prices WHERE symbol=? ORDER BY date', (asset['symbol'],)).fetchall()
            # Arrays avoid repeating field names millions of times. Gzip is decoded in the browser.
            payload = json.dumps({'columns': FIELDS, 'rows': [list(row) for row in rows]}, separators=(',', ':'), allow_nan=False).encode()
            filename = 'prices/' + quote(asset['symbol'], safe='-._') + '.json.gz'
            (OUTPUT / filename).write_bytes(gzip.compress(payload, mtime=0))
            files.append(filename)
            count += len(rows)
    snapshot = {'built_at': datetime.now(timezone.utc).isoformat(), 'symbols': len(symbols), 'records': count}
    (OUTPUT / 'snapshot.json').write_text(json.dumps(snapshot), encoding='utf-8')
    archive = ROOT / 'data' / 'site.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as handle:
        for name in files:
            handle.write(OUTPUT / name, name)
    size = sum((OUTPUT / name).stat().st_size for name in files)
    if size > 900_000_000:
        raise RuntimeError('Site exceeds the configured GitHub Pages size budget')
    print(f'Built {len(symbols)} assets, {count:,} records, {size / 1e6:.1f} MB; archive: {archive}', flush=True)
    return archive


if __name__ == '__main__':
    build()
