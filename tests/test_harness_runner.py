"""Tests for the HarnessRunner seam: pagination, watermark, and jd_fetch."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from lib.harness_utils import HarnessResult, LiveHarnessRunner
from lib.scraper import JobListing
from lib.tracker import load_last_scrape, save_last_scrape


# ---------------------------------------------------------------------------
# Fake runner
# ---------------------------------------------------------------------------

def _jobs_page(jobs: list[dict]) -> str:
    """Encode a list of job dicts as a harness JSON-lines stdout string."""
    return json.dumps({"jobs": jobs}) + "\n"


def _empty_page() -> str:
    return json.dumps({"jobs": []}) + "\n"


def _make_job(job_id: str, posted: str | None = "today") -> dict:
    return {
        "job_id": job_id,
        "url": f"https://example.com/job/{job_id}",
        "title": "Software Engineer",
        "company": "Acme",
        "snippet": "",
        "posted": posted,
    }


class CannedRunner:
    """Fake harness runner backed by a call-sequence dict.

    ``pages`` maps (script_name, page) → stdout string. Unknown calls return
    an empty-page result so tests don't have to enumerate every possible call.
    """

    def __init__(self, pages: dict[tuple, str]) -> None:
        self._pages = pages
        self.calls: list[dict] = []

    def run(
        self,
        script_name: str,
        *,
        timeout: int,
        source: str | None = None,
        **params,
    ) -> HarnessResult:
        page = params.get("page", 1)
        self.calls.append({"script": script_name, "page": page, "params": params})
        stdout = self._pages.get((script_name, page), _empty_page())
        return HarnessResult(stdout=stdout, stderr="", retcode=0)


class FailingRunner:
    """Fake runner that always returns retcode != 0."""

    def run(self, script_name: str, *, timeout: int, source: str | None = None, **params) -> HarnessResult:
        return HarnessResult(stdout="", stderr="timeout", retcode=1)


# ---------------------------------------------------------------------------
# Pagination tests
# ---------------------------------------------------------------------------

class PaginationTests(unittest.TestCase):
    """_scrape_paginated aggregates across pages and stops on empty page."""

    def _run_paginated(self, pages: dict, max_results: int = 50, max_pages: int = 3) -> list[JobListing]:
        from lib.smart_scrape import _scrape_paginated

        runner = CannedRunner(pages)
        return _scrape_paginated(
            "seek",
            ("https://example.com",),
            "seek-list",
            lambda base, page: base,
            max_results,
            window=7,
            max_pages=max_pages,
            runner=runner,
        )

    def test_two_pages_then_empty_aggregates_and_stops(self):
        """Listings from pages 1 and 2 are returned; page 3 (empty) stops iteration."""
        pages = {
            ("seek-list", 1): _jobs_page([_make_job("a"), _make_job("b")]),
            ("seek-list", 2): _jobs_page([_make_job("c")]),
            # page 3 not provided → defaults to empty
        }
        listings = self._run_paginated(pages)
        self.assertEqual([lst.job_id for lst in listings], ["a", "b", "c"])

    def test_stops_on_non_zero_retcode(self):
        """A non-zero retcode from the runner stops pagination immediately."""
        from lib.smart_scrape import _scrape_paginated

        fail_runner = FailingRunner()
        listings = _scrape_paginated(
            "seek",
            ("https://example.com",),
            "seek-list",
            lambda base, page: base,
            50,
            window=7,
            max_pages=3,
            runner=fail_runner,
        )
        self.assertEqual(listings, [])

    def test_max_results_cap_respected(self):
        """max_results caps the returned list even if pages have more."""
        pages = {
            ("seek-list", 1): _jobs_page([_make_job(str(i)) for i in range(10)]),
            ("seek-list", 2): _jobs_page([_make_job(str(i)) for i in range(10, 20)]),
        }
        listings = self._run_paginated(pages, max_results=5)
        self.assertEqual(len(listings), 5)

    def test_within_run_dedup_across_pages(self):
        """Duplicate job_ids across pages are removed by dedup_within_run."""
        from lib.smart_scrape import dedup_within_run

        pages = {
            ("seek-list", 1): _jobs_page([_make_job("dup"), _make_job("unique")]),
            ("seek-list", 2): _jobs_page([_make_job("dup")]),
        }
        listings = self._run_paginated(pages)
        # Two listings from pages, but dedup_within_run is called by smart_scrape,
        # not _scrape_paginated itself. Verify via the full dedup helper.
        deduped = dedup_within_run(listings)
        self.assertEqual([lst.job_id for lst in deduped], ["dup", "unique"])


# ---------------------------------------------------------------------------
# Watermark + date-window filtering through the real flow
# ---------------------------------------------------------------------------

class WatermarkWindowTests(unittest.TestCase):
    """smart_scrape date-window filters listings through the real parsing path."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.tracker_file = self.root / "application-tracker.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def _run_scrape_seek(
        self,
        pages: dict,
        existing_watermark: dict | None = None,
    ) -> list[JobListing]:
        """Run smart_scrape with seek source using CannedRunner; returns listings."""
        from lib import smart_scrape as ss
        from unittest.mock import patch

        if existing_watermark is not None:
            save_last_scrape(self.tracker_file, existing_watermark)

        runner = CannedRunner(pages)

        profiles = [{"sources": ["seek"], "keywords": ["Software Engineer"]}]
        with patch.object(ss, "tracker_path", return_value=self.tracker_file):
            listings, _ = ss.smart_scrape(profiles=profiles, max_total=100, runner=runner)
        return listings

    def test_listings_within_window_are_returned(self):
        """Listings posted within the date window pass through."""
        pages = {
            ("seek-list", 1): _jobs_page([_make_job("j1", posted="today"), _make_job("j2", posted="2d")]),
        }
        listings = self._run_scrape_seek(pages)
        job_ids = [lst.job_id for lst in listings]
        self.assertIn("j1", job_ids)
        self.assertIn("j2", job_ids)

    def test_listings_older_than_window_are_filtered(self):
        """Listings older than the window are filtered by the recent_filter path.

        workingnomads uses a recent_filter; seek does not (Seek filters server-side
        via daterange param). We test via workingnomads to exercise the filter path.
        """
        from lib import smart_scrape as ss
        from unittest.mock import patch

        # workingnomads uses recent_filter=lambda p: within_days(p, window)
        # Window for first run (no watermark) is initial_lookback (31d).
        # A listing "60 days ago" should be filtered out.
        old_job = _make_job("old", posted="60 days ago")
        new_job = _make_job("new", posted="today")
        pages = {
            ("workingnomads-list", 1): _jobs_page([old_job, new_job]),
        }
        runner = CannedRunner(pages)
        profiles = [{"sources": ["workingnomads"], "keywords": ["Software Engineer"]}]
        with patch.object(ss, "tracker_path", return_value=self.tracker_file):
            listings, _ = ss.smart_scrape(profiles=profiles, max_total=100, runner=runner)
        job_ids = [lst.job_id for lst in listings]
        self.assertIn("new", job_ids)
        self.assertNotIn("old", job_ids)

    def test_watermark_advances_after_successful_scrape(self):
        """smart_scrape advances the watermark when the fake runner returns listings."""
        pages = {
            ("seek-list", 1): _jobs_page([_make_job("j1")]),
        }
        self._run_scrape_seek(pages)
        watermark = load_last_scrape(self.tracker_file)
        self.assertEqual(watermark.get("seek"), date.today().isoformat())

    def test_watermark_unchanged_on_empty_result(self):
        """Zero listings from a source keeps the old watermark."""
        old = "2026-05-01"
        self._run_scrape_seek({}, existing_watermark={"seek": old})
        watermark = load_last_scrape(self.tracker_file)
        self.assertEqual(watermark.get("seek"), old)


