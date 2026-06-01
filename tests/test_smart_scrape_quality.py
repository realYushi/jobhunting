import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from lib import smart_scrape
from lib.scraper import JobListing


class SmartScrapeQualityTests(unittest.TestCase):
    def test_keywords_for_source_uses_allowlist(self):
        keywords = smart_scrape._keywords_for_source(
            "seek",
            ["Software Engineer", "Product Engineer", "Application Developer"],
        )
        self.assertEqual(keywords, ["Software Engineer"])

    def test_keywords_for_source_falls_back_to_allowlist_when_empty(self):
        keywords = smart_scrape._keywords_for_source("seek", ["Product Engineer"])
        self.assertIn("Software Engineer", keywords)
        self.assertNotIn("Product Engineer", keywords)

    def test_title_looks_software_filters_non_software_engineering(self):
        self.assertTrue(smart_scrape._title_looks_software("Backend Engineer"))
        self.assertTrue(smart_scrape._title_looks_software("LLM Engineer"))
        self.assertFalse(smart_scrape._title_looks_software("Site Engineer"))
        self.assertFalse(smart_scrape._title_looks_software("Avionics Engineer I - Design"))

    def test_seek_urls_use_software_subclassifications_only(self):
        urls = smart_scrape._seek_base_urls(["Software Engineer"])
        self.assertTrue(all("classification=6281" in url for url in urls))
        self.assertTrue(all("subclassification=6287%2C6290" in url for url in urls))
        self.assertTrue(all("1209" not in url for url in urls))
        self.assertTrue(all("6302" not in url for url in urls))

    def test_linkedin_results_are_filtered_to_software_titles(self):
        original = smart_scrape._scrape_paginated
        try:
            smart_scrape._scrape_paginated = lambda *args, **kwargs: [
                JobListing(
                    job_id="1",
                    source="linkedin",
                    url="https://example.com/1",
                    title="Backend Engineer",
                    company="Acme",
                    snippet="",
                ),
                JobListing(
                    job_id="2",
                    source="linkedin",
                    url="https://example.com/2",
                    title="Site Engineer",
                    company="BuildCo",
                    snippet="",
                ),
            ]
            listings = smart_scrape._scrape_source(
                "linkedin", 50, 31, keywords=["Software Engineer"]
            )
        finally:
            smart_scrape._scrape_paginated = original

        self.assertEqual([lst.title for lst in listings], ["Backend Engineer"])


if __name__ == "__main__":
    unittest.main()
