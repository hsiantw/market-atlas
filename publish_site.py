"""Publish a prepared snapshot using the locally authenticated GitHub CLI."""
import json
import shutil
import subprocess
from pathlib import Path
from build_site import build
from dashboard import ROOT


def publish():
    config = json.loads((ROOT / 'deployment.json').read_text(encoding='utf-8'))
    repo = config['repository']
    gh = shutil.which('gh') or str(Path('C:/Program Files/GitHub CLI/gh.exe'))
    archive = build()
    subprocess.run([gh, 'release', 'upload', 'site-data', str(archive), '--clobber', '--repo', repo], check=True)
    subprocess.run([gh, 'workflow', 'run', 'pages.yml', '--repo', repo], check=True)
    print('Snapshot uploaded and deployment requested for ' + repo, flush=True)


if __name__ == '__main__':
    publish()
