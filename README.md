# Personalized Daily Job Checker

This local tool checks staffing-company job boards for senior Python, Django/DRF, FastAPI, backend APIs, microservices, cloud, ETL/data engineering, AI/ML, GenAI, RAG, and LLM work.

## Quick Start

```bash
cd jobPortals_scrapper
PYTHONPATH=src python3 -m job_checker doctor
PYTHONPATH=src python3 -m job_checker run
```

Outputs:

- `data/jobs.sqlite`
- `reports/jobs_latest.xlsx`
- `reports/YYYY-MM-DD_jobs.xlsx`
- `reports/YYYY-MM-DD_jobs.csv`
- `reports/site/index.html`
- `logs/job_checker.log`

## Local Dashboard

Run the lightweight web dashboard:

```bash
python3 job_portal_dashboard.py --port 8766
```

Then open:

```bash
open http://127.0.0.1:8766
```

The dashboard can scrape all configured portals, edit the keyword list and posted-date window, and open the latest filtered jobs for the weekday rotation.

## Daily Schedule

Create the macOS LaunchAgent:

```bash
PYTHONPATH=src python3 -m job_checker install-schedule
launchctl load ~/Library/LaunchAgents/com.venkatadora.jobchecker.plist
```

The schedule runs every 3 hours: 12 AM, 3 AM, 6 AM, 9 AM, 12 PM, 3 PM, 6 PM, and 9 PM local Mac time.

## Visualization

Open this file in your browser:

```bash
open reports/site/index.html
```

The website lets you filter by first-seen date, company, match bucket, and search text. A link appears as new only on the first day it was discovered; later runs update `last_seen_at` in SQLite without repeating it as a new daily link.
