"""Tests for smart_scrape watermark advance / keep-on-error behaviour."""

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from lib.scraper import JobListing
from lib.tracker import load_last_scrape


def _make_listing(job_id: str, source: str = "linkedin") -> JobListing:
    return JobListing(
        job_id=job_id,
        source=source,
        url=f"https://example.com/{job_id}",
        title="Software Engineer",
        company="Acme",
        snippet="",
    )


class WatermarkAdvanceTests(unittest.TestCase):
    """smart_scrape advances watermark for successful sources and keeps it on error."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.tracker_file = self.root / "application-tracker.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def _run_scrape(self, source_listings_map: dict, existing_watermark: dict | None = None):
        """Run smart_scrape with mocked _scrape_source and tracker path.

        ``source_listings_map`` maps source name → either a list[JobListing]
        (success) or an Exception (raises on scrape).
        """
        from lib import smart_scrape as ss

        if existing_watermark is not None:
            from lib.tracker import save_last_scrape
            save_last_scrape(self.tracker_file, existing_watermark)

        def fake_scrape_source(source, max_results, window, *, keywords=None):
            result = source_listings_map.get(source, [])
            if isinstance(result, Exception):
                raise result
            return result

        profiles = [{"sources": list(source_listings_map.keys()), "keywords": ["Software Engineer"]}]

        with patch.object(ss, "_scrape_source", side_effect=fake_scrape_source), \
             patch.object(ss, "tracker_path", return_value=self.tracker_file):
            listings, summary = ss.smart_scrape(profiles=profiles, max_total=100)

        return listings, summary

    def test_successful_source_advances_watermark(self):
        """A source that returns without error advances last_scrape to today."""
        listings, _ = self._run_scrape({"linkedin": [_make_listing("1")]})
        watermark = load_last_scrape(self.tracker_file)
        self.assertEqual(watermark.get("linkedin"), date.today().isoformat())

    def test_empty_result_does_not_advance_watermark(self):
        """A source that returns zero listings must NOT advance its watermark.

        Zero is unconfirmed: it can mean a login wall, a bot challenge, or an
        empty page — not "no new jobs". Advancing would mark the window covered
        and silently skip whatever the block hid, so the old watermark is kept.
        """
        old_date = "2026-05-01"
        self._run_scrape(
            {"wellfound": []},
            existing_watermark={"wellfound": old_date},
        )
        watermark = load_last_scrape(self.tracker_file)
        self.assertEqual(watermark.get("wellfound"), old_date)

    def test_first_run_empty_result_sets_no_watermark(self):
        """On first run, a zero result leaves no watermark so the next run still
        uses the initial lookback rather than a one-day window."""
        self._run_scrape({"wellfound": []})
        watermark = load_last_scrape(self.tracker_file)
        self.assertIsNone(watermark.get("wellfound"))

    def test_erroring_source_keeps_old_watermark(self):
        """A source that raises an exception must NOT update its watermark."""
        old_date = "2026-05-01"
        self._run_scrape(
            {"seek": RuntimeError("network error")},
            existing_watermark={"seek": old_date},
        )
        watermark = load_last_scrape(self.tracker_file)
        self.assertEqual(watermark.get("seek"), old_date)

    def test_partial_failure_preserves_successful_sources(self):
        """Successful sources advance even when another source errors."""
        old_date = "2026-05-01"
        self._run_scrape(
            {
                "linkedin": [_make_listing("1")],
                "seek": RuntimeError("timeout"),
            },
            existing_watermark={"seek": old_date},
        )
        watermark = load_last_scrape(self.tracker_file)
        self.assertEqual(watermark.get("linkedin"), date.today().isoformat())
        self.assertEqual(watermark.get("seek"), old_date)

    def test_first_run_no_watermark_uses_initial_lookback(self):
        """On first run, no watermark → window defaults to initial_lookback."""
        windows_used = []

        def capturing_scrape(source, max_results, window, *, keywords=None):
            windows_used.append((source, window))
            return []

        from lib import smart_scrape as ss
        profiles = [{"sources": ["linkedin"], "keywords": ["Software Engineer"]}]
        with patch.object(ss, "_scrape_source", side_effect=capturing_scrape), \
             patch.object(ss, "tracker_path", return_value=self.tracker_file):
            ss.smart_scrape(profiles=profiles)

        self.assertEqual(len(windows_used), 1)
        source, window = windows_used[0]
        self.assertEqual(source, "linkedin")
        # Default initial lookback is 31 (from search-config.json)
        self.assertGreaterEqual(window, 31)


if __name__ == "__main__":
    unittest.main()
