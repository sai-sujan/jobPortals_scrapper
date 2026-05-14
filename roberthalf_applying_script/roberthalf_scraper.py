#!/usr/bin/env python3
"""Standalone Robert Half scraper using the embedded AEM initial jobs JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_vendor_filters import VendorJob, clean_text, extract_contact_info, filter_and_sort_jobs, score_title, write_outputs

BASE_URL = "https://www.roberthalf.com"
SEARCH_URL = f"{BASE_URL}/us/en/jobs"


def fetch_initial_jobs(timeout: int) -> list[dict[str, Any]]:
    html = requests.get(SEARCH_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout).text
    match = re.search(r"initialResults\s*=\s*JSON\.parse\('(.+?)'\);", html, re.S)
    if not match:
        raise RuntimeError("Could not find Robert Half initialResults JSON")
    data = json.loads(match.group(1).encode("utf-8").decode("unicode_escape"))
    jobs = data.get("data", {}).get("jobs") or []
    print(f"Robert Half: extracted {len(jobs)} embedded jobs before filtering")
    return jobs


def normalize(row: dict[str, Any]) -> VendorJob:
    title = clean_text(row.get("jobtitle"))
    raw_text = clean_text(" ".join(str(row.get(k) or "") for k in ("description", "skills", "boiler_plate")))
    rank, reasons = score_title(title, raw_text)
    location = clean_text(", ".join(x for x in [row.get("city"), row.get("stateprovince")] if x))
    salary = clean_text(" - ".join(x for x in [row.get("payrate_min"), row.get("payrate_max")] if x))
    return VendorJob("Robert Half", "embedded-initial-results", rank, reasons, title, clean_text(row.get("functional_role")), location, clean_text(row.get("emptype")), salary, str(row.get("date_posted") or ""), str(row.get("unique_job_number") or row.get("sf_jo_number") or ""), str(row.get("job_detail_url") or ""), str(row.get("job_detail_url") or ""), extract_contact_info(raw_text), raw_text[:900], raw_text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Robert Half jobs into CSV/JSON/Excel.")
    parser.add_argument("--posted-within-days", type=int, default=4)
    parser.add_argument("--keep-w2-f2f-onsite-interview", action="store_true")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "output")
    parser.add_argument("--no-excel", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs = [normalize(row) for row in fetch_initial_jobs(args.timeout)]
    filtered = filter_and_sort_jobs(jobs, args.posted_within_days, not args.keep_w2_f2f_onsite_interview)
    write_outputs("roberthalf", filtered, args.out_dir, args.posted_within_days, args.no_excel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
