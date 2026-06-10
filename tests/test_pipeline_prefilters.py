import sys
import unittest
from pathlib import Path

import pipeline
from lib.scraper import JobListing


class PipelinePrefilterTests(unittest.TestCase):
    def test_title_hard_drop_matches_senior_and_qa_noise(self):
        senior = JobListing(
            job_id="1",
            source="seek",
            url="https://example.com/1",
            title="Senior Quality Assurance Engineer",
            company="Acme",
            snippet="",
        )
        self.assertEqual(
            pipeline._title_hard_drop_reason(senior),
            "title hard-drop: senior",
        )

        qa = JobListing(
            job_id="2",
            source="seek",
            url="https://example.com/2",
            title="Quality Assurance Engineer",
            company="Acme",
            snippet="",
        )
        self.assertEqual(
            pipeline._title_hard_drop_reason(qa),
            "title hard-drop: quality assurance",
        )

    def test_title_hard_drop_keeps_relevant_product_engineering_titles(self):
        listing = JobListing(
            job_id="3",
            source="seek",
            url="https://example.com/3",
            title="Intermediate Full Stack Product Engineer",
            company="Acme",
            snippet="",
        )
        self.assertIsNone(pipeline._title_hard_drop_reason(listing))


if __name__ == "__main__":
    unittest.main()
