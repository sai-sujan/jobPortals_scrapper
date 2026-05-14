#!/usr/bin/env python3
"""Local control UI for the separate job scraper folders."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
import time
import urllib.parse
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "job_portal_dashboard_config.json"
PYTHON = sys.executable or "python3"


DEFAULT_KEYWORDS = [
    "python developer",
    "python engineer",
    "full stack developer",
    "full stack engineer",
    "backend developer",
    "software engineer python",
    "data engineer",
    "data engineering",
    "etl developer",
    "ai engineer",
    "machine learning engineer",
    "generative ai",
    "llm",
    "rag",
]


@dataclass(frozen=True)
class Vendor:
    slug: str
    label: str
    folder: str
    scraper: str
    opener: str
    prefix: str
    terms_mode: str = "none"
    page_arg: str = ""
    page_default: int = 0


VENDORS: list[Vendor] = [
    Vendor("teksystems", "TEKsystems", "teksystems_applying_script", "teksystems_scraper.py", "teksystems_open_jobs.py", "teksystems", "file"),
    Vendor("apexsystems", "Apex Systems", "apexsystems_applying_script", "apex_scraper.py", "apex_open_jobs.py", "apex", "file", "rows-per-search", 100),
    Vendor("judgegroup", "Judge Group", "judgegroup_applying_script", "judgegroup_scraper.py", "judgegroup_open_jobs.py", "judgegroup", "file", "max-pages", 3),
    Vendor("beaconhill", "Beacon Hill", "beaconhill_applying_script", "beaconhill_scraper.py", "beaconhill_open_jobs.py", "beaconhill", "file", "max-pages", 3),
    Vendor("akkodis", "Akkodis", "akkodis_applying_script", "akkodis_scraper.py", "akkodis_open_jobs.py", "akkodis", "file", "max-detail-pages", 30),
    Vendor("randstad", "Randstad", "randstad_applying_script", "randstad_scraper.py", "randstad_open_jobs.py", "randstad", "file"),
    Vendor("eliassen", "Eliassen", "eliassen_applying_script", "eliassen_scraper.py", "eliassen_open_jobs.py", "eliassen"),
    Vendor("experis", "Experis", "experis_applying_script", "experis_scraper.py", "experis_open_jobs.py", "experis", "append", "max-pages", 3),
    Vendor("brooksource", "Brooksource", "brooksource_applying_script", "brooksource_scraper.py", "brooksource_open_jobs.py", "brooksource"),
    Vendor("kellymitchell", "KellyMitchell", "kellymitchell_applying_script", "kellymitchell_scraper.py", "kellymitchell_open_jobs.py", "kellymitchell", "append", "jobs-per-page", 50),
    Vendor("mitchellmartin", "Mitchell Martin", "mitchellmartin_applying_script", "mitchellmartin_scraper.py", "mitchellmartin_open_jobs.py", "mitchellmartin", "none", "max-jobs", 40),
    Vendor("cbts", "CBTS", "cbts_applying_script", "cbts_scraper.py", "cbts_open_jobs.py", "cbts", "file"),
    Vendor("roberthalf", "Robert Half", "roberthalf_applying_script", "roberthalf_scraper.py", "roberthalf_open_jobs.py", "roberthalf"),
    Vendor("kforce", "Kforce", "kforce_applying_script", "kforce_scraper.py", "kforce_open_jobs.py", "kforce", "file"),
    Vendor("insightglobal", "Insight Global", "insightglobal_applying_script", "insightglobal_scraper.py", "insightglobal_open_jobs.py", "insightglobal", "append"),
]

VENDOR_BY_SLUG = {vendor.slug: vendor for vendor in VENDORS}

ROTATION_PAIRS = [
    ["teksystems", "apexsystems"],
    ["judgegroup", "beaconhill"],
    ["akkodis", "randstad"],
    ["eliassen", "experis"],
    ["brooksource", "kellymitchell"],
    ["mitchellmartin", "cbts"],
    ["roberthalf", "kforce"],
    ["insightglobal", "teksystems"],
]

RUN_LOCK = threading.Lock()
RUNS: dict[str, dict[str, Any]] = {}


def default_config() -> dict[str, Any]:
    return {
        "posted_within_days": 4,
        "open_limit": 8,
        "start_at": 1,
        "delay": 0.5,
        "keep_open_minutes": 60,
        "keywords": DEFAULT_KEYWORDS,
        "vendor_overrides": {},
    }


def load_config() -> dict[str, Any]:
    config = default_config()
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                config.update(saved)
        except json.JSONDecodeError:
            pass
    config["keywords"] = normalize_keywords(config.get("keywords"))
    return config


def save_config(config: dict[str, Any]) -> None:
    clean = default_config()
    clean.update(config)
    clean["keywords"] = normalize_keywords(clean.get("keywords"))
    CONFIG_PATH.write_text(json.dumps(clean, indent=2), encoding="utf-8")


def normalize_keywords(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = value.splitlines()
    elif isinstance(value, list):
        parts = [str(item) for item in value]
    else:
        parts = []
    seen: set[str] = set()
    keywords: list[str] = []
    for part in parts:
        keyword = " ".join(part.strip().split())
        key = keyword.lower()
        if keyword and key not in seen:
            seen.add(key)
            keywords.append(keyword)
    return keywords or DEFAULT_KEYWORDS[:]


def nth_workday_index(today: date | None = None) -> int:
    today = today or date.today()
    anchor = date(2026, 5, 11)
    step = 1 if today >= anchor else -1
    current = anchor
    count = 0
    while current != today:
        current += timedelta(days=step)
        if current.weekday() < 5:
            count += step
    return count


def active_pair_for(day: date | None = None) -> list[str]:
    index = nth_workday_index(day) % len(ROTATION_PAIRS)
    return ROTATION_PAIRS[index]


def rotation_preview(days: int = 10) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    current = date.today()
    while len(rows) < days:
        if current.weekday() < 5:
            pair = active_pair_for(current)
            rows.append({
                "date": current.isoformat(),
                "weekday": current.strftime("%A"),
                "vendors": [VENDOR_BY_SLUG[slug].label for slug in pair],
                "slugs": pair,
            })
        current += timedelta(days=1)
    return rows


def latest_jobs_file(vendor: Vendor) -> Path | None:
    out_dir = ROOT / vendor.folder / "output"
    files = sorted(out_dir.glob(f"{vendor.prefix}_jobs_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    return files[0] if files else None


def vendor_status(vendor: Vendor) -> dict[str, Any]:
    latest = latest_jobs_file(vendor)
    count = 0
    modified = ""
    if latest:
        try:
            data = json.loads(latest.read_text(encoding="utf-8"))
            count = len(data) if isinstance(data, list) else 0
            modified = datetime.fromtimestamp(latest.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        except (OSError, json.JSONDecodeError):
            count = 0
    return {
        **asdict(vendor),
        "latest_file": str(latest.relative_to(ROOT)) if latest else "",
        "latest_count": count,
        "latest_modified": modified,
        "active_today": vendor.slug in active_pair_for(),
    }


def command_for_scrape(vendor: Vendor, config: dict[str, Any]) -> list[str]:
    cmd = [
        PYTHON,
        str(ROOT / vendor.folder / vendor.scraper),
        "--posted-within-days",
        str(int(config.get("posted_within_days") or 0)),
    ]
    if vendor.terms_mode == "file":
        terms_path = ROOT / vendor.folder / ".dashboard_terms.txt"
        terms_path.write_text("\n".join(normalize_keywords(config.get("keywords"))) + "\n", encoding="utf-8")
        cmd.extend(["--terms-file", str(terms_path)])
    elif vendor.terms_mode == "append":
        for keyword in normalize_keywords(config.get("keywords")):
            cmd.extend(["--term", keyword])
    overrides = config.get("vendor_overrides") if isinstance(config.get("vendor_overrides"), dict) else {}
    vendor_override = overrides.get(vendor.slug) if isinstance(overrides.get(vendor.slug), dict) else {}
    page_value = vendor_override.get(vendor.page_arg) if vendor.page_arg else None
    if vendor.page_arg and page_value not in (None, ""):
        cmd.extend([f"--{vendor.page_arg}", str(int(page_value))])
    return cmd


def command_for_open(vendor: Vendor, config: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    cmd = [
        PYTHON,
        str(ROOT / vendor.folder / vendor.opener),
        "--limit",
        str(int(payload.get("limit") or config.get("open_limit") or 0)),
        "--start-at",
        str(int(payload.get("start_at") or config.get("start_at") or 1)),
    ]
    if "delay" in opener_help(vendor):
        cmd.extend(["--delay", str(float(payload.get("delay") or config.get("delay") or 0.5))])
    if "keep-open-minutes" in opener_help(vendor):
        cmd.extend(["--keep-open-minutes", str(int(payload.get("keep_open_minutes") or config.get("keep_open_minutes") or 60))])
    return cmd


def opener_help(vendor: Vendor) -> str:
    path = ROOT / vendor.folder / vendor.opener
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def start_run(kind: str, vendor_slugs: list[str], config: dict[str, Any]) -> str:
    run_id = datetime.now().strftime("%Y%m%d%H%M%S")
    RUNS[run_id] = {
        "id": run_id,
        "kind": kind,
        "status": "running",
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "finished_at": "",
        "vendors": vendor_slugs,
        "steps": [],
        "log": "",
    }
    thread = threading.Thread(target=run_scrapers, args=(run_id, vendor_slugs, config), daemon=True)
    thread.start()
    return run_id


def run_scrapers(run_id: str, vendor_slugs: list[str], config: dict[str, Any]) -> None:
    for slug in vendor_slugs:
        vendor = VENDOR_BY_SLUG[slug]
        step_started = datetime.now()
        step = {
            "vendor": vendor.label,
            "slug": slug,
            "status": "running",
            "count": 0,
            "output": "",
            "started_at": step_started.isoformat(timespec="seconds"),
            "finished_at": "",
            "duration_seconds": None,
            "summary": "",
        }
        RUNS[run_id]["steps"].append(step)
        before = latest_jobs_file(vendor)
        cmd = command_for_scrape(vendor, config)
        try:
            proc = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, timeout=900)
            step_finished = datetime.now()
            after = latest_jobs_file(vendor)
            status = vendor_status(vendor)
            output = (proc.stdout + "\n" + proc.stderr).strip()
            step.update({
                "status": "done" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "count": status["latest_count"] if proc.returncode == 0 else 0,
                "latest_file": status["latest_file"],
                "changed": str(before) != str(after),
                "output": output[-5000:],
                "summary": summarize_scraper_output(output),
                "finished_at": step_finished.isoformat(timespec="seconds"),
                "duration_seconds": round((step_finished - step_started).total_seconds(), 1),
            })
        except Exception as exc:  # noqa: BLE001 - surface failures in the UI.
            step_finished = datetime.now()
            step.update({
                "status": "failed",
                "output": str(exc),
                "summary": str(exc),
                "returncode": -1,
                "finished_at": step_finished.isoformat(timespec="seconds"),
                "duration_seconds": round((step_finished - step_started).total_seconds(), 1),
            })
    RUNS[run_id]["status"] = "done" if all(step["status"] == "done" for step in RUNS[run_id]["steps"]) else "failed"
    RUNS[run_id]["finished_at"] = datetime.now().isoformat(timespec="seconds")


def summarize_scraper_output(output: str) -> str:
    if not output:
        return ""
    interesting_prefixes = ("Extracted ", "Saved ", "CSV:", "JSON:", "Excel:")
    lines = []
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith(interesting_prefixes):
            lines.append(stripped)
    return " | ".join(lines[-5:])


def open_vendor(slug: str, config: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    vendor = VENDOR_BY_SLUG[slug]
    cmd = command_for_open(vendor, config, payload)
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return {"status": "started", "pid": proc.pid, "vendor": vendor.label}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self.send_html(HTML)
        elif parsed.path == "/api/config":
            self.send_json({"config": load_config(), "vendors": [vendor_status(v) for v in VENDORS], "rotation": rotation_preview()})
        elif parsed.path == "/api/status":
            self.send_json({"runs": list(RUNS.values())[-10:], "vendors": [vendor_status(v) for v in VENDORS], "rotation": rotation_preview()})
        else:
            self.send_error(404)

    def do_POST(self) -> None:  # noqa: N802
        payload = self.read_json()
        config = load_config()
        if self.path == "/api/config":
            config.update(payload)
            save_config(config)
            self.send_json({"ok": True, "config": load_config()})
            return
        if self.path == "/api/scrape":
            with RUN_LOCK:
                active = any(run.get("status") == "running" for run in RUNS.values())
                if active:
                    self.send_json({"ok": False, "error": "A scrape is already running."}, status=409)
                    return
                mode = payload.get("mode") or "selected"
                if mode == "all":
                    slugs = [vendor.slug for vendor in VENDORS]
                elif mode == "today":
                    slugs = active_pair_for()
                else:
                    slugs = [slug for slug in payload.get("vendors", []) if slug in VENDOR_BY_SLUG]
                if not slugs:
                    self.send_json({"ok": False, "error": "No vendors selected."}, status=400)
                    return
                run_id = start_run(mode, slugs, config)
                self.send_json({"ok": True, "run_id": run_id})
            return
        if self.path == "/api/open":
            slug = str(payload.get("vendor") or "")
            if slug not in VENDOR_BY_SLUG:
                self.send_json({"ok": False, "error": "Unknown vendor."}, status=400)
                return
            try:
                result = open_vendor(slug, config, payload)
            except Exception as exc:  # noqa: BLE001
                self.send_json({"ok": False, "error": str(exc)}, status=500)
                return
            self.send_json({"ok": True, **result})
            return
        self.send_error(404)

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Job Portal Control</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1d242b;
      --muted: #65717d;
      --line: #d8dee4;
      --paper: #f7f8fa;
      --panel: #ffffff;
      --brand: #136f63;
      --brand-2: #8a5a12;
      --danger: #a73333;
      --good-bg: #eaf6ef;
      --warn-bg: #fff4df;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: var(--paper);
    }
    header {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 20px;
      padding: 24px 28px 18px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1, h2, h3 { margin: 0; letter-spacing: 0; }
    h1 { font-size: 25px; line-height: 1.15; }
    h2 { font-size: 17px; }
    h3 { font-size: 14px; }
    .sub { margin-top: 7px; color: var(--muted); font-size: 14px; }
    main {
      display: grid;
      grid-template-columns: 340px 1fr;
      min-height: calc(100vh - 86px);
    }
    aside {
      padding: 20px;
      border-right: 1px solid var(--line);
      background: #fbfbfc;
    }
    section { padding: 20px 24px 28px; }
    .block {
      border-bottom: 1px solid var(--line);
      padding: 0 0 18px;
      margin-bottom: 18px;
    }
    .block:last-child { border-bottom: 0; }
    label { display: block; font-size: 12px; font-weight: 700; color: #34404b; margin-bottom: 7px; }
    input, textarea, select {
      width: 100%;
      border: 1px solid #c9d1d9;
      background: white;
      border-radius: 6px;
      padding: 9px 10px;
      font: inherit;
      font-size: 14px;
      color: var(--ink);
    }
    textarea { min-height: 190px; resize: vertical; line-height: 1.35; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .buttons { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
    button {
      border: 1px solid #b9c2cb;
      background: white;
      color: var(--ink);
      min-height: 36px;
      border-radius: 6px;
      padding: 0 12px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
    }
    button.primary { background: var(--brand); color: white; border-color: var(--brand); }
    button.secondary { background: #26323f; color: white; border-color: #26323f; }
    button.warn { background: var(--brand-2); color: white; border-color: var(--brand-2); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    table {
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
    }
    th, td { text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--line); font-size: 13px; vertical-align: middle; }
    th { background: #eef1f4; font-size: 12px; color: #3d4852; }
    tr.active td { background: var(--good-bg); }
    tr:last-child td { border-bottom: 0; }
    .toolbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      margin-bottom: 14px;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 28px;
      min-height: 24px;
      padding: 2px 8px;
      border-radius: 999px;
      background: #e8edf2;
      font-weight: 800;
      font-size: 12px;
    }
    .active-pill { background: #cdeedb; color: #075f3e; }
    .zero { color: var(--muted); }
    .log {
      margin-top: 18px;
      background: #101820;
      color: #d8e5ee;
      padding: 12px;
      border-radius: 8px;
      min-height: 120px;
      max-height: 260px;
      overflow: auto;
      white-space: pre-wrap;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }
    .rotation {
      display: grid;
      grid-template-columns: repeat(5, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }
    .day {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      min-height: 88px;
    }
    .day.today { border-color: #73b894; background: var(--good-bg); }
    .date { font-size: 12px; font-weight: 800; margin-bottom: 6px; }
    .names { color: #34404b; font-size: 13px; line-height: 1.35; }
    .notice {
      background: var(--warn-bg);
      border: 1px solid #e0c891;
      border-radius: 8px;
      padding: 10px 12px;
      font-size: 13px;
      color: #513b10;
      margin-bottom: 14px;
    }
    @media (max-width: 980px) {
      header { align-items: start; flex-direction: column; }
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .rotation { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Job Portal Control</h1>
      <div class="sub">Daily scrape all portals. Actively open two weekday portals from the rotation.</div>
    </div>
    <div class="buttons">
      <button class="primary" id="scrapeAll">Scrape All 15</button>
      <button class="secondary" id="scrapeToday">Scrape Today's 2</button>
      <button id="refresh">Refresh</button>
    </div>
  </header>
  <main>
    <aside>
      <div class="block">
        <h2>Filters</h2>
        <div class="sub">These values are passed into each scraper that supports them.</div>
        <div class="row" style="margin-top:12px">
          <div>
            <label for="days">Posted within days</label>
            <input id="days" type="number" min="0" step="1">
          </div>
          <div>
            <label for="openLimit">Open limit</label>
            <input id="openLimit" type="number" min="0" step="1">
          </div>
        </div>
        <div class="row" style="margin-top:10px">
          <div>
            <label for="startAt">Start at</label>
            <input id="startAt" type="number" min="1" step="1">
          </div>
          <div>
            <label for="keepOpen">Keep open minutes</label>
            <input id="keepOpen" type="number" min="1" step="1">
          </div>
        </div>
      </div>
      <div class="block">
        <label for="keywords">Keywords</label>
        <textarea id="keywords" spellcheck="false"></textarea>
        <div class="buttons">
          <button class="primary" id="save">Save Controls</button>
        </div>
      </div>
      <div class="block">
        <h2>Open Jobs</h2>
        <div class="sub">Choose a portal, then open latest filtered results.</div>
        <div style="margin-top:12px">
          <label for="openVendor">Portal</label>
          <select id="openVendor"></select>
        </div>
        <div class="buttons">
          <button class="warn" id="openSelected">Open Selected</button>
          <button id="openToday">Open Today's 2</button>
        </div>
      </div>
      <div class="notice">Weekends are skipped for the two-portal rotation. Scrape All 15 is the daily safety net.</div>
    </aside>
    <section>
      <div class="toolbar">
        <h2>Weekday Rotation</h2>
        <span class="pill" id="runState">idle</span>
      </div>
      <div class="rotation" id="rotation"></div>
      <div class="toolbar">
        <h2>Portals</h2>
        <div class="buttons">
          <button id="scrapeSelected">Scrape Checked</button>
        </div>
      </div>
      <table>
        <thead>
          <tr>
            <th><input type="checkbox" id="toggleAll"></th>
            <th>Portal</th>
            <th>Today</th>
            <th>Latest Jobs</th>
            <th>Latest Output</th>
            <th>Controls</th>
          </tr>
        </thead>
        <tbody id="vendors"></tbody>
      </table>
      <div class="log" id="log">Ready.</div>
    </section>
  </main>
  <script>
    const state = {
      vendors: [],
      rotation: [],
      config: {},
      runs: [],
      configLoaded: false,
      configDirty: false,
      selectedVendor: "",
      checkedVendors: new Set(),
      vendorChecksTouched: false,
    };
    const $ = (id) => document.getElementById(id);

    async function api(path, options = {}) {
      const response = await fetch(path, {
        headers: { "Content-Type": "application/json" },
        ...options,
      });
      const data = await response.json();
      if (!response.ok || data.ok === false) throw new Error(data.error || response.statusText);
      return data;
    }

    function readConfig() {
      return {
        posted_within_days: Number($("days").value || 0),
        open_limit: Number($("openLimit").value || 0),
        start_at: Number($("startAt").value || 1),
        keep_open_minutes: Number($("keepOpen").value || 60),
        keywords: $("keywords").value.split(/\n+/).map((x) => x.trim()).filter(Boolean),
      };
    }

    async function saveConfig() {
      const data = await api("/api/config", { method: "POST", body: JSON.stringify(readConfig()) });
      state.config = data.config || readConfig();
      state.configDirty = false;
      renderConfig();
      await refreshStatus();
    }

    function renderConfig() {
      if (state.configDirty) return;
      $("days").value = state.config.posted_within_days ?? 4;
      $("openLimit").value = state.config.open_limit ?? 8;
      $("startAt").value = state.config.start_at ?? 1;
      $("keepOpen").value = state.config.keep_open_minutes ?? 60;
      $("keywords").value = (state.config.keywords || []).join("\n");
    }

    function renderRotation() {
      const today = new Date().toISOString().slice(0, 10);
      $("rotation").innerHTML = state.rotation.slice(0, 5).map((row) => `
        <div class="day ${row.date === today ? "today" : ""}">
          <div class="date">${row.weekday}<br>${row.date}</div>
          <div class="names">${row.vendors.join("<br>")}</div>
        </div>
      `).join("");
    }

    function renderVendors() {
      const previousVendor = state.selectedVendor || $("openVendor").value;
      const previousChecks = new Set([...document.querySelectorAll(".pick:checked")].map((item) => item.value));
      if (state.vendorChecksTouched) state.checkedVendors = previousChecks;

      $("openVendor").innerHTML = state.vendors.map((v) => `<option value="${v.slug}">${v.label}</option>`).join("");
      const validVendor = state.vendors.some((v) => v.slug === previousVendor);
      $("openVendor").value = validVendor ? previousVendor : (state.vendors[0]?.slug || "");
      state.selectedVendor = $("openVendor").value;

      $("vendors").innerHTML = state.vendors.map((v) => `
        <tr class="${v.active_today ? "active" : ""}">
          <td><input class="pick" type="checkbox" value="${v.slug}" ${(state.vendorChecksTouched ? state.checkedVendors.has(v.slug) : v.active_today) ? "checked" : ""}></td>
          <td><strong>${v.label}</strong></td>
          <td>${v.active_today ? '<span class="pill active-pill">active</span>' : ""}</td>
          <td class="${v.latest_count ? "" : "zero"}">${v.latest_count}</td>
          <td>${v.latest_file ? `${v.latest_file}<br><span class="sub">${v.latest_modified}</span>` : '<span class="zero">No output yet</span>'}</td>
          <td><button data-open="${v.slug}">Open</button></td>
        </tr>
      `).join("");
      document.querySelectorAll("[data-open]").forEach((button) => {
        button.addEventListener("click", () => openPortal(button.dataset.open));
      });
      document.querySelectorAll(".pick").forEach((box) => {
        box.addEventListener("change", () => {
          state.vendorChecksTouched = true;
          state.checkedVendors = new Set([...document.querySelectorAll(".pick:checked")].map((item) => item.value));
        });
      });
      updateToggleAll();
    }

    function renderRuns() {
      const latest = state.runs[state.runs.length - 1];
      $("runState").textContent = latest ? latest.status : "idle";
      if (!latest) return;
      const freshNote = latest.kind === "today" ? "Fresh scrape from page/API start for today's 2 portals" : "Fresh scrape run";
      const lines = [`Run ${latest.id} - ${latest.kind} - ${latest.status}`, freshNote];
      for (const step of latest.steps || []) {
        const countText = step.status === "running" ? "scraping from beginning..." : `${step.count ?? 0} jobs`;
        const duration = step.duration_seconds == null ? "" : ` in ${step.duration_seconds}s`;
        const freshness = step.changed ? "new output" : "no new file";
        lines.push(`${step.status.padEnd(7)} ${step.vendor}: ${countText}${duration} (${freshness})`);
        if (step.latest_file) lines.push(`        file: ${step.latest_file}`);
        if (step.summary) lines.push(`        ${step.summary}`);
        if (step.status === "failed" && step.output) lines.push(step.output);
      }
      $("log").textContent = lines.join("\n");
    }

    async function refresh() {
      const configData = await api("/api/config");
      state.config = configData.config || {};
      state.configLoaded = true;
      renderConfig();
      await refreshStatus();
    }

    async function refreshStatus() {
      const data = await api("/api/status");
      state.runs = data.runs || [];
      state.vendors = data.vendors || [];
      state.rotation = data.rotation || [];
      renderRotation();
      renderVendors();
      renderRuns();
    }

    async function scrape(mode, vendors = []) {
      await saveConfig();
      await api("/api/scrape", { method: "POST", body: JSON.stringify({ mode, vendors }) });
      $("log").textContent = mode === "today"
        ? "Fresh scrape started for today's 2 portals from the beginning. Old counts remain visible until new output finishes."
        : "Fresh scrape started. Old counts remain visible until new output finishes.";
      setTimeout(refresh, 1200);
    }

    function selectedVendors() {
      state.vendorChecksTouched = true;
      state.checkedVendors = new Set([...document.querySelectorAll(".pick:checked")].map((item) => item.value));
      return [...state.checkedVendors];
    }

    async function openPortal(slug) {
      await saveConfig();
      const payload = { vendor: slug, limit: Number($("openLimit").value || 0), start_at: Number($("startAt").value || 1), keep_open_minutes: Number($("keepOpen").value || 60) };
      await api("/api/open", { method: "POST", body: JSON.stringify(payload) });
      $("log").textContent = `Opening ${slug} jobs in the browser.`;
    }

    $("save").addEventListener("click", saveConfig);
    $("refresh").addEventListener("click", refreshStatus);
    $("scrapeAll").addEventListener("click", () => scrape("all"));
    $("scrapeToday").addEventListener("click", () => scrape("today"));
    $("scrapeSelected").addEventListener("click", () => scrape("selected", selectedVendors()));
    $("openSelected").addEventListener("click", () => openPortal($("openVendor").value));
    $("openToday").addEventListener("click", async () => {
      for (const vendor of state.vendors.filter((v) => v.active_today)) await openPortal(vendor.slug);
    });
    $("toggleAll").addEventListener("change", (event) => {
      state.vendorChecksTouched = true;
      document.querySelectorAll(".pick").forEach((box) => { box.checked = event.target.checked; });
      state.checkedVendors = new Set([...document.querySelectorAll(".pick:checked")].map((item) => item.value));
      updateToggleAll();
    });
    $("openVendor").addEventListener("change", (event) => { state.selectedVendor = event.target.value; });
    ["days", "openLimit", "startAt", "keepOpen", "keywords"].forEach((id) => {
      $(id).addEventListener("input", () => { state.configDirty = true; });
    });
    setInterval(refreshStatus, 5000);
    refresh().catch((error) => { $("log").textContent = error.message; });

    function updateToggleAll() {
      const boxes = [...document.querySelectorAll(".pick")];
      if (!boxes.length) return;
      const checked = boxes.filter((box) => box.checked).length;
      $("toggleAll").checked = checked === boxes.length;
      $("toggleAll").indeterminate = checked > 0 && checked < boxes.length;
    }
  </script>
</body>
</html>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local job portal control UI.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    save_config(load_config())
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Job portal dashboard: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
