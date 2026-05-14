#!/usr/bin/env python3
"""Run the weekday job scraping routine from one command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from job_portal_dashboard import (
    ROOT,
    VENDORS,
    VENDOR_BY_SLUG,
    active_pair_for,
    command_for_open,
    command_for_scrape,
    load_config,
    vendor_status,
)


LOG_DIR = ROOT / "logs"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run daily job scraper automation.")
    parser.add_argument("--mode", choices=["all", "today"], default="all", help="Scrape all portals or only today's two active portals.")
    parser.add_argument("--weekdays-only", action="store_true", help="Skip Saturday and Sunday.")
    parser.add_argument("--open-today", action="store_true", help="After scraping, open today's two active portals.")
    parser.add_argument("--open-limit", type=int, help="Override the saved open limit.")
    return parser.parse_args()


def selected_vendors(mode: str) -> list[str]:
    if mode == "today":
        return active_pair_for()
    return [vendor.slug for vendor in VENDORS]


def main() -> int:
    args = parse_args()
    if args.weekdays_only and date.today().weekday() >= 5:
        print("Weekend detected. Skipping daily scrape.")
        return 0

    config = load_config()
    if args.open_limit is not None:
        config["open_limit"] = args.open_limit

    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"daily_scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    slugs = selected_vendors(args.mode)
    failures = 0

    with log_path.open("w", encoding="utf-8") as log:
        def write(line: str) -> None:
            print(line)
            log.write(line + "\n")
            log.flush()

        write(f"Started: {datetime.now().isoformat(timespec='seconds')}")
        write(f"Mode: {args.mode}")
        write(f"Vendors: {', '.join(slugs)}")

        for slug in slugs:
            vendor = VENDOR_BY_SLUG[slug]
            write(f"\n[{vendor.label}] scraping")
            proc = subprocess.run(command_for_scrape(vendor, config), cwd=ROOT, text=True, capture_output=True, timeout=900)
            if proc.stdout:
                log.write(proc.stdout)
            if proc.stderr:
                log.write(proc.stderr)
            status = vendor_status(vendor)
            write(f"[{vendor.label}] returncode={proc.returncode} latest_count={status['latest_count']} latest_file={status['latest_file']}")
            if proc.returncode != 0:
                failures += 1

        if args.open_today:
            write("\nOpening today's two portals")
            for slug in active_pair_for():
                vendor = VENDOR_BY_SLUG[slug]
                proc = subprocess.Popen(command_for_open(vendor, config, {}), cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                write(f"[{vendor.label}] opener pid={proc.pid}")

        write(f"\nFinished: {datetime.now().isoformat(timespec='seconds')}")
        write(f"Log: {log_path}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
