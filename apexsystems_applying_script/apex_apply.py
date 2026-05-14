#!/usr/bin/env python3
"""Fill Apex Systems applications and leave tabs open for manual submit."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


DEFAULT_RESUME = Path(os.environ.get("JOB_PORTAL_RESUME", "resume.docx")).expanduser()
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "output"


@dataclass(frozen=True)
class Applicant:
    first_name: str = ""
    last_name: str = ""
    email: str = ""


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


def close_cookie_banner(page: Page) -> None:
    try:
        button = page.locator("#onetrust-accept-btn-handler")
        if button.is_visible(timeout=2500):
            button.click(timeout=2500)
            page.wait_for_timeout(500)
    except PlaywrightTimeoutError:
        pass


def fill_input(page: Page, name: str, value: str) -> None:
    field = page.locator(f"input[name='{name}']").first
    field.fill(value, timeout=5000)


def wait_for_resume_parse(page: Page) -> None:
    continue_button = page.get_by_role("button", name=re.compile(r"continue", re.I)).first
    for _ in range(40):
        try:
            text = continue_button.inner_text(timeout=1000)
            disabled = continue_button.is_disabled(timeout=1000)
            if "continue" in text.lower() and not disabled:
                return
        except Exception:
            pass
        page.wait_for_timeout(1000)
    raise RuntimeError("Resume parse did not finish; Continue button stayed unavailable")


def fill_application(page: Page, applicant: Applicant, resume_path: Path) -> None:
    close_cookie_banner(page)
    page.locator("input[type='file']").first.set_input_files(str(resume_path))
    wait_for_resume_parse(page)
    page.get_by_role("button", name=re.compile(r"continue", re.I)).first.click(timeout=10000)
    page.wait_for_timeout(2500)

    # Resume parsing usually fills these, but set them explicitly so every tab is consistent.
    fill_input(page, "firstName", applicant.first_name)
    fill_input(page, "lastName", applicant.last_name)
    fill_input(page, "email", applicant.email)

    page.get_by_role("button", name=re.compile(r"submit application", re.I)).first.wait_for(timeout=10000)


def write_report(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    keys = ["status", "job_id", "title", "posted_date", "apply_url", "message", "screenshot"]
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill Apex applications and leave them open for manual submit.")
    parser.add_argument("--jobs-file", type=Path, help="Filtered apex_jobs_*.json file. Defaults to latest output.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--resume", type=Path, default=DEFAULT_RESUME)
    parser.add_argument("--first-name", default=Applicant.first_name)
    parser.add_argument("--last-name", default=Applicant.last_name)
    parser.add_argument("--email", default=Applicant.email)
    parser.add_argument("--limit", type=int, default=4)
    parser.add_argument("--start-at", type=int, default=1, help="1-based job index to start from.")
    parser.add_argument("--keep-open-minutes", type=int, default=120)
    parser.add_argument("--slow-mo", type=int, default=250)
    parser.add_argument("--browser-channel", default="chrome", help="Playwright browser channel to use. Defaults to Chrome.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = [name for name, value in (("first name", args.first_name), ("last name", args.last_name), ("email", args.email)) if not value]
    if missing:
        print(f"Missing applicant {', '.join(missing)}. Pass the values with flags.", file=sys.stderr)
        return 2
    resume_path = args.resume.expanduser().resolve()
    if not resume_path.exists():
        print(f"Resume not found: {resume_path}", file=sys.stderr)
        return 2

    jobs_file = args.jobs_file or latest_jobs_file(args.out_dir)
    jobs = load_jobs(jobs_file)
    start = max(args.start_at - 1, 0)
    selected = jobs[start:]
    if args.limit > 0:
        selected = selected[: args.limit]
    if not selected:
        print("No jobs selected.")
        return 0

    applicant = Applicant(args.first_name, args.last_name, args.email)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = args.out_dir / f"apply_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_rows: list[dict[str, Any]] = []

    print(f"Jobs file: {jobs_file}")
    print(f"Resume: {resume_path}")
    print(f"Selected jobs: {len(selected)}")
    print("Mode: fill tabs and leave open for manual Submit Application")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.browser_channel, headless=False, slow_mo=args.slow_mo)
        context = browser.new_context(accept_downloads=True)
        first_page = context.new_page()

        try:
            for offset, job in enumerate(selected, start=start + 1):
                page = first_page if offset == start + 1 else context.new_page()
                title = str(job.get("title") or "").strip()
                job_id = str(job.get("job_id") or "").strip()
                apply_url = str(job.get("apply_url") or "").strip()
                screenshot = run_dir / f"{offset:03d}_{job_id.lower()}_filled.png"
                print(f"\n[{offset}/{len(jobs)}] {title} | {job_id}")
                print(apply_url)

                status = "filled"
                message = "Filled and waiting for manual Submit Application."
                try:
                    if not apply_url:
                        raise RuntimeError("Missing apply_url")
                    page.goto(apply_url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(8000)
                    fill_application(page, applicant, resume_path)
                    page.screenshot(path=str(screenshot), full_page=True)
                    print("Status: filled; manual submit needed")
                except Exception as exc:
                    status = "error"
                    message = str(exc)
                    try:
                        page.screenshot(path=str(screenshot), full_page=True)
                    except Exception:
                        pass
                    print(f"Status: error - {message}")

                report_rows.append(
                    {
                        "status": status,
                        "job_id": job_id,
                        "title": title,
                        "posted_date": job.get("posted_date", ""),
                        "apply_url": apply_url,
                        "message": message,
                        "screenshot": str(screenshot),
                    }
                )
                write_report(run_dir / "apply_report.csv", report_rows)
                time.sleep(1)

            print("\nBrowser is staying open. Manually click Submit Application in each tab and handle CAPTCHA if shown.")
            print(f"Apply report: {run_dir / 'apply_report.csv'}")
            print(f"It will stay open for {args.keep_open_minutes} minutes unless you close it first.")
            first_page.wait_for_timeout(max(args.keep_open_minutes, 1) * 60 * 1000)
        finally:
            context.close()
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
