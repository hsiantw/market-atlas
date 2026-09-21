# Free GitHub Pages hosting

The local dashboard runs a Python server; the hosted version is a static snapshot. Both provide search, favorites, charts, date filtering, tables and CSV downloads. GitHub Pages serves the static files without running Python or SQLite.

## Publishing architecture

1. `build_site.py` reads the local database and creates `site/` plus `data/site.zip`.
2. Historical rows are compressed separately for each symbol. A visitor downloads only the selected symbol and the browser decompresses it. Modern Chrome, Edge, Firefox or Safari is required.
3. `publish_site.py` uploads the archive to the `site-data` GitHub release and dispatches `.github/workflows/pages.yml`.
4. The workflow deploys the archive to GitHub Pages. Database files, logs, the virtual environment, and local deployment settings are excluded from source control.
5. When `deployment.json` exists, the daily collector invokes the publisher after updating its database and exports. The collector machine must be online and logged in; the already-published website remains available when it is off.

The repository, website and uploaded price snapshots will be public on the free GitHub Pages plan. The provider's data terms still apply; yfinance does not grant redistribution rights. Review those terms for any public redistribution or commercial use. Source: https://github.com/ranaroussi/yfinance

## Local preview

```powershell
.\.venv\Scripts\python.exe build_site.py
.\.venv\Scripts\python.exe -m http.server 8766 --bind 127.0.0.1 --directory site
```

Open http://127.0.0.1:8766. The complete site is capped at 900 MB by the builder, below GitHub Pages' 1 GB limit. The generated archive is uploaded as a release asset rather than committed into Git history.

## Account setup

Git and GitHub CLI are needed to publish. Authenticate using `gh auth login --hostname github.com --git-protocol https --web --scopes workflow`; complete the device authorization in your browser. Never put credentials into project files.

After creating a public repository and pushing the source, enable Pages with GitHub Actions as the source. Create a `site-data` release containing `data/site.zip` before running the Pages workflow.

Local `deployment.json` contains only the chosen repository:

```json
{"repository": "YOUR_USERNAME/market-atlas"}
```

Run `.\.venv\Scripts\python.exe publish_site.py` to upload a new snapshot and request deployment. A successful upload is not a confirmed deployment: check the workflow result and website afterward. To stop automatic publishing, rename `deployment.json`; daily local downloads will continue.

There are no paid services or custom domain requirements. Free hosting is subject to GitHub's documented limits: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
