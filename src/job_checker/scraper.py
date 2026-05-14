import html
import json
import logging
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote_plus, urldefrag, urljoin, urlparse
from urllib.request import ProxyHandler, Request, build_opener
from xml.etree import ElementTree

from .models import Job, SiteResult


LOGGER = logging.getLogger(__name__)
URL_OPENER = build_opener(ProxyHandler({}))


JOB_PATH_HINTS = ("job", "jobs", "career", "careers", "opening", "position")
TITLE_HINTS = (
    "python",
    "django",
    "fastapi",
    "flask",
    "developer",
    "engineer",
    "software",
    "backend",
    "api",
    "rest",
    "machine",
    "ai",
    "ml",
    "llm",
    "rag",
    "genai",
    "generative",
    "openai",
    "langchain",
    "data",
    "etl",
    "sql",
    "cloud",
    "aws",
    "azure",
    "architect",
    "consultant",
)
EMAIL_RE = re.compile(r"(?<![A-Za-z0-9._%+-])([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})(?![A-Za-z0-9._%+-])")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}(?!\d)")
US_LOCATION_SIGNALS = (
    "united states",
    "usa",
    "u.s.",
    "u.s.a",
    "remote us",
    "remote, us",
    "remote - us",
    "remote usa",
)
US_STATE_SIGNALS = (
    "alabama",
    "alaska",
    "arizona",
    "arkansas",
    "california",
    "colorado",
    "connecticut",
    "delaware",
    "florida",
    "georgia",
    "hawaii",
    "idaho",
    "illinois",
    "indiana",
    "iowa",
    "kansas",
    "kentucky",
    "louisiana",
    "maine",
    "maryland",
    "massachusetts",
    "michigan",
    "minnesota",
    "mississippi",
    "missouri",
    "montana",
    "nebraska",
    "nevada",
    "new hampshire",
    "new jersey",
    "new mexico",
    "new york",
    "north carolina",
    "north dakota",
    "ohio",
    "oklahoma",
    "oregon",
    "pennsylvania",
    "rhode island",
    "south carolina",
    "south dakota",
    "tennessee",
    "texas",
    "utah",
    "vermont",
    "virginia",
    "washington",
    "west virginia",
    "wisconsin",
    "wyoming",
    "district of columbia",
)
US_STATE_ABBREVIATIONS = (
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
)
NON_US_LOCATION_SIGNALS = (
    "canada",
    "india",
    "china",
    "united kingdom",
    " uk",
    "england",
    "scotland",
    "ireland",
    "australia",
    "germany",
    "france",
    "spain",
    "italy",
    "netherlands",
    "singapore",
    "mexico",
    "brazil",
    "philippines",
    "poland",
    "romania",
    "sweden",
    "switzerland",
    "europe",
    "emea",
    "apac",
)
C2C_SIGNALS = (
    "c2c",
    "c to c",
    "corp-to-corp",
    "corp to corp",
    "corporation to corporation",
    "inc to inc",
)
CONTRACT_COMPATIBLE_SIGNALS = (
    "contract",
    "contractor",
    "consultant",
    "consulting",
    "temporary",
    "temp",
    "freelance",
    "1099",
)
NON_C2C_SIGNALS = (
    "no c2c",
    "no corp-to-corp",
    "no corp to corp",
    "not c2c",
    "not open to c2c",
    "cannot do c2c",
    "unable to do c2c",
    "w2 only",
    "w-2 only",
    "w 2 only",
    "w2 role",
    "w-2 role",
    "w2 contract",
    "w-2 contract",
    "full-time",
    "full time",
    "full_time",
    "permanent",
    "direct hire",
    "direct-hire",
    "contract-to-hire",
    "contract to hire",
    "c2h",
    "contract 2 hire",
)
GENERIC_NON_JOB_TITLE_SIGNALS = (
    "account login",
    "jobseeker",
    "jobs & careers",
    "jobs and careers",
    "edtech jobs",
    "welcome to careers",
    "careers at",
    "job search",
    "career search",
    "privacy policy",
    "terms of use",
    "energy transition",
)
GENERIC_TITLE_PREFIXES = (
    "careers - ",
    "careers |",
    "careers at ",
    "welcome to careers",
)


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self._current_href: Optional[str] = None
        self._text: List[str] = []
        self.page_text: List[str] = []
        self.json_ld: List[str] = []
        self._script_type = ""
        self._script_text: List[str] = []

    def handle_starttag(self, tag, attrs):
        attr = dict(attrs)
        if tag == "a" and attr.get("href"):
            self._current_href = attr["href"]
            self._text = []
        if tag == "script":
            self._script_type = attr.get("type", "")
            self._script_text = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._text.append(data)
        if self._script_type == "application/ld+json":
            self._script_text.append(data)
        self.page_text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._current_href is not None:
            text = " ".join(part.strip() for part in self._text if part.strip())
            self.links.append((self._current_href, html.unescape(text)))
            self._current_href = None
            self._text = []
        if tag == "script":
            if self._script_type == "application/ld+json":
                self.json_ld.append("".join(self._script_text))
            self._script_type = ""
            self._script_text = []


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(text or "")).strip()


