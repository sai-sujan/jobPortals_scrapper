import unittest

from job_checker.config import ROOT
from job_checker.resume import extract_docx_text, extract_resume_terms


class ResumeTest(unittest.TestCase):
    def test_resume_terms(self):
        resume_path = ROOT / "resume.docx"
        if not resume_path.exists():
            self.skipTest("local resume document is not committed")
        text = extract_docx_text(resume_path)
        terms = extract_resume_terms(text)
        self.assertIn("python", terms)
        self.assertIn("django", terms)
        self.assertIn("fastapi", terms)
        self.assertIn("langchain", terms)


if __name__ == "__main__":
    unittest.main()
