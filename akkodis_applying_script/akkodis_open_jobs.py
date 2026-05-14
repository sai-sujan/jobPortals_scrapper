#!/usr/bin/env python3
"""Open filtered Akkodis job pages in Chrome tabs and keep the browser open."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def latest_jobs_file(output_dir: Path) -> Path:
    files = sorted(output_dir.glob("akkodis_jobs_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No akkodis_jobs_*.json files found in {output_dir}")
    return files[0]


def load_jobs(path: Path) -> list[dict[str, Any]]:
    with path.open() as handle:
        jobs = json.load(handle)
    if not isinstance(jobs, list):
        raise ValueError(f"Expected a list of jobs in {path}")
    return jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Akkodis job pages in Chrome tabs.")
    parser.add_argument("--jobs-file", type=Path, help="Filtered akkodis_jobs_*.json file. Defaults to latest output.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-at", type=int, default=1, help="1-based job index to start from.")
    parser.add_argument("--keep-open-minutes", type=int, default=120)
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--browser-channel", default="chrome", help="Playwright browser channel to use. Defaults to Chrome.")
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
    print(f"Opening Akkodis job tabs in Chrome: {len(selected)}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.browser_channel, headless=False, slow_mo=args.slow_mo)
        context = browser.new_context()
        first_page = context.new_page()

        try:
            for index, job in enumerate(selected, start=start + 1):
                page = first_page if index == start + 1 else context.new_page()
                title = str(job.get("title") or "").strip()
                job_url = str(job.get("job_url") or "").strip()
                if not job_url:
                    print(f"[{index}] skipped, missing job_url: {title}", file=sys.stderr)
                    continue
                print(f"[{index}/{len(jobs)}] {title}")
                print(job_url)
                page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1000)

            print(f"\nBrowser will stay open for {args.keep_open_minutes} minutes.")
            first_page.wait_for_timeout(max(args.keep_open_minutes, 1) * 60 * 1000)
        finally:
            context.close()
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