def extract_contact_info(text: str) -> str:
    cleaned = clean_text(text)
    emails = []
    for email in EMAIL_RE.findall(cleaned):
        lowered = email.lower()
        if lowered not in emails:
            emails.append(lowered)
    phones = []
    for phone in PHONE_RE.findall(cleaned):
        normalized = clean_text(phone)
        digits = re.sub(r"\D", "", normalized)
        if len(digits) == 11 and digits.startswith("1"):
            digits = digits[1:]
        if len(digits) != 10 or digits in {"0000000000", "1111111111"}:
            continue
        display = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        if display not in phones:
            phones.append(display)
    return ", ".join(emails + phones)


def canonicalize(url: str) -> str:
    url, _ = urldefrag(url)
    parsed = urlparse(url)
    return parsed._replace(query=parsed.query.strip("&")).geturl().rstrip("/")


def fetch_text(url: str, timeout: int) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 VenkataDoraJobChecker/0.1 (+local personal job search)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with URL_OPENER.open(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return raw.decode(charset, errors="replace")


def fetch_json(url: str, timeout: int, payload: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
    request_headers = {
        "User-Agent": "Mozilla/5.0 VenkataDoraJobChecker/0.1 (+local personal job search)",
        "Accept": "application/json,text/plain,*/*",
    }
    if headers:
        request_headers.update(headers)
    data = None
    method = "GET"
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        method = "POST"
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=request_headers, method=method)
    with URL_OPENER.open(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    return json.loads(raw.decode(charset, errors="replace"))


def has_us_signal(text: str) -> bool:
    lowered = f" {clean_text(text).lower()} "
    if any(signal in lowered for signal in US_LOCATION_SIGNALS):
        return True
    if any(state in lowered for state in US_STATE_SIGNALS):
        return True
    return any(re.search(rf"(^|[^A-Za-z]){abbr}([^A-Za-z]|$)", text or "") for abbr in US_STATE_ABBREVIATIONS)


def has_non_us_signal(text: str) -> bool:
    lowered = f" {clean_text(text).lower()} "
    return any(signal in lowered for signal in NON_US_LOCATION_SIGNALS)


def is_usa_job(job: Job) -> bool:
    location_text = " ".join([job.location or "", job.title or "", job.description_snippet or "", job.raw_text or ""])
    if has_us_signal(location_text):
        return True
    return not has_non_us_signal(location_text)


def filter_usa_jobs(jobs: Iterable[Job], enabled: bool) -> List[Job]:
    if not enabled:
        return list(jobs)
    return [job for job in jobs if is_usa_job(job)]


def is_generic_non_job_page(job: Job) -> bool:
    title = clean_text(job.title).lower()
    if not title:
        return True
    if any(signal in title for signal in GENERIC_NON_JOB_TITLE_SIGNALS):
        return True
    if any(title.startswith(prefix) for prefix in GENERIC_TITLE_PREFIXES):
        return True
    if title in {"careers", "career", "jobs", "job openings", "open positions"}:
        return True
    return False


def filter_generic_non_job_pages(jobs: Iterable[Job]) -> List[Job]:
    return [job for job in jobs if not is_generic_non_job_page(job)]


def job_work_text(job: Job) -> str:
    return clean_text(" ".join([job.title, job.location, job.employment_type, job.description_snippet, job.raw_text])).lower()


def has_disallowed_work_signal(text: str) -> bool:
    return any(signal in text for signal in NON_C2C_SIGNALS)


def has_c2c_signal(text: str) -> bool:
    return any(signal in text for signal in C2C_SIGNALS)


def has_contract_compatible_signal(text: str) -> bool:
    return any(signal in text for signal in CONTRACT_COMPATIBLE_SIGNALS)


def is_c2c_contract_job(job: Job) -> bool:
    text = job_work_text(job)
    if has_disallowed_work_signal(text):
        return False
    return has_c2c_signal(text)


def is_c2c_compatible_contract_job(job: Job) -> bool:
    text = job_work_text(job)
    if has_disallowed_work_signal(text):
        return False
    return has_c2c_signal(text) or has_contract_compatible_signal(text)


def filter_c2c_contract_jobs(jobs: Iterable[Job], enabled: bool, mode: str = "strict") -> List[Job]:
    if not enabled:
        return list(jobs)
    kept = []
    compatible_review = mode == "compatible_review"
    for job in jobs:
        text = job_work_text(job)
        if has_disallowed_work_signal(text):
            continue
        if has_c2c_signal(text):
            job.employment_type = "C2C Contract"
            kept.append(job)
        elif compatible_review and has_contract_compatible_signal(text):
            job.employment_type = "C2C Review - Contract"
            kept.append(job)
    return kept


def filter_strict_c2c_contract_jobs(jobs: Iterable[Job], enabled: bool) -> List[Job]:
    if not enabled:
        return list(jobs)
    kept = []
    for job in jobs:
        if is_c2c_contract_job(job):
            job.employment_type = "C2C Contract"
            kept.append(job)
    return kept


def search_terms_for_template(template: str, run_config: Dict) -> List[str]:
    if "{query}" not in template:
        return [""]
    terms = list(run_config.get("search_terms", ["python"]))
    if run_config.get("usa_only", False):
        suffix = run_config.get("usa_search_suffix", "United States")
        if suffix:
            terms = [f"{term} {suffix}" for term in terms]
    return terms


def parse_json_ld_jobs(company: str, base_url: str, url: str, parser: LinkParser) -> List[Job]:
    jobs: List[Job] = []
    for block in parser.json_ld:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        nodes = payload if isinstance(payload, list) else [payload]
        for node in nodes:
            if isinstance(node, dict) and node.get("@graph"):
                nodes.extend(node["@graph"])
                continue
            if not isinstance(node, dict):
                continue
            node_type = node.get("@type", "")
            if isinstance(node_type, list):
                is_job = "JobPosting" in node_type
            else:
                is_job = node_type == "JobPosting"
            if not is_job:
                continue
            link = node.get("url") or url
            location = ""
            job_location = node.get("jobLocation")
            if isinstance(job_location, dict):
                address = job_location.get("address") or {}
                if isinstance(address, dict):
                    location = ", ".join(str(address.get(k, "")) for k in ("addressLocality", "addressRegion", "addressCountry") if address.get(k))
            description = clean_text(re.sub("<[^>]+>", " ", str(node.get("description", ""))))
            jobs.append(
                Job(
                    source_company=company,
                    title=clean_text(node.get("title", "")) or "Untitled job",
                    job_url=urljoin(base_url, link),
                    canonical_url=canonicalize(urljoin(base_url, link)),
                    location=location,
                    employment_type=clean_text(str(node.get("employmentType", ""))),
                    posted_date=clean_text(str(node.get("datePosted", ""))),
                    contact_info=extract_contact_info(description),
                    description_snippet=description[:900],
                    raw_text=description,
                )
            )
    return jobs


def is_probable_job_link(href: str, text: str) -> bool:
    haystack = f"{href} {text}".lower()
    return any(hint in haystack for hint in JOB_PATH_HINTS) and any(hint in haystack for hint in TITLE_HINTS)


def infer_employment_type(text: str) -> str:
    lowered = text.lower()
    if has_c2c_signal(lowered) and not has_disallowed_work_signal(lowered):
        return "C2C Contract"
    if "contract-to-hire" in lowered or "contract to hire" in lowered or "c2h" in lowered:
        return "Contract-to-hire"
    if has_contract_compatible_signal(lowered):
        return "Contract"
    if "full-time" in lowered or "full time" in lowered:
        return "Full-time"
    if "permanent" in lowered:
        return "Permanent"
    return ""


def infer_remote(text: str) -> str:
    lowered = text.lower()
    if "remote" in lowered:
        return "Remote"
    if "hybrid" in lowered:
        return "Hybrid"
    if "onsite" in lowered or "on-site" in lowered:
        return "Onsite"
    return ""


def build_job_from_detail(company: str, url: str, title_hint: str, body: str) -> Job:
    parser = LinkParser()
    try:
        parser.feed(body)
    except Exception:
        pass
    text = clean_text(" ".join(parser.page_text))
    title = clean_text(title_hint)
    title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.I | re.S)
    if title_match:
        title = clean_text(re.sub(r"\s+\|.*$", "", title_match.group(1))) or title
    return Job(
        source_company=company,
        title=title or "Untitled job",
        job_url=url,
        canonical_url=canonicalize(url),
        location="",
        remote_status=infer_remote(text),
        employment_type=infer_employment_type(text),
        contact_info=extract_contact_info(text),
        description_snippet=text[:900],
        raw_text=text,
    )


def slugify_job_part(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9 ]+", "", value or "")
    value = re.sub(r"\s+", "-", value.strip().lower())
    return value.strip("-")


def akkodis_job_url(row: Dict[str, Any]) -> str:
    title = slugify_job_part(str(row.get("jobTitle") or row.get("jobName") or "job"))
    location = str(row.get("jobLocation") or row.get("location") or "")
    location_prefix = location.split(",", 1)[0]
    location_slug = slugify_job_part(location_prefix)
    job_id = str(row.get("jobId") or "").lower()
    title_location = "-".join(part for part in (title, location_slug) if part)
    return f"https://www.akkodis.com/en-us/careers/job/{title_location}/{job_id}"


def akkodis_search_terms(run_config: Dict) -> List[str]:
    return [str(term).strip() for term in run_config.get("search_terms", ["python"]) if str(term).strip()]


def akkodis_search_payload(term: str) -> Dict[str, Any]:
    return {
        "baseSearchQuery": "",
        "filtersToDisplay": "",
        "selectedFilters": "",
        "queryString": f"&q={term}",
        "range": 0,
        "siteName": "akkodis",
        "brand": "modis",
        "brandFromDictionary": "",
        "countryCookie": "US",
        "langCookie": "en",
    }


def akkodis_row_to_job(company: str, row: Dict[str, Any], detail: Optional[Dict[str, Any]] = None) -> Job:
    detail = detail or {}
    description_html = str(detail.get("jobDescription") or row.get("description") or row.get("clientJobDescription") or "")
    description = clean_text(re.sub("<[^>]+>", " ", description_html))
    title = clean_text(str(detail.get("jobName") or row.get("jobTitle") or "Untitled job"))
    location = clean_text(str(detail.get("location") or row.get("jobLocation") or ""))
    employment_type = clean_text(
        str(
            detail.get("contract")
            or detail.get("contractTypeTitle")
            or row.get("contractTypeTitle")
            or row.get("jobType")
            or ""
        )
    )
    posted_date = clean_text(str(detail.get("jobCreatedDate") or row.get("postedDate") or row.get("jobCreationDate") or ""))
    job_url = akkodis_job_url(row)
    return Job(
        source_company=company,
        title=title,
        job_url=job_url,
        canonical_url=canonicalize(job_url),
        location=location,
        remote_status="Remote" if bool(detail.get("isRemote") or row.get("isRemote")) else "",
        employment_type=infer_employment_type(f"{employment_type} {description}") or employment_type,
        posted_date=posted_date,
        contact_info=extract_contact_info(description),
        description_snippet=description[:900],
        raw_text=description,
    )


def akkodis_detail(row: Dict[str, Any], timeout: int) -> Optional[Dict[str, Any]]:
    job_id = str(row.get("jobId") or "")
    if not job_id:
        return None
    url = f"https://www.akkodis.com/api/data/jobs/job-description-details/{quote_plus(job_id)}/modis/US/en/job-details"
    try:
        detail = fetch_json(url, timeout)
    except Exception as exc:
        LOGGER.debug("Akkodis detail fetch failed for %s: %s", job_id, exc)
        return None
    return detail if isinstance(detail, dict) else None


def akkodis_jobs(site: Dict, run_config: Dict) -> List[Job]:
    timeout = int(run_config.get("request_timeout_seconds", 20))
    max_detail = int(run_config.get("max_detail_pages_per_site", 30))
    sleep_seconds = float(run_config.get("sleep_between_requests_seconds", 1.0))
    search_url = "https://www.akkodis.com/api/data/jobs/summarized"
    seen_ids = set()
    rows: List[Dict[str, Any]] = []

    for term in akkodis_search_terms(run_config):
        try:
            payload = akkodis_search_payload(term)
            result = fetch_json(
                search_url,
                timeout,
                payload=payload,
                headers={
                    "Origin": "https://www.akkodis.com",
                    "Referer": f"https://www.akkodis.com/en-us/careers/job-results?k={quote_plus(term)}",
                },
            )
        except Exception as exc:
            LOGGER.debug("Akkodis search failed for %s: %s", term, exc)
            continue
        for row in result.get("jobs", []) if isinstance(result, dict) else []:
            if not isinstance(row, dict):
                continue
            job_id = str(row.get("jobId") or row.get("externalReference") or "")
            if not job_id or job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            rows.append(row)
        time.sleep(sleep_seconds)

    jobs: List[Job] = []
    for index, row in enumerate(rows):
        detail = akkodis_detail(row, timeout) if index < max_detail else None
        jobs.append(akkodis_row_to_job(site["name"], row, detail))
        if index < max_detail:
            time.sleep(sleep_seconds)
    return jobs


def atom_jobs(site: Dict, timeout: int) -> List[Job]:
    jobs: List[Job] = []
    for feed_url in site.get("feed_urls", []):
        xml_text = fetch_text(feed_url, timeout)
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns) or root.findall("entry")
        for entry in entries:
            title = entry.findtext("atom:title", default="", namespaces=ns) or entry.findtext("title", default="")
            summary = entry.findtext("atom:summary", default="", namespaces=ns) or entry.findtext("summary", default="")
            updated = entry.findtext("atom:updated", default="", namespaces=ns) or entry.findtext("updated", default="")
            link = ""
            for link_node in entry.findall("atom:link", ns) or entry.findall("link"):
                link = link_node.attrib.get("href", "")
                if link:
                    break
            if not link:
                continue
            full_url = urljoin(site["base_url"], link)
            jobs.append(
                Job(
                    source_company=site["name"],
                    title=clean_text(title),
                    job_url=full_url,
                    canonical_url=canonicalize(full_url),
                    posted_date=clean_text(updated),
                    contact_info=extract_contact_info(f"{title} {summary}"),
                    description_snippet=clean_text(summary)[:900],
                    raw_text=clean_text(summary),
                    employment_type=infer_employment_type(f"{title} {summary}"),
                    remote_status=infer_remote(f"{title} {summary}"),
                )
            )
    return jobs


