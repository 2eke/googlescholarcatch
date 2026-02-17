# Google Scholar Catcher

This project tracks your Google Scholar profile daily and records:

- Total citations
- h-index and i10-index
- Citation count for each publication

It stores snapshots in a local SQLite database and can generate trend plots.

## 1) Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2) Find your author ID

Open your Google Scholar profile URL. It looks like:

```text
https://scholar.google.com/citations?user=YOUR_AUTHOR_ID&hl=en
```

Copy `YOUR_AUTHOR_ID`.

## 3) Fetch a daily snapshot

```bash
python scholar_tracker.py fetch --author-id YOUR_AUTHOR_ID
```

This creates/updates `scholar_history.db`.

## 4) Generate plots

Total citations over time:

```bash
python scholar_tracker.py plot-total --output total_citations.png
```

Per-publication citation trends (top 10 papers by default):

```bash
python scholar_tracker.py plot-publications --top 10 --output publication_citations.png
```

## 5) Run daily automatically (cron)

Edit cron jobs:

```bash
crontab -e
```

Add (runs daily at 08:00):

```cron
0 8 * * * cd /workspace/googlescholarcatch && /usr/bin/python3 scholar_tracker.py fetch --author-id YOUR_AUTHOR_ID >> scholar_fetch.log 2>&1
```

## Notes

- Google Scholar may throttle or block frequent scraping. If that happens, reduce fetch frequency.
- Publication titles can occasionally change formatting; this script uses title text to align timeseries.
- You can change the database path by editing `DB_PATH` in `scholar_tracker.py`.
