# Eliassen standalone job scraper

Scrapes Eliassen jobs from the public Atom feed and writes filtered CSV, JSON, Excel, and daily grouped outputs.

Unlike search-page scrapers, this extracts the full feed first, then filters locally. The default posting window is 4 days.

## Run

```bash
python3 eliassen_scraper.py
```

Useful options:

```bash
python3 eliassen_scraper.py --posted-within-days 4
python3 eliassen_scraper.py --no-excel
python3 eliassen_open_jobs.py --limit 5
```

## Filters

- Extracts all jobs present in `https://careers.eliassen.com/feeds/jobs.atom` before filtering.
- Includes full stack, Python, backend, API, AI/ML/GenAI/LLM/RAG, data engineer, and data engineering roles.
- Excludes W2/W-2, W2-only, "No C2C", no corp-to-corp, F2F, onsite/in-person interview, local-only, permanent, and direct-hire language.
- Allows C2H/contract-to-hire when present.
- Excludes junior, entry-level, intern, embedded/hardware-heavy roles.