# ---------------------------------------------------------------------------
# jd_fetch tests
# ---------------------------------------------------------------------------

class JdFetchRunnerTests(unittest.TestCase):
    """_fetch_full_jd returns JD text from canned runner; error paths pinned."""

    def _make_jd_runner(self, jd_text: str) -> CannedRunner:
        """Runner that returns a canned JD for any jd-fetch call."""
        # jd-fetch does not paginate; we key by ("jd-fetch", 1) but the runner
        # uses page param which defaults to whatever is passed (none for jd-fetch).
        # Use a catch-all by returning the same stdout for any call.
        class JdCannedRunner:
            def run(self, script_name: str, *, timeout: int, source: str | None = None, **params) -> HarnessResult:
                payload = json.dumps({"jd": jd_text}) + "\n"
                return HarnessResult(stdout=payload, stderr="", retcode=0)

        return JdCannedRunner()

    def test_returns_jd_text_from_runner(self):
        """_fetch_full_jd extracts 'jd' from the first parsed JSON object."""
        from lib.jd_fetch import _fetch_full_jd

        runner = self._make_jd_runner("This is the job description.")
        result = _fetch_full_jd("https://example.com/job/1", runner=runner)
        self.assertEqual(result, "This is the job description.")

    def test_non_zero_retcode_returns_error_string(self):
        """retcode != 0 → returns error string containing the URL."""
        from lib.jd_fetch import _fetch_full_jd

        runner = FailingRunner()
        result = _fetch_full_jd("https://example.com/job/bad", runner=runner)
        self.assertIn("https://example.com/job/bad", result)
        self.assertIn("Failed to fetch JD", result)
        # stderr from the runner is propagated
        self.assertIn("timeout", result)

    def test_empty_output_returns_could_not_extract(self):
        """When stdout has no 'jd' key, a 'Could not extract' message is returned."""
        from lib.jd_fetch import _fetch_full_jd

        class NoJdRunner:
            def run(self, script_name: str, *, timeout: int, source: str | None = None, **params) -> HarnessResult:
                return HarnessResult(stdout=json.dumps({"other": "data"}) + "\n", stderr="", retcode=0)

        result = _fetch_full_jd("https://example.com/job/nojd", runner=NoJdRunner())
        self.assertIn("Could not extract JD", result)

    def test_fetch_jds_parallel_threads_runner(self):
        """_fetch_jds_parallel passes the runner through to each _fetch_full_jd call."""
        from lib.jd_fetch import _fetch_jds_parallel
        from lib.scorer import JobScore

        runner = self._make_jd_runner("Parallel JD text.")
        items = [
            JobScore(
                job_id="x1",
                source="seek",
                title="SWE",
                company="Acme",
                url="https://example.com/job/x1",
                score=80,
                reason="",
            )
        ]
        out = _fetch_jds_parallel(items, runner=runner)
        self.assertEqual(out["https://example.com/job/x1"], "Parallel JD text.")


