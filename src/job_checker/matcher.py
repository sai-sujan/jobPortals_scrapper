import re
from typing import Dict, Iterable, List, Tuple

from .models import Job


WORDISH = re.compile(r"[^a-z0-9+#./-]+")


def normalize_text(text: str) -> str:
    return WORDISH.sub(" ", (text or "").lower()).strip()


def contains_term(text: str, term: str) -> bool:
    term = normalize_text(term)
    if not term:
        return False
    if len(term) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text) is not None
    return term in text


def matched_from(text: str, terms: Iterable[str]) -> List[str]:
    return sorted({term for term in terms if contains_term(text, term)}, key=str.lower)


class ResumeMatcher:
    def __init__(self, profile: Dict):
        self.profile = profile["matching"]
        self.must_have_any = self.profile["must_have_any"]
        self.exclusions = self.profile["exclusions"]
        self.title_exclusions = [
            "recruiter",
            "recruiting",
            "sales",
            "account manager",
            "business development",
            "junior",
            "intern",
            "internship",
            "helpdesk",
            "help desk",
            "desktop support",
            "quality assurance",
            "qa",
            "frontend",
            "front-end",
            "java developer",
            "java engineer",
            "java architect",
            "java backend",
            "java software",
            "java full stack",
            "java fullstack",
            "full stack java",
            "fullstack java",
            "senior java",
            "sr java",
            ".net developer",
            "dotnet developer",
            "account login",
            "jobseeker",
            "jobs & careers",
            "jobs and careers",
            "welcome to careers",
            "careers at",
            "energy transition",
        ]
        self.best_min = int(self.profile["best_match_min_score"])
        self.borderline_min = int(self.profile["borderline_min_score"])

    def score(self, job: Job) -> Job:
        text = normalize_text(" ".join([job.title, job.location, job.employment_type, job.description_snippet, job.raw_text]))
        title_text = normalize_text(job.title)
        exclusions = matched_from(title_text, self.title_exclusions)
        must_haves = matched_from(text, self.must_have_any)

        if exclusions:
            job.matched_terms = exclusions
            job.score = 0
            job.match_bucket = "excluded"
            job.status = "excluded"
            return job

        if not must_haves:
            job.matched_terms = []
            job.score = 0
            job.match_bucket = "stored"
            job.status = "non_match"
            return job

        score = 0
        matched: List[str] = []
        for group in self.profile["strong_terms"].values():
            group_matches = matched_from(text, group["terms"])
            matched.extend(group_matches)
            score += len(group_matches) * int(group["weight"])

        seniority_matches = matched_from(text, self.profile["seniority_boost"]["terms"])
        contract_matches = matched_from(text, self.profile["contract_boost"]["terms"])
        matched.extend(seniority_matches)
        matched.extend(contract_matches)
        if seniority_matches:
            score += int(self.profile["seniority_boost"]["weight"])
        if contract_matches:
            score += int(self.profile["contract_boost"]["weight"])
        elif not job.employment_type:
            score += int(self.profile.get("unknown_type_penalty", 0))

        # Title matches matter more because staffing listings often have short descriptions.
        title_boost_terms = [
            "python",
            "django",
            "fastapi",
            "machine learning",
            "gen ai",
            "llm",
            "ai",
            "software engineer",
            "software developer",
            "backend",
            "api",
            "data engineer",
            "cloud engineer",
            "sql",
        ]
        if matched_from(title_text, title_boost_terms):
            score += 12

        job.matched_terms = sorted(set(matched + must_haves), key=str.lower)
        job.score = max(score, 1)
        if job.score >= self.best_min:
            job.match_bucket = "best"
            job.status = "match"
        elif job.score >= self.borderline_min:
            job.match_bucket = "borderline"
            job.status = "match"
        else:
            job.match_bucket = "stored"
            job.status = "non_match"
        return job
