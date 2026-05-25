import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from lib import smart_scrape


class SmartScrapeKeywordTests(unittest.TestCase):
    def test_unique_keywords_preserves_order(self):
        keywords = smart_scrape._unique_keywords(
            [
                {"keywords": ["Software Engineer", "Full Stack Engineer"]},
                {"keywords": ["software engineer", "AI Engineer"]},
            ]
        )
        self.assertEqual(
            keywords,
            ["Software Engineer", "Full Stack Engineer", "AI Engineer"],
        )

    def test_linkedin_urls_follow_keywords(self):
        urls = smart_scrape._linkedin_base_urls(["Software Engineer", "AI Engineer"])
        self.assertEqual(len(urls), 2)
        self.assertIn("keywords=Software%20Engineer", urls[0])
        self.assertIn("keywords=AI%20Engineer", urls[1])

    def test_seek_urls_expand_per_keyword(self):
        urls = smart_scrape._seek_base_urls(["Product Engineer"])
        self.assertEqual(len(urls), 3)
        self.assertTrue(all("Product-Engineer" in url for url in urls))

    def test_wellfound_urls_map_role_aliases(self):
        urls = smart_scrape._wellfound_base_urls(
            ["Frontend Developer", "AI Engineer", "Frontend Engineer"]
        )
        self.assertEqual(
            urls,
            [
                "https://wellfound.com/role/r/frontend-engineer",
                "https://wellfound.com/role/r/artificial-intelligence-engineer",
            ],
        )

    def test_weworkremotely_uses_search_term(self):
        url = smart_scrape._weworkremotely_search_url(
            ["Software Engineer", "Full Stack Developer"]
        )
        self.assertIn("term=Software%20Engineer%20Full%20Stack%20Developer", url)


if __name__ == "__main__":
    unittest.main()
