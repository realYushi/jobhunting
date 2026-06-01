import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from lib import smart_scrape
from lib.smart_scrape import within_days


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

    def test_linkedin_urls_carry_window_tpr(self):
        """f_TPR=r{window*86400} appears in all LinkedIn URLs for the given window."""
        urls = smart_scrape._linkedin_base_urls(["Software Engineer", "AI Engineer"], window_days=7)
        self.assertEqual(len(urls), 4)
        tpr = f"f_TPR=r{7 * 86400}"
        self.assertTrue(all(tpr in u for u in urls), f"Expected {tpr!r} in all URLs")

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

    def test_seek_urls_pick_correct_daterange_bucket(self):
        """daterange is the smallest Seek bucket >= window_days."""
        # window=5 → bucket 7
        urls_5 = smart_scrape._seek_base_urls(["Software Engineer"], window_days=5)
        self.assertTrue(all("daterange=7" in u for u in urls_5 if "daterange=" in u))
        # window=8 → bucket 14
        urls_8 = smart_scrape._seek_base_urls(["Software Engineer"], window_days=8)
        self.assertTrue(all("daterange=14" in u for u in urls_8 if "daterange=" in u))
        # window=31 → bucket 31
        urls_31 = smart_scrape._seek_base_urls(["Software Engineer"], window_days=31)
        self.assertTrue(all("daterange=31" in u for u in urls_31 if "daterange=" in u))

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


class WithinDaysTests(unittest.TestCase):
    """Boundary tests for the within_days() recency helper."""

    def test_null_returns_true(self):
        self.assertTrue(within_days(None, 7))

    def test_empty_string_returns_true(self):
        self.assertTrue(within_days("", 7))

    def test_garbage_returns_true(self):
        self.assertTrue(within_days("some random text", 7))

    def test_today_is_zero_days(self):
        self.assertTrue(within_days("today", 0))
        self.assertTrue(within_days("today", 7))

    def test_new_is_zero_days(self):
        self.assertTrue(within_days("new", 0))

    def test_yesterday_is_one_day(self):
        self.assertTrue(within_days("yesterday", 1))
        self.assertFalse(within_days("yesterday", 0))

    def test_nd_format(self):
        self.assertTrue(within_days("3d", 3))
        self.assertTrue(within_days("3d", 7))
        self.assertFalse(within_days("3d", 2))

    def test_n_days_ago(self):
        self.assertTrue(within_days("5 days ago", 5))
        self.assertTrue(within_days("5 days ago", 10))
        self.assertFalse(within_days("5 days ago", 4))
        # singular
        self.assertTrue(within_days("1 day ago", 1))

    def test_n_weeks_ago(self):
        self.assertTrue(within_days("2 weeks ago", 14))
        self.assertTrue(within_days("2 weeks ago", 20))
        self.assertFalse(within_days("2 weeks ago", 13))
        # singular
        self.assertTrue(within_days("1 week ago", 7))

    def test_n_months_ago(self):
        self.assertTrue(within_days("1 month ago", 30))
        self.assertTrue(within_days("1 month ago", 31))
        self.assertFalse(within_days("1 month ago", 29))

    def test_case_insensitive(self):
        self.assertTrue(within_days("Today", 0))
        self.assertTrue(within_days("YESTERDAY", 1))
        self.assertTrue(within_days("3 Days Ago", 3))

    def test_boundary_exact_match(self):
        """Listings exactly at the window boundary are kept."""
        self.assertTrue(within_days("7 days ago", 7))

    def test_boundary_one_over(self):
        """Listings one day beyond the window are dropped."""
        self.assertFalse(within_days("8 days ago", 7))


if __name__ == "__main__":
    unittest.main()
