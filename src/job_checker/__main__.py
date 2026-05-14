import argparse
import csv
import fcntl
import logging
import multiprocessing
import queue
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from .config import ROOT, load_config
from .matcher import ResumeMatcher
from .models import Job, SiteResult
from .report import export_excel
from .resume import extract_docx_text, extract_resume_terms
from .scheduler import install_launchd, plist_path
from .scraper import scrape_site
from .storage import JobStore
from .worker import scrape_site_process


DEFAULT_SLOW_SITE_THRESHOLD_SECONDS = 15 * 60
DEFAULT_MAX_SITE_DURATION_SECONDS = 15 * 60
DEFAULT_PRIORITY_MAX_SITE_DURATION_SECONDS = 20 * 60
DEFAULT_PARALLEL_WORKERS = 4
RUN_LOCK_PATH = ROOT / "data" / "job_checker.lock"


def site_keys(site) -> set:
    keys = set()
    name = (site.get("name") or "").strip().lower()
    if name:
        keys.add(f"name:{name}")
    urls = [site.get("base_url") or ""]
    urls.extend(site.get("search_url_templates", []))
    urls.extend(site.get("feed_urls", []))
    for url in urls:
        domain = urlparse(str(url).strip()).netloc.lower().removeprefix("www.")
        if domain:
            keys.add(f"domain:{domain}")
    return keys


def is_priority_site(site) -> bool:
    return bool(site.get("priority")) or site.get("group") == "core"


def priority_site_names(sites) -> list:
    return [site["name"] for site in sites if is_priority_site(site)]


def max_duration_for_site(site, run_config) -> int:
    if is_priority_site(site):
        return int(run_config.get("priority_max_site_duration_seconds", DEFAULT_PRIORITY_MAX_SITE_DURATION_SECONDS))
    return int(run_config.get("max_site_duration_seconds", DEFAULT_MAX_SITE_DURATION_SECONDS))


def setup_logging(root: Path) -> None:
    (root / "logs").mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(root / "logs" / "job_checker.log"),
            logging.StreamHandler(),
        ],
    )


def ordered_sites(sites, store: JobStore, run_config):
    threshold = int(run_config.get("slow_site_threshold_seconds", DEFAULT_SLOW_SITE_THRESHOLD_SECONDS))
    minimum_runs = int(run_config.get("slow_site_minimum_runs", 1))
    history_by_site = store.site_run_history(minimum_runs=minimum_runs)
    deduped_sites = {}
    key_to_site_key = {}
    for index, site in enumerate(sites):
        keys = site_keys(site) or {f"site:{index}"}
        existing_key = next((key_to_site_key[key] for key in keys if key in key_to_site_key), None)
        if existing_key is None:
            site_entry_key = next(iter(keys))
            deduped_sites[site_entry_key] = (index, site)
            for key in keys:
                key_to_site_key[key] = site_entry_key
            continue
        existing = deduped_sites[existing_key]
        if is_priority_site(site) and not is_priority_site(existing[1]):
            deduped_sites[existing_key] = (index, site)
            for key in keys:
                key_to_site_key[key] = existing_key

    def sort_key(item):
        index, site = item
        history = history_by_site.get(site["name"], {})
        slowest = max(history.get("avg_duration", 0), history.get("max_duration", 0))
        problem = bool(history.get("failure_count", 0))
        return (not is_priority_site(site), slowest >= threshold or problem, index)

    return [site for _, site in sorted(deduped_sites.values(), key=sort_key)]


