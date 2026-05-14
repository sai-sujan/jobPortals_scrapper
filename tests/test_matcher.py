import unittest

from job_checker.config import ROOT, load_config
from job_checker.matcher import ResumeMatcher
from job_checker.models import Job


class MatcherTest(unittest.TestCase):
    def setUp(self):
        self.matcher = ResumeMatcher(load_config(ROOT)["profile"])

    def score(self, title, text, employment_type="Contract"):
        job = Job(
            source_company="Test",
            title=title,
            job_url="https://example.com/job",
            canonical_url="https://example.com/job",
            employment_type=employment_type,
            description_snippet=text,
            raw_text=text,
        )
        return self.matcher.score(job)

    def test_best_python_ai_contract_match(self):
        job = self.score(
            "Senior Python Gen AI Developer",
            "Contract role using Django REST Framework, FastAPI, LangChain, RAG, OpenAI API, AWS Lambda, Docker.",
        )
        self.assertEqual(job.status, "match")
        self.assertEqual(job.match_bucket, "best")
        self.assertIn("python", [term.lower() for term in job.matched_terms])

    def test_borderline_match(self):
        job = self.score("Python Developer", "Contract backend APIs with AWS.", "Contract")
        self.assertEqual(job.status, "match")
        self.assertIn(job.match_bucket, {"best", "borderline"})

    def test_excludes_recruiter(self):
        job = self.score("Technical Recruiter", "Recruiting Python developers for contract jobs.")
        self.assertEqual(job.status, "excluded")

    def test_non_python_java_only(self):
        job = self.score("Senior Java Developer", "Contract Java Spring Boot role.", "Contract")
        self.assertNotEqual(job.status, "match")


if __name__ == "__main__":
    unittest.main()
