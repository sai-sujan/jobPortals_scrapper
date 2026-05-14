#!/usr/bin/env python3
"""Fill and optionally submit a Judge Group application in Chrome."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


DEFAULT_JOB_URL = "https://www.judge.com/jobs/details/1132024/"
DEFAULT_RESUME = Path(os.environ.get("JOB_PORTAL_RESUME", "resume.docx")).expanduser()


@dataclass(frozen=True)
class Applicant:
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    country: str = "United States"
    street_address: str = "Jersey city"
    city: str = "Jersey City"
    state: str = "NJ"
    zip_code: str = "08540"


def close_cookie_banner(page: Page) -> None:
    for name in (r"accept all", r"reject all"):
        try:
            button = page.get_by_role("button", name=re.compile(name, re.I)).first
            if button.is_visible(timeout=1500):
                button.click(timeout=2500)
                page.wait_for_timeout(400)
                return
        except PlaywrightTimeoutError:
            pass


def fill_by_label(page: Page, label: str, value: str) -> None:
    field = page.get_by_label(re.compile(rf"^{re.escape(label)}\s*\*?$", re.I)).first
    field.fill(value, timeout=7000)


def select_country(page: Page, country: str) -> None:
    country_field = page.get_by_label(re.compile(r"^country$", re.I)).first
    try:
        country_field.select_option(label=country, timeout=5000)
        return
    except Exception:
        pass

    # Fallback for non-native selects.
    country_field.click(timeout=5000)
    page.get_by_text(country, exact=True).click(timeout=5000)


def fill_application(page: Page, applicant: Applicant, resume_path: Path) -> None:
    close_cookie_banner(page)
    page.get_by_role("heading", name=re.compile(r"apply now", re.I)).scroll_into_view_if_needed(timeout=10000)

    fill_by_label(page, "FIRST NAME", applicant.first_name)
    fill_by_label(page, "LAST NAME", applicant.last_name)
    fill_by_label(page, "EMAIL", applicant.email)
    fill_by_label(page, "PHONE NUMBER", applicant.phone)
    select_country(page, applicant.country)
    fill_by_label(page, "STREET ADDRESS", applicant.street_address)
    fill_by_label(page, "CITY", applicant.city)
    fill_by_label(page, "STATE/REGION", applicant.state)
    fill_by_label(page, "ZIP / POSTAL CODE", applicant.zip_code)

    file_input = page.locator("input[type='file']").first
    file_input.set_input_files(str(resume_path))
    page.wait_for_timeout(1500)


def submit_application(page: Page) -> None:
    submit = page.get_by_role("button", name=re.compile(r"submit application", re.I)).first
    submit.scroll_into_view_if_needed(timeout=5000)
    submit.click(timeout=10000)


def submission_status(page: Page) -> str:
    page.wait_for_timeout(5000)
    status_patterns = [
        r"thank you",
        r"application (?:has been )?submitted",
        r"success",
        r"received",
    ]
    body = page.locator("body").inner_text(timeout=10000)
    for pattern in status_patterns:
        if re.search(pattern, body, re.I):
            return f"possible_success: matched '{pattern}' at {page.url}"
    try:
        submit = page.get_by_role("button", name=re.compile(r"submit application", re.I)).first
        if submit.is_visible(timeout=1500):
            return f"unknown: submit button still visible at {page.url}"
    except Exception:
        pass
    return f"unknown: no success text found at {page.url}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill a Judge Group job application in Chrome.")
    parser.add_argument("--url", default=DEFAULT_JOB_URL, help="Judge Group job details URL.")
    parser.add_argument("--resume", type=Path, default=DEFAULT_RESUME)
    parser.add_argument("--first-name", default=Applicant.first_name)
    parser.add_argument("--last-name", default=Applicant.last_name)
    parser.add_argument("--email", default=Applicant.email)
    parser.add_argument("--phone", default=Applicant.phone)
    parser.add_argument("--country", default=Applicant.country)
    parser.add_argument("--street-address", default=Applicant.street_address)
    parser.add_argument("--city", default=Applicant.city)
    parser.add_argument("--state", default=Applicant.state)
    parser.add_argument("--zip-code", default=Applicant.zip_code)
    parser.add_argument("--submit", action="store_true", help="Click Submit Application after filling.")
    parser.add_argument("--keep-open-seconds", type=int, default=45)
    parser.add_argument(
        "--screenshot",
        type=Path,
        help="Path for a screenshot after fill/submit. Defaults to judgegroup_applying_script/output/apply_*.png.",
    )
    parser.add_argument("--browser-channel", default="chrome", help="Use installed Google Chrome by default.")
    parser.add_argument("--slow-mo", type=int, default=200)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = [
        name
        for name, value in (
            ("first name", args.first_name),
            ("last name", args.last_name),
            ("email", args.email),
            ("phone", args.phone),
            ("street address", args.street_address),
            ("city", args.city),
            ("state", args.state),
            ("zip code", args.zip_code),
        )
        if not value
    ]
    if missing:
        print(f"Missing applicant {', '.join(missing)}. Pass the values with flags or dashboard settings.", file=sys.stderr)
        return 2
    resume_path = args.resume.expanduser().resolve()
    if not resume_path.exists():
        print(f"Resume not found: {resume_path}", file=sys.stderr)
        return 2
    screenshot_path = args.screenshot
    if screenshot_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        screenshot_path = Path(__file__).resolve().parent / "output" / f"apply_{stamp}.png"
    screenshot_path = screenshot_path.expanduser().resolve()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)

    applicant = Applicant(
        first_name=args.first_name,
        last_name=args.last_name,
        email=args.email,
        phone=args.phone,
        country=args.country,
        street_address=args.street_address,
        city=args.city,
        state=args.state,
        zip_code=args.zip_code,
    )

    print(f"Opening Chrome: {args.url}")
    print(f"Resume: {resume_path}")
    print("Mode: submit" if args.submit else "Mode: fill only")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel=args.browser_channel, headless=False, slow_mo=args.slow_mo)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2500)
            fill_application(page, applicant, resume_path)
            print("Filled application fields and attached resume.")

            if args.submit:
                submit_application(page)
                print("Clicked Submit Application.")
                print(f"Post-submit status: {submission_status(page)}")
            else:
                print("Submit was not clicked. Re-run with --submit to submit automatically.")

            page.screenshot(path=str(screenshot_path), full_page=True)
            print(f"Screenshot: {screenshot_path}")
            page.wait_for_timeout(max(args.keep_open_seconds, 1) * 1000)
        finally:
            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
