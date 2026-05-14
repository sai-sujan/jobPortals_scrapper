import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_vendor_filters import VendorJob, filter_and_sort_jobs


def make_job(title: str) -> VendorJob:
    return VendorJob(
        source_company="Test",
        search_term="test",
        title_rank=100,
        title_rank_reasons="test",
        title=title,
        category="",
        location="",
        employment_type="Contract",
        salary="",
        posted_date="",
        job_id=title,
        job_url=f"https://example.com/{title}",
        apply_url="",
        contact_info="",
        description_snippet="",
        raw_text="Contract role.",
    )


class SharedVendorFilterTest(unittest.TestCase):
    def test_java_titles_are_excluded(self):
        jobs = [
            make_job("Java Full Stack Developer"),
            make_job("Senior Java Developer"),
            make_job("Full Stack Java Engineer"),
            make_job("Python Full Stack Developer"),
        ]
        kept = filter_and_sort_jobs(jobs, posted_within_days=4, exclude_disallowed_work=False)
        self.assertEqual([job.title for job in kept], ["Python Full Stack Developer"])

    def test_javascript_title_is_not_treated_as_java(self):
        jobs = [make_job("JavaScript Full Stack Developer")]
        kept = filter_and_sort_jobs(jobs, posted_within_days=4, exclude_disallowed_work=False)
        self.assertEqual([job.title for job in kept], ["JavaScript Full Stack Developer"])


if __name__ == "__main__":
    unittest.main()
