from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class Job:
    source_company: str
    title: str
    job_url: str
    canonical_url: str
    location: str = ""
    remote_status: str = ""
    employment_type: str = ""
    posted_date: str = ""
    contact_info: str = ""
    description_snippet: str = ""
    raw_text: str = ""
    matched_terms: List[str] = field(default_factory=list)
    score: int = 0
    status: str = "discovered"
    match_bucket: str = "stored"
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    last_checked_at: Optional[str] = None


@dataclass
class SiteResult:
    source_company: str
    checked_at: str
    discovered_count: int = 0
    matched_count: int = 0
    duration_seconds: float = 0.0
    status: str = "ok"
    error: str = ""
    metadata: Dict[str, str] = field(default_factory=dict)
