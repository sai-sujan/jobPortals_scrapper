#!/usr/bin/env python3
"""Standalone Mitchell Martin scraper using rendered career-portal job cards."""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_vendor_filters import VendorJob, clean_text, extract_contact_info, filter_and_sort_jobs, score_title, write_outputs

BASE_URL = "https://www.mitchellmartin.com"
CAREER_URL = f"{BASE_URL}/career-portal"


def fetch_links(timeout: int) -> list[str]:
    html = requests.get(CAREER_URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout).text
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for anchor in soup.select('a[href*="/blog/job/"]'):
        href = anchor.get("href", "").strip()
        if href and href not in links:
            links.append(href)
    print(f"Mitchell Martin: extracted {len(links)} job links from first rendered grid")
    return links


def normalize(url: str, timeout: int) -> VendorJob:
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout).text
    soup = BeautifulSoup(html, "html.parser")
    title = clean_text((soup.find("h1") or soup.find("title") or "").get_text(" ", strip=True))
    title = re.sub(r"\s*-\s*Mitchell Martin.*$", "", title, flags=re.I)
    raw_text = clean_text(soup.get_text(" ", strip=True))
    rank, reasons = score_title(title, raw_text)
    location = ""
    loc_match = re.search(r"\b([A-Z][A-Za-z ]+\s*\|\s*[A-Za-z .-]+)\b", raw_text)
    if loc_match:
        location = clean_text(loc_match.group(1))
    employment = "IT Contract" if re.search(r"\bIT Contract\b|\bContract\b", raw_text, re.I) else ""
    return VendorJob("Mitchell Martin", "career-portal-grid", rank, reasons, title, "", location, employment, "", "", url.rsplit("/", 1)[-1], url, url, extract_contact_info(raw_text), raw_text[:900], raw_text)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape Mitchell Martin jobs into CSV/JSON/Excel.")
    parser.add_argument("--posted-within-days", type=int, default=4)
    parser.add_argument("--keep-w2-f2f-onsite-interview", action="store_true")
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.2)
    parser.add_argument("--max-jobs", type=int, default=40)
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).resolve().parent / "output")
    parser.add_argument("--no-excel", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    jobs = []
    for url in fetch_links(args.timeout)[: args.max_jobs]:
        jobs.append(normalize(url, args.timeout))
        time.sleep(args.sleep)
    filtered = filter_and_sort_jobs(jobs, args.posted_within_days, not args.keep_w2_f2f_onsite_interview)
    write_outputs("mitchellmartin", filtered, args.out_dir, args.posted_within_days, args.no_excel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
