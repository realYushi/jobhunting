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
        # Each keyword expands to two location variants: an Auckland search and
        # an NZ-wide remote-only (f_WT=2) search. Both must carry the keyword.
        urls = smart_scrape._linkedin_base_urls(["Software Engineer", "AI Engineer"])
        self.assertEqual(len(urls), 4)
        self.assertTrue(all("keywords=Software%20Engineer" in u for u in urls[:2]))
        self.assertTrue(all("keywords=AI%20Engineer" in u for u in urls[2:]))
        # Per keyword, exactly one variant is the NZ-wide remote search.
        self.assertEqual(sum("f_WT=2" in u for u in urls), 2)
        self.assertEqual(sum("location=Auckland" in u for u in urls), 2)

    def test_seek_urls_expand_per_keyword(self):
        # Each keyword expands to four variants: Auckland full-time, Auckland
        # (any arrangement), AU remote, and NZ remote.
        urls = smart_scrape._seek_base_urls(["Product Engineer"])
        self.assertEqual(len(urls), 4)
        self.assertTrue(all("Product-Engineer" in url for url in urls))
        self.assertEqual(sum("/remote" in url for url in urls), 2)

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
