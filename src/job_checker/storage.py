import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, List

from .models import Job, SiteResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_company TEXT NOT NULL,
  title TEXT NOT NULL,
  job_url TEXT NOT NULL,
  canonical_url TEXT NOT NULL UNIQUE,
  location TEXT,
  remote_status TEXT,
  employment_type TEXT,
  posted_date TEXT,
  contact_info TEXT,
  description_snippet TEXT,
  matched_terms TEXT,
  score INTEGER DEFAULT 0,
  status TEXT,
  match_bucket TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  last_checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  discovered_count INTEGER DEFAULT 0,
  matched_count INTEGER DEFAULT 0,
  status TEXT,
  error TEXT
);
CREATE TABLE IF NOT EXISTS site_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER,
  source_company TEXT NOT NULL,
  checked_at TEXT NOT NULL,
  discovered_count INTEGER DEFAULT 0,
  matched_count INTEGER DEFAULT 0,
  duration_seconds REAL DEFAULT 0,
  status TEXT,
  error TEXT,
  FOREIGN KEY(run_id) REFERENCES runs(id)
);
"""


class JobStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        site_run_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(site_runs)")}
        if "duration_seconds" not in site_run_columns:
            self.conn.execute("ALTER TABLE site_runs ADD COLUMN duration_seconds REAL DEFAULT 0")
        job_columns = {row["name"] for row in self.conn.execute("PRAGMA table_info(jobs)")}
        if "contact_info" not in job_columns:
            self.conn.execute("ALTER TABLE jobs ADD COLUMN contact_info TEXT")
        self._backfill_site_run_durations()

    def _backfill_site_run_durations(self) -> None:
        runs = self.conn.execute("SELECT id, finished_at FROM runs WHERE finished_at IS NOT NULL").fetchall()
        for run in runs:
            site_rows = self.conn.execute(
                """
                SELECT id, checked_at, duration_seconds
                FROM site_runs
                WHERE run_id=?
                ORDER BY id
                """,
                (run["id"],),
            ).fetchall()
            for index, row in enumerate(site_rows):
                if row["duration_seconds"]:
                    continue
                end_at = site_rows[index + 1]["checked_at"] if index + 1 < len(site_rows) else run["finished_at"]
                try:
                    duration = (datetime.fromisoformat(end_at) - datetime.fromisoformat(row["checked_at"])).total_seconds()
                except ValueError:
                    continue
                if duration > 0:
                    self.conn.execute("UPDATE site_runs SET duration_seconds=? WHERE id=?", (duration, row["id"]))

    def close(self) -> None:
        self.conn.close()

    def start_run(self) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        cur = self.conn.execute("INSERT INTO runs (started_at, status) VALUES (?, ?)", (now, "running"))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, discovered_count: int, matched_count: int, status: str = "ok", error: str = "") -> None:
        now = datetime.now().isoformat(timespec="seconds")
        self.conn.execute(
            "UPDATE runs SET finished_at=?, discovered_count=?, matched_count=?, status=?, error=? WHERE id=?",
            (now, discovered_count, matched_count, status, error, run_id),
        )
        self.conn.commit()

    def save_site_result(self, run_id: int, result: SiteResult) -> None:
        self.conn.execute(
            """
            INSERT INTO site_runs (
              run_id, source_company, checked_at, discovered_count, matched_count,
              duration_seconds, status, error
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                result.source_company,
                result.checked_at,
                result.discovered_count,
                result.matched_count,
                result.duration_seconds,
                result.status,
                result.error,
            ),
        )
        self.conn.commit()

    def upsert_jobs(self, jobs: Iterable[Job], checked_at: str) -> List[Job]:
        saved: List[Job] = []
        for job in jobs:
            existing = self.conn.execute("SELECT first_seen_at FROM jobs WHERE canonical_url=?", (job.canonical_url,)).fetchone()
            first_seen = existing["first_seen_at"] if existing else checked_at
            job.first_seen_at = first_seen
            job.last_seen_at = checked_at
            job.last_checked_at = checked_at
            self.conn.execute(
                """
                INSERT INTO jobs (
                  source_company, title, job_url, canonical_url, location, remote_status, employment_type,
                  posted_date, contact_info, description_snippet, matched_terms, score, status, match_bucket,
                  first_seen_at, last_seen_at, last_checked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_url) DO UPDATE SET
                  source_company=excluded.source_company,
                  title=excluded.title,
                  job_url=excluded.job_url,
                  location=excluded.location,
                  remote_status=excluded.remote_status,
                  employment_type=excluded.employment_type,
                  posted_date=excluded.posted_date,
                  contact_info=excluded.contact_info,
                  description_snippet=excluded.description_snippet,
                  matched_terms=excluded.matched_terms,
                  score=excluded.score,
                  status=excluded.status,
                  match_bucket=excluded.match_bucket,
                  last_seen_at=excluded.last_seen_at,
                  last_checked_at=excluded.last_checked_at
                """,
                (
                    job.source_company,
                    job.title,
                    job.job_url,
                    job.canonical_url,
                    job.location,
                    job.remote_status,
                    job.employment_type,
                    job.posted_date,
                    job.contact_info,
                    job.description_snippet,
                    ", ".join(job.matched_terms),
                    job.score,
                    job.status,
                    job.match_bucket,
                    first_seen,
                    checked_at,
                    checked_at,
                ),
            )
            saved.append(job)
        self.conn.commit()
        return saved

    def query_jobs(self, where: str = "1=1", params=()) -> List[sqlite3.Row]:
        return list(self.conn.execute(f"SELECT * FROM jobs WHERE {where} ORDER BY score DESC, first_seen_at DESC", params))

    def latest_site_runs(self, run_id: int) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM site_runs WHERE run_id=? ORDER BY id", (run_id,)))

    def site_run_history(self, minimum_runs: int = 1) -> dict:
        rows = self.conn.execute(
            """
            SELECT
              source_company,
              AVG(duration_seconds) AS avg_duration,
              MAX(duration_seconds) AS max_duration,
              COUNT(*) AS run_count,
              SUM(CASE WHEN status != 'ok' THEN 1 ELSE 0 END) AS failure_count
            FROM site_runs
            GROUP BY source_company
            HAVING COUNT(*) >= ?
            """,
            (minimum_runs,),
        ).fetchall()
        return {
            row["source_company"]: {
                "avg_duration": float(row["avg_duration"] or 0),
                "max_duration": float(row["max_duration"] or 0),
                "run_count": int(row["run_count"] or 0),
                "failure_count": int(row["failure_count"] or 0),
            }
            for row in rows
        }

    def latest_run_id(self) -> int:
        row = self.conn.execute("SELECT max(id) AS id FROM runs").fetchone()
        return int(row["id"] or 0)

    def companies(self) -> List[str]:
        rows = self.conn.execute("SELECT DISTINCT source_company FROM jobs ORDER BY source_company").fetchall()
        return [row["source_company"] for row in rows]

    def daily_summary(self) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT
                  substr(first_seen_at, 1, 10) AS first_seen_date,
                  CASE strftime('%w', first_seen_at)
                    WHEN '0' THEN 'Sunday'
                    WHEN '1' THEN 'Monday'
                    WHEN '2' THEN 'Tuesday'
                    WHEN '3' THEN 'Wednesday'
                    WHEN '4' THEN 'Thursday'
                    WHEN '5' THEN 'Friday'
                    WHEN '6' THEN 'Saturday'
                  END AS day_name,
                  SUM(CASE WHEN status='match' THEN 1 ELSE 0 END) AS new_matches,
                  SUM(CASE WHEN match_bucket='best' THEN 1 ELSE 0 END) AS best,
                  SUM(CASE WHEN match_bucket='borderline' THEN 1 ELSE 0 END) AS borderline,
                  SUM(CASE WHEN match_bucket='stored' THEN 1 ELSE 0 END) AS stored,
                  SUM(CASE WHEN match_bucket='excluded' THEN 1 ELSE 0 END) AS excluded
                FROM jobs
                GROUP BY substr(first_seen_at, 1, 10)
                ORDER BY first_seen_date DESC
                """
            )
        )

    def company_daily_summary(self) -> List[sqlite3.Row]:
        return list(
            self.conn.execute(
                """
                SELECT
                  substr(first_seen_at, 1, 10) AS first_seen_date,
                  CASE strftime('%w', first_seen_at)
                    WHEN '0' THEN 'Sunday'
                    WHEN '1' THEN 'Monday'
                    WHEN '2' THEN 'Tuesday'
                    WHEN '3' THEN 'Wednesday'
                    WHEN '4' THEN 'Thursday'
                    WHEN '5' THEN 'Friday'
                    WHEN '6' THEN 'Saturday'
                  END AS day_name,
                  source_company,
                  SUM(CASE WHEN status='match' THEN 1 ELSE 0 END) AS new_matches,
                  SUM(CASE WHEN match_bucket='best' THEN 1 ELSE 0 END) AS best,
                  SUM(CASE WHEN match_bucket='borderline' THEN 1 ELSE 0 END) AS borderline,
                  SUM(CASE WHEN match_bucket='stored' THEN 1 ELSE 0 END) AS stored,
                  SUM(CASE WHEN match_bucket='excluded' THEN 1 ELSE 0 END) AS excluded
                FROM jobs
                GROUP BY substr(first_seen_at, 1, 10), source_company
                ORDER BY first_seen_date DESC, source_company
                """
            )
        )
