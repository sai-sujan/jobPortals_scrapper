#!/usr/bin/env python3
"""Open Apex job pages, click Apply, and leave redirected application pages open."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def latest_jobs_file(output_dir: Path) -> Path:
    files = sorted(output_dir.glob("apex_jobs_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError(f"No apex_jobs_*.json files found in {output_dir}")
    return files[0]


def load_jobs(path: Path) -> list[dict[str, Any]]:
    with path.open() as handle:
        jobs = json.load(handle)
    if not isinstance(jobs, list):
        raise ValueError(f"Expected a list of jobs in {path}")
    return jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open Apex job pages, click Apply, and keep redirected pages open.")
    parser.add_argument("--jobs-file", type=Path, help="Filtered apex_jobs_*.json file. Defaults to latest output.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--start-at", type=int, default=1, help="1-based job index to start from.")
    parser.add_argument("--keep-open-minutes", type=int, default=120)
    parser.add_argument("--slow-mo", type=int, default=150)
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
    print(f"Opening job pages, clicking Apply, and keeping redirected pages only: {len(selected)}")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.browser_channel, headless=False, slow_mo=args.slow_mo)
        context = browser.new_context()
        first_page = None
        opened = 0

        try:
            for index, job in enumerate(selected, start=start + 1):
                page = context.new_page()
                if first_page is None:
                    first_page = page

                title = str(job.get("title") or "").strip()
                job_url = str(job.get("job_url") or "").strip()
                fallback_apply_url = str(job.get("apply_url") or "").strip()
                if not job_url:
                    print(f"[{index}] skipped, missing job_url: {title}")
                    continue

                print(f"[{index}/{len(jobs)}] {title}")
                print(f"Job page: {job_url}")
                page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(1500)

                before_pages = set(context.pages)
                try:
                    page.locator('a.apply-btn, a:has-text("Apply")').first.click(timeout=15000)
                    page.wait_for_load_state("domcontentloaded", timeout=45000)
                    page.wait_for_timeout(2500)
                    new_pages = [candidate for candidate in context.pages if candidate not in before_pages]
                    if new_pages:
                        redirected = new_pages[-1]
                        try:
                            redirected.wait_for_load_state("domcontentloaded", timeout=45000)
                        except PlaywrightTimeoutError:
                            pass
                        page.close()
                        page = redirected
                except Exception as exc:
                    if not fallback_apply_url:
                        raise
                    print(f"Apply click failed ({exc}); opening scraped apply URL instead.")
                    page.goto(fallback_apply_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2500)

                print(f"Redirected page: {page.url}")
                opened += 1

            visible_page = next((page for page in context.pages if not page.is_closed()), None)
            if visible_page:
                visible_page.bring_to_front()
                print(f"\nOpened {opened} redirected Apex application pages. No details filled.")
                print(f"Browser will stay open for {args.keep_open_minutes} minutes.")
                visible_page.wait_for_timeout(max(args.keep_open_minutes, 1) * 60 * 1000)
        finally:
            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