def generic_jobs(site: Dict, run_config: Dict) -> List[Job]:
    timeout = int(run_config.get("request_timeout_seconds", 20))
    max_detail = int(run_config.get("max_detail_pages_per_site", 30))
    sleep_seconds = float(run_config.get("sleep_between_requests_seconds", 1.0))
    seen_urls = set()
    jobs: List[Job] = []
    detail_candidates: List[Tuple[str, str]] = []

    for template in site.get("search_url_templates", []):
        terms = search_terms_for_template(template, run_config)
        for term in terms:
            url = template.format(query=quote_plus(term))
            try:
                body = fetch_text(url, timeout)
            except Exception as exc:
                LOGGER.debug("Search fetch failed for %s: %s", url, exc)
                continue
            parser = LinkParser()
            try:
                parser.feed(body)
            except Exception:
                pass
            jobs.extend(parse_json_ld_jobs(site["name"], site["base_url"], url, parser))
            for href, text in parser.links:
                full_url = canonicalize(urljoin(url, href))
                if full_url in seen_urls:
                    continue
                if urlparse(full_url).netloc and site_domain_match(site["base_url"], full_url) and is_probable_job_link(full_url, text):
                    seen_urls.add(full_url)
                    detail_candidates.append((full_url, text))
            time.sleep(sleep_seconds)

    for detail_url, title_hint in detail_candidates[:max_detail]:
        try:
            body = fetch_text(detail_url, timeout)
            jobs.extend(parse_detail_jobs_or_page(site["name"], site["base_url"], detail_url, title_hint, body))
        except Exception as exc:
            LOGGER.debug("Detail fetch failed for %s: %s", detail_url, exc)
        time.sleep(sleep_seconds)

    unique: Dict[str, Job] = {}
    for job in jobs:
        unique[job.canonical_url] = job
    return list(unique.values())