def format_duration(seconds: float) -> str:
    total = int(round(seconds))
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def run_sites_parallel(sites, run_config, logger):
    workers = max(1, int(run_config.get("parallel_workers", DEFAULT_PARALLEL_WORKERS)))
    ctx = multiprocessing.get_context("spawn")
    pending = list(sites)
    active = {}
    completed = []

    def start_site(site):
        result_queue = ctx.Queue(maxsize=1)
        process = ctx.Process(target=scrape_site_process, args=(site, run_config, result_queue))
        process.start()
        active[site["name"]] = {
            "site": site,
            "process": process,
            "queue": result_queue,
            "started": time.perf_counter(),
            "checked_at": datetime.now().isoformat(timespec="seconds"),
            "max_duration": max_duration_for_site(site, run_config),
        }
        logger.info("Checking %s", site["name"])

    while pending or active:
        while pending and len(active) < workers:
            start_site(pending.pop(0))

        for name, state in list(active.items()):
            process = state["process"]
            elapsed = time.perf_counter() - state["started"]
            max_duration = state["max_duration"]
            if process.is_alive() and elapsed > max_duration:
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()
                    process.join(timeout=5)
                result = SiteResult(
                    source_company=name,
                    checked_at=state["checked_at"],
                    duration_seconds=elapsed,
                    status="timed_out",
                    error=f"Exceeded site max duration of {max_duration} seconds",
                )
                completed.append((state["site"], [], result))
                logger.warning("%s: duration=%s status=timed_out", name, format_duration(elapsed))
                del active[name]
                continue

            if not process.is_alive():
                process.join()
                try:
                    jobs, result = state["queue"].get(timeout=1)
                except queue.Empty:
                    jobs = []
                    result = SiteResult(
                        source_company=name,
                        checked_at=state["checked_at"],
                        status="failed",
                        error=f"Worker exited without result, exitcode={process.exitcode}",
                    )
                result.duration_seconds = elapsed
                completed.append((state["site"], jobs, result))
                del active[name]

        if active:
            time.sleep(0.2)

    return completed


def doctor(args) -> int:
    config = load_config(ROOT)
    resume_path = ROOT / config["profile"].get("resume_file", "venkataD_resume.docx")
    print(f"Project root: {ROOT}")
    print(f"Resume: {resume_path} {'OK' if resume_path.exists() else 'MISSING'}")
    print(f"SQLite path: {ROOT / 'data' / 'jobs.sqlite'}")
    print(f"Reports dir: {ROOT / 'reports'}")
    print(f"Python: {sys.executable}")
    print(f"launchd plist: {plist_path()}")
    print("Schedule: every 3 hours at 00:00, 03:00, 06:00, 09:00, 12:00, 15:00, 18:00, 21:00")
    if resume_path.exists():
        text = extract_docx_text(resume_path)
        print("Resume terms:", ", ".join(extract_resume_terms(text)))
    print(f"Configured sites: {len(config['sites'].get('sites', []))}")
    return 0