# ---------------------------------------------------------------------------
# LiveHarnessRunner interface test (unit — doesn't actually run browser)
# ---------------------------------------------------------------------------

class LiveHarnessRunnerInterfaceTests(unittest.TestCase):
    """LiveHarnessRunner.run() delegates to load_script + run_harness."""

    def test_run_returns_harness_result(self):
        """run() wraps (stdout, stderr, retcode) in a HarnessResult."""
        from lib import harness_utils

        runner = LiveHarnessRunner()
        with unittest.mock.patch.object(
            harness_utils, "run_harness", return_value=("out", "err", 0)
        ) as mock_rh, unittest.mock.patch.object(
            harness_utils, "load_script", return_value="script_body"
        ) as mock_ls:
            result = runner.run("seek-list", url="https://x.com", page=1, timeout=60)

        mock_ls.assert_called_once_with("seek-list", url="https://x.com", page=1)
        mock_rh.assert_called_once_with("script_body", timeout=60, source=None)
        self.assertIsInstance(result, HarnessResult)
        self.assertEqual(result.stdout, "out")
        self.assertEqual(result.stderr, "err")
        self.assertEqual(result.retcode, 0)

    def test_run_passes_source(self):
        """source= keyword is forwarded to run_harness."""
        from lib import harness_utils

        runner = LiveHarnessRunner()
        with unittest.mock.patch.object(
            harness_utils, "run_harness", return_value=("", "", 0)
        ) as mock_rh, unittest.mock.patch.object(
            harness_utils, "load_script", return_value=""
        ):
            runner.run("prosple-list", url="https://p.com", page=1, timeout=120, source="prosple")

        _args, kwargs = mock_rh.call_args
        self.assertEqual(kwargs.get("source"), "prosple")


import unittest.mock  # noqa: E402 (needed for the last test class)


if __name__ == "__main__":
    unittest.main()