def parse_detail_jobs_or_page(company: str, base_url: str, detail_url: str, title_hint: str, body: str) -> List[Job]:
    parser = LinkParser()
    try:
        parser.feed(body)
    except Exception:
        pass
    jobs = parse_json_ld_jobs(company, base_url, detail_url, parser)
    if jobs:
        return jobs
    return [build_job_from_detail(company, detail_url, title_hint, body)]


def site_domain_match(base_url: str, candidate_url: str) -> bool:
    base = urlparse(base_url).netloc.replace("www.", "")
    candidate = urlparse(candidate_url).netloc.replace("www.", "")
    return candidate == base or candidate.endswith("." + base) or base.endswith("." + candidate)


def scrape_site(site: Dict, run_config: Dict) -> Tuple[List[Job], SiteResult]:
    checked_at = datetime.now().isoformat(timespec="seconds")
    result = SiteResult(source_company=site["name"], checked_at=checked_at)
    try:
        if site.get("adapter") == "akkodis":
            jobs = akkodis_jobs(site, run_config)
        elif site.get("adapter") == "atom":
            jobs = atom_jobs(site, int(run_config.get("request_timeout_seconds", 20)))
            if site.get("search_url_templates"):
                jobs.extend(generic_jobs(site, run_config))
        else:
            jobs = generic_jobs(site, run_config)
        unique = {job.canonical_url: job for job in jobs if job.canonical_url}
        jobs = filter_generic_non_job_pages(unique.values())
        jobs = filter_usa_jobs(jobs, bool(run_config.get("usa_only", False)))
        jobs = filter_c2c_contract_jobs(jobs, bool(run_config.get("c2c_only", False)), str(run_config.get("c2c_mode", "strict")))
        result.discovered_count = len(jobs)
        return jobs, result
    except Exception as exc:
        result.status = "failed"
        result.error = str(exc)
        LOGGER.exception("Site failed: %s", site["name"])
        return [], result
