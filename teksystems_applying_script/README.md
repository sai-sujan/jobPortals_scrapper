# TEKsystems Standalone Scraper

Scrapes TEKsystems jobs from `careers.teksystems.com` and writes filtered CSV, JSON, Excel, and daily grouped outputs. Defaults to jobs posted in the last 4 days.

## Run

```bash
python3 teksystems_scraper.py
```

Useful options:

```bash
python3 teksystems_scraper.py --posted-within-days 4
python3 teksystems_scraper.py --term "data engineer" --term "python developer"
python3 teksystems_scraper.py --no-excel
```

## Open Jobs

```bash
python3 teksystems_open_jobs.py --limit 10
python3 teksystems_open_jobs.py --apply --limit 5
```

## Filter Intent

Keeps Python, full stack, backend/API, AI/ML, data engineering, ETL, cloud, and data science roles.

Rejects junior/entry/intern titles, W2-only, no-C2C/no-corp-to-corp, full-time, permanent, direct hire, face-to-face interview, onsite interview, and local-only signals.

Contract-to-hire/C2H is allowed.
