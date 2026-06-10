import unittest

from lib import smart_scrape
from lib.inbox import _parse_apply_url


class ProspleSupportTests(unittest.TestCase):
    def test_parse_apply_url_supports_prosple(self):
        source, job_id = _parse_apply_url(
            "https://nz.prosple.com/graduate-employers/cognex-new-zealand/jobs-internships/junior-software-engineer-rust"
        )
        self.assertEqual(source, "prosple")
        self.assertEqual(job_id, "junior-software-engineer-rust")

    def test_prosple_base_urls_include_keyword(self):
        urls = smart_scrape._prosple_base_urls(["Software Engineer", "AI Engineer"])
        self.assertEqual(len(urls), 2)
        self.assertIn("keywords=Software+Engineer", urls[0])
        self.assertIn("keywords=AI+Engineer", urls[1])
        self.assertTrue(all("opportunity_types=1" in url for url in urls))

    def test_keywords_for_source_supports_prosple_allowlist(self):
        keywords = smart_scrape._keywords_for_source(
            "prosple",
            ["Software Engineer", "Product Engineer", "AI Engineer"],
        )
        self.assertEqual(keywords, ["Software Engineer", "AI Engineer"])


if __name__ == "__main__":
    unittest.main()
