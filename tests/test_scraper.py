import unittest

from job_checker.models import Job
from job_checker.scraper import (
    akkodis_job_url,
    akkodis_jobs,
    akkodis_search_payload,
    extract_contact_info,
    filter_c2c_contract_jobs,
    filter_generic_non_job_pages,
    filter_usa_jobs,
    search_terms_for_template,
)


class ScraperLocationTest(unittest.TestCase):
    def test_usa_filter_keeps_us_jobs(self):
        jobs = [
            Job(
                source_company="Test",
                title="Python Developer",
                job_url="https://example.com/us",
                canonical_url="https://example.com/us",
                location="New York, NY, United States",
            )
        ]
        self.assertEqual(len(filter_usa_jobs(jobs, True)), 1)

    def test_usa_filter_removes_explicit_non_us_jobs(self):
        jobs = [
            Job(
                source_company="Test",
                title="Python Developer",
                job_url="https://example.com/ca",
                canonical_url="https://example.com/ca",
                location="Toronto, Canada",
            ),
            Job(
                source_company="Test",
                title="Data Engineer",
                job_url="https://example.com/in",
                canonical_url="https://example.com/in",
                description_snippet="Bengaluru, India hybrid role.",
            ),
        ]
        self.assertEqual(filter_usa_jobs(jobs, True), [])

    def test_search_terms_get_usa_suffix(self):
        terms = search_terms_for_template("https://example.com/jobs?q={query}", {"usa_only": True, "search_terms": ["python"]})
        self.assertEqual(terms, ["python United States"])

    def test_c2c_filter_keeps_explicit_c2c(self):
        jobs = [
            Job(
                source_company="Test",
                title="Python Developer",
                job_url="https://example.com/c2c",
                canonical_url="https://example.com/c2c",
                description_snippet="Contract role. C2C candidates accepted.",
            )
        ]
        self.assertEqual(len(filter_c2c_contract_jobs(jobs, True)), 1)
        self.assertEqual(jobs[0].employment_type, "C2C Contract")

    def test_c2c_compatible_mode_keeps_contract_for_review(self):
        jobs = [
            Job(
                source_company="Test",
                title="Python Developer",
                job_url="https://example.com/contract",
                canonical_url="https://example.com/contract",
                description_snippet="Six month contract role with a staffing vendor.",
            )
        ]
        self.assertEqual(filter_c2c_contract_jobs(jobs, True), [])
        kept = filter_c2c_contract_jobs(jobs, True, "compatible_review")
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].employment_type, "C2C Review - Contract")

    def test_c2c_filter_removes_w2_full_time_and_c2h(self):
        jobs = [
            Job(
                source_company="Test",
                title="Python Developer",
                job_url="https://example.com/w2",
                canonical_url="https://example.com/w2",
                description_snippet="W2 only contract role.",
            ),
            Job(
                source_company="Test",
                title="Python Developer",
                job_url="https://example.com/ft",
                canonical_url="https://example.com/ft",
                employment_type="FULL_TIME",
            ),
            Job(
                source_company="Test",
                title="Python Developer",
                job_url="https://example.com/c2h",
                canonical_url="https://example.com/c2h",
                description_snippet="Contract-to-hire role. No C2C.",
            ),
        ]
        self.assertEqual(filter_c2c_contract_jobs(jobs, True), [])

    def test_extract_contact_info(self):
        text = "Contact Jane at Jane.Recruiter@Example.com or 212-555-0199. Backup: jane.recruiter@example.com."
        self.assertEqual(extract_contact_info(text), "jane.recruiter@example.com, (212) 555-0199")

    def test_generic_career_pages_are_removed(self):
        jobs = [
            Job(
                source_company="Test",
                title="Welcome to careers at Example US",
                job_url="https://example.com/careers",
                canonical_url="https://example.com/careers",
            ),
            Job(
                source_company="Test",
                title="Senior Software Engineer, AI Automations",
                job_url="https://example.com/job",
                canonical_url="https://example.com/job",
            ),
        ]
        kept = filter_generic_non_job_pages(jobs)
        self.assertEqual([job.title for job in kept], ["Senior Software Engineer, AI Automations"])

    def test_akkodis_search_payload_uses_site_query_format(self):
        payload = akkodis_search_payload("python developer")
        self.assertEqual(payload["queryString"], "&q=python developer")
        self.assertEqual(payload["brand"], "modis")
        self.assertEqual(payload["countryCookie"], "US")

    def test_akkodis_job_url_matches_public_detail_shape(self):
        url = akkodis_job_url(
            {
                "jobTitle": "Python Developer",
                "jobLocation": "Jersey city, New Jersey",
                "jobId": "US_EN_6_916329_1574283",
            }
        )
        self.assertEqual(url, "https://www.akkodis.com/en-us/careers/job/python-developer-jersey-city/us_en_6_916329_1574283")

    def test_akkodis_jobs_fetches_search_and_detail(self):
        calls = []

        def fake_fetch_json(url, timeout, payload=None, headers=None):
            calls.append((url, payload))
            if url.endswith("/api/data/jobs/summarized"):
                return {
                    "jobs": [
                        {
                            "jobTitle": "Python Developer",
                            "jobId": "US_EN_6_916329_1574283",
                            "jobLocation": "Jersey city, New Jersey",
                            "contractTypeTitle": "Contractor",
                            "postedDate": "2026-04-09T20:03:31Z",
                            "isRemote": True,
                        }
                    ]
                }
            return {
                "jobName": "Python Developer",
                "location": "Jersey city, New Jersey",
                "contract": "Contractor",
                "jobDescription": "<p>Contract role using Python and Django. Contact test@example.com</p>",
            }

        import job_checker.scraper as scraper

        original_fetch_json = scraper.fetch_json
        try:
            scraper.fetch_json = fake_fetch_json
            jobs = akkodis_jobs(
                {"name": "Akkodis"},
                {
                    "search_terms": ["python developer"],
                    "request_timeout_seconds": 1,
                    "sleep_between_requests_seconds": 0,
                    "max_detail_pages_per_site": 1,
                },
            )
        finally:
            scraper.fetch_json = original_fetch_json

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].title, "Python Developer")
        self.assertEqual(jobs[0].employment_type, "Contract")
        self.assertEqual(jobs[0].remote_status, "Remote")
        self.assertEqual(jobs[0].contact_info, "test@example.com")
        self.assertEqual(calls[0][1]["queryString"], "&q=python developer")


if __name__ == "__main__":
    unittest.main()
