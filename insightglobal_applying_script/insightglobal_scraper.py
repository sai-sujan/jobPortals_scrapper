#!/usr/bin/env python3
"""Standalone Insight Global scraper using the public Jibe/iCIMS API."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_vendor_filters import VendorJob, clean_text, extract_contact_info, filter_and_sort_jobs, score_title, write_outputs


BASE_URL = "https://careers.insightglobal.com"
API_URL = f"{BASE_URL}/api/jobs"
DEFAULT_SEARCH_TERMS = ["python", "full stack", "backend", "data engineer", "data engineering", "etl", "ai engineer", "machine learning", "llm", "rag"]


def fetch_term(term: str, timeout: int) -> list[dict[str, Any]]:
    params = {"keywords": term, "tags5": "Insight Global (External)", "sortBy": "posted_date"}
    response = requests.get(API_URL, params=params, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=timeout)
    if response.status_code == 404:
        print(f"Insight Global {term}: no API results")
        return []
    response.raise_for_status()
    data = response.json()
    rows = data.get("jobs") or []
    print(f"Insight Global {term}: extracted {len(rows)} jobs")
    return rows


def normalize(row: dict[str, Any], search_term: str) -> VendorJob:
    data = row.get("data") if isinstance(row.get("data"), dict) else row
    title = clean_text(data.get("title"))
    raw_text = clean_text(" ".join(str(data.get(k) or "") for k in ("description", "responsibilities", "qualifications")))
    rank, reasons = score_title(title, raw_text)
    location = clean_text(data.get("full_location") or ", ".join(x for x in [data.get("city"), data.get("state")] if x))
    category = ", ".join(clean_text(item.get("name")) for item in data.get("categories", []) if isinstance(item, dict))
    slug = clean_text(data.get("slug") or data.get("req_id"))
    return VendorJob("Insight Global", search_term, rank, reasons, title, category, location, clean_text(", ".join((data.get("tags2") or []) + (data.get("tags1") or []))), "", str(data.get("posted_date") or ""), str(data.get("req_id") or slug), f"{BASE_URL}/jobs/{slug}?lang=en-us", str(data.get("apply_url") or ""), extract_contact_info(raw_text), raw_text[:900], raw_text)


def scrape(terms: Iterable[str], posted_within_days: int, exclude_disallowed_work: bool, timeout: int) -> list[VendorJob]:
    seen: set[str] = set()
    jobs: list[VendorJob] = []
    for term in terms:
        for row in fetch_term(term, timeout):
            job = normalize(row, term)
            key = job.job_id or job.job_url
            if key in seen:
                continue
            seen.add(key)
            jobs.append(job)
    print(f"Extracted {len(jobs)} unique Insight Global jobs before filtering")
    return filter_and_sort_jobs(jobs, posted_within_days, exclude_disallowed_work)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Insight Global jobs into CSV/JSON/Excel.")
    parser.add_argument("--term", action="append", dest="terms")
    parser.add_argument("--posted-within-days", type=int, default=4)
    parser.add_argument("--keep-w2-f2f-onsite-interview", action="store_true")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "output")
    parser.add_argument("--no-excel", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs = scrape(args.terms or DEFAULT_SEARCH_TERMS, args.posted_within_days, not args.keep_w2_f2f_onsite_interview, args.timeout)
    write_outputs("insightglobal", jobs, args.out_dir, args.posted_within_days, args.no_excel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
