from datetime import datetime

from .models import SiteResult
from .scraper import scrape_site


def scrape_site_process(site, run_config, result_queue) -> None:
    try:
        jobs, site_result = scrape_site(site, run_config)
        result_queue.put((jobs, site_result))
    except Exception as exc:
        checked_at = datetime.now().isoformat(timespec="seconds")
        result_queue.put(([], SiteResult(source_company=site["name"], checked_at=checked_at, status="failed", error=str(exc))))
