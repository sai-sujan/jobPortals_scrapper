#!/usr/bin/env python3
"""Open filtered TEKsystems job pages in the existing browser."""

from __future__ import annotations

import argparse
import json
import sys
import time
import webbrowser
from pathlib import Path
from typing import Any


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def latest_jobs_file(output_dir: Path) -> Path:
    files = sorted(output_dir.glob("teksystems_jobs_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No teksystems_jobs_*.json files found in {output_dir}")
    return files[0]


def load_jobs(path: Path) -> list[dict[str, Any]]:
    with path.open() as handle:
        jobs = json.load(handle)
    if not isinstance(jobs, list):
        raise ValueError(f"Expected a list of jobs in {path}")
    return jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open TEKsystems job pages in browser tabs.")
    parser.add_argument("--jobs-file", type=Path, help="Filtered teksystems_jobs_*.json. Defaults to latest output.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-at", type=int, default=1, help="1-based job index to start from.")
    parser.add_argument("--delay", type=float, default=0.5, help="Seconds between opening each tab.")
    parser.add_argument("--apply", action="store_true", help="Open apply URLs instead of job detail URLs when available.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs_file = args.jobs_file or latest_jobs_file(args.out_dir)
    jobs = load_jobs(jobs_file)
    start = max(args.start_at - 1, 0)
    selected = jobs[start:]
    if args.limit > 0:
        selected = selected[: args.limit]
    if not selected:
        print("No jobs selected.")
        return 0

    print(f"Jobs file: {jobs_file}")
    print(f"Opening {len(selected)} TEKsystems tabs...")

    for index, job in enumerate(selected, start=start + 1):
        title = str(job.get("title") or "").strip()
        job_url = str(job.get("job_url") or "").strip()
        apply_url = str(job.get("apply_url") or "").strip()
        url = apply_url if args.apply and apply_url else job_url or apply_url
        if not url:
            print(f"[{index}] skipped, missing url: {title}", file=sys.stderr)
            continue
        print(f"[{index}/{len(jobs)}] {title}")
        webbrowser.open_new_tab(url)
        time.sleep(args.delay)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
