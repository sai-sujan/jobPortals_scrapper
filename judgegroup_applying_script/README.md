# Judge Group Applying Script

Standalone Judge Group scraper for the separate-folder workflow.

## What It Does

- Searches Judge Group contract jobs through `https://www.judge.com/wp-admin/admin-ajax.php?action=jdg_get_jobs`.
- Keeps Information Technology contract roles that match full stack, Python, backend/API, AI/ML/GenAI/LLM/RAG, cloud, and data engineering terms.
- Excludes junior/entry/intern roles.
- Excludes W2/W-2, W2 contract, no C2C, no corp-to-corp, not open to C2C, face-to-face interview, and local-only wording.
- Allows C2H/contract-to-hire wording.
- Defaults to jobs posted in the last 4 days.
- Writes CSV, JSON, Excel, and daily grouped CSV/JSON output files.

## Run

```bash
python3 judgegroup_scraper.py
```

Useful smoke test:

```bash
python3 judgegroup_scraper.py --term "python" --term "software engineer" --term "data engineer" --posted-within-days 90 --max-pages 1 --no-excel
```

Open latest filtered jobs:

```bash
python3 judgegroup_open_jobs.py --limit 10
```

Fill one application in Chrome and leave it open without submitting:

```bash
python3 judgegroup_apply.py \
  --url "https://www.judge.com/jobs/details/1132024/" \
  --resume /path/to/resume.docx \
  --first-name Jane \
  --last-name Candidate \
  --email jane@example.com \
  --phone 5551234567 \
  --street-address "City center" \
  --city "Jersey City" \
  --state NJ \
  --zip-code 08540
```

Fill and submit:

```bash
python3 judgegroup_apply.py --url "https://www.judge.com/jobs/details/1132024/" --resume /path/to/resume.docx --first-name Jane --last-name Candidate --email jane@example.com --phone 5551234567 --street-address "City center" --city "Jersey City" --state NJ --zip-code 08540 --submit --keep-open-seconds 20
```

Outputs are written to `output/`.
