import tempfile
import unittest
from pathlib import Path

from job_checker.models import Job
from job_checker.storage import JobStore


class StorageTest(unittest.TestCase):
    def test_deduplicates_by_canonical_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = JobStore(Path(tmp) / "jobs.sqlite")
            job = Job(
                source_company="Test",
                title="Senior Python Developer",
                job_url="https://example.com/job?x=1",
                canonical_url="https://example.com/job",
                score=55,
                status="match",
                match_bucket="best",
            )
            store.upsert_jobs([job], "2026-05-05T08:00:00")
            job.title = "Senior Python Developer Updated"
            store.upsert_jobs([job], "2026-05-06T08:00:00")
            rows = store.query_jobs("1=1")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Senior Python Developer Updated")
            self.assertEqual(rows[0]["first_seen_at"], "2026-05-05T08:00:00")
            store.close()


if __name__ == "__main__":
    unittest.main()