def run(args) -> int:
    setup_logging(ROOT)
    logger = logging.getLogger("job_checker")
    RUN_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = RUN_LOCK_PATH.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        message = "Another job checker run is already active; skipping this overlapping run."
        logger.warning(message)
        print(message)
        lock_handle.close()
        return 0
    config = load_config(ROOT)
    matcher = ResumeMatcher(config["profile"])
    store = JobStore(ROOT / "data" / "jobs.sqlite")
    run_id = store.start_run()
    checked_at = datetime.now().isoformat(timespec="seconds")
    discovered_total = 0
    matched_total = 0
    all_saved = []
    try:
        configured_sites = config["sites"].get("sites", [])
        run_config = dict(config["sites"].get("run", {}))
        if args.priority_deep:
            run_config["max_detail_pages_per_site"] = max(int(run_config.get("max_detail_pages_per_site", 30)), 150)
            run_config["priority_max_site_duration_seconds"] = max(int(run_config.get("priority_max_site_duration_seconds", 1200)), 1800)
            run_config["slow_site_threshold_seconds"] = max(int(run_config.get("slow_site_threshold_seconds", 900)), 1800)
        sites = ordered_sites(configured_sites, store, run_config)
        if args.priority_only:
            sites = [site for site in sites if is_priority_site(site)]
        priority_companies = priority_site_names(configured_sites)
        parallel_workers = int(run_config.get("parallel_workers", 1))
        if parallel_workers > 1:
            site_outputs = run_sites_parallel(sites, run_config, logger)
        else:
            site_outputs = []
            for site in sites:
                site_start = time.perf_counter()
                logger.info("Checking %s", site["name"])
                jobs, site_result = scrape_site(site, run_config)
                site_result.duration_seconds = time.perf_counter() - site_start
                site_outputs.append((site, jobs, site_result))

        for site, jobs, site_result in site_outputs:
            scored = [matcher.score(job) for job in jobs]
            saved = store.upsert_jobs(scored, checked_at)
            site_result.matched_count = sum(1 for job in scored if job.status == "match")
            store.save_site_result(run_id, site_result)
            discovered_total += len(saved)
            matched_total += site_result.matched_count
            all_saved.extend(saved)
            logger.info(
                "%s: discovered=%s matched=%s duration=%s status=%s",
                site["name"],
                len(saved),
                site_result.matched_count,
                format_duration(site_result.duration_seconds),
                site_result.status,
            )
        latest = export_excel(store, run_id, config["profile"], ROOT / "reports", priority_companies)
        export_csv(store, ROOT / "reports" / f"{datetime.now():%Y-%m-%d}_jobs.csv")
        store.finish_run(run_id, discovered_total, matched_total, "ok")
        logger.info("Done. discovered=%s matched=%s report=%s", discovered_total, matched_total, latest)
        print(f"Done. Discovered {discovered_total} jobs, matched {matched_total}. Report: {latest}")
        return 0
    except Exception as exc:
        store.finish_run(run_id, discovered_total, matched_total, "failed", str(exc))
        logger.exception("Run failed")
        return 1
    finally:
        store.close()
        fcntl.flock(lock_handle, fcntl.LOCK_UN)
        lock_handle.close()


def export_csv(store: JobStore, path: Path) -> None:
    rows = store.query_jobs("1=1")
    headers = rows[0].keys() if rows else [
        "source_company",
        "title",
        "job_url",
        "canonical_url",
        "score",
        "status",
        "match_bucket",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row[key] for key in headers])


def rescore(args) -> int:
    setup_logging(ROOT)
    config = load_config(ROOT)
    matcher = ResumeMatcher(config["profile"])
    priority_companies = priority_site_names(config["sites"].get("sites", []))
    store = JobStore(ROOT / "data" / "jobs.sqlite")
    checked_at = datetime.now().isoformat(timespec="seconds")
    run_row = store.conn.execute("SELECT max(id) AS id FROM runs").fetchone()
    run_id = int(run_row["id"] or store.start_run())
    try:
        rows = store.query_jobs("1=1")
        rescored = []
        for row in rows:
            job = Job(
                source_company=row["source_company"],
                title=row["title"],
                job_url=row["job_url"],
                canonical_url=row["canonical_url"],
                location=row["location"] or "",
                remote_status=row["remote_status"] or "",
                employment_type=row["employment_type"] or "",
                posted_date=row["posted_date"] or "",
                contact_info=row["contact_info"] or "",
                description_snippet=row["description_snippet"] or "",
                raw_text=row["description_snippet"] or "",
            )
            rescored.append(matcher.score(job))
        store.upsert_jobs(rescored, checked_at)
        latest = export_excel(store, run_id, config["profile"], ROOT / "reports", priority_companies)
        export_csv(store, ROOT / "reports" / f"{datetime.now():%Y-%m-%d}_jobs.csv")
        print(f"Rescored {len(rescored)} stored links. Report: {latest}")
        return 0
    finally:
        store.close()


def install_schedule(args) -> int:
    path = install_launchd(ROOT, sys.executable)
    print(f"Wrote {path}")
    print(f"Load it with: launchctl load {path}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Personalized daily job checker")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor").set_defaults(func=doctor)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--priority-only", action="store_true", help="check only core/priority portals")
    run_parser.add_argument("--priority-deep", action="store_true", help="use deeper detail-page and timeout settings for priority portals")
    run_parser.set_defaults(func=run)
    sub.add_parser("rescore").set_defaults(func=rescore)
    sub.add_parser("install-schedule").set_defaults(func=install_schedule)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
