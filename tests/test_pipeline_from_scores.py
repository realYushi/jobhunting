import json
import sys
import tempfile
import unittest
from pathlib import Path

import pipeline
from lib.scorer import JobScore


class RunFromScoresJoinTests(unittest.TestCase):
    """run_from_scores must reuse the JDs fetched upstream rather than refetch.

    The redesign moved JD fetching into --scrape-only, so packaging joins the
    scores file to the listings dump by job_id. These tests pin that join (and
    the title/company/url backfill) without exercising real packaging.
    """

    def setUp(self):
        self.captured = {}

        def fake_package(
            root, passed, cap, dry_run, listings_by_id=None, skip_reconcile=False
        ):
            self.captured = {
                "passed": passed,
                "cap": cap,
                "listings_by_id": listings_by_id or {},
                "skip_reconcile": skip_reconcile,
            }

        self._orig = pipeline.do_package_from_scores
        pipeline.do_package_from_scores = fake_package

    def tearDown(self):
        pipeline.do_package_from_scores = self._orig

    @staticmethod
    def _write(tmp: Path, name: str, payload: dict) -> Path:
        path = tmp / name
        path.write_text(json.dumps(payload))
        return path

    def test_joins_full_jd_and_backfills_missing_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            listings = self._write(
                tmp,
                "listings.json",
                {
                    "cutoff": 65,
                    "cap": 100,
                    "listings": [
                        {
                            "job_id": "1",
                            "source": "seek",
                            "title": "Backend Engineer",
                            "company": "Acme",
                            "url": "https://x/1",
                            "full_jd": "FULL JD ONE",
                        }
                    ],
                },
            )
            # Score row omits title/company/url — they must be backfilled.
            scores = self._write(
                tmp,
                "scores.json",
                {"cap": 5, "scores": [{"job_id": "1", "source": "seek", "score": 88, "reason": "good"}]},
            )

            pipeline.run_from_scores(
                root=tmp,
                scores_file=scores,
                listings_file=listings,
                cap_override=None,
                dry_run=True,
                reconcile_inbox=False,
            )

        c = self.captured
        self.assertEqual(c["cap"], 5)  # cap from scores file
        self.assertTrue(c["skip_reconcile"])
        self.assertEqual(c["listings_by_id"]["1"]["full_jd"], "FULL JD ONE")
        self.assertEqual(len(c["passed"]), 1)
        sr = c["passed"][0]
        self.assertIsInstance(sr, JobScore)
        self.assertEqual(sr.title, "Backend Engineer")
        self.assertEqual(sr.company, "Acme")
        self.assertEqual(sr.url, "https://x/1")
        self.assertEqual(sr.score, 88)

    def test_cap_override_wins_and_listings_optional(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            scores = self._write(
                tmp,
                "scores.json",
                {
                    "scores": [
                        {
                            "job_id": "9",
                            "source": "seek",
                            "title": "Dev",
                            "company": "Beta",
                            "url": "https://x/9",
                            "score": 70,
                            "reason": "ok",
                        }
                    ]
                },
            )
            pipeline.run_from_scores(
                root=tmp,
                scores_file=scores,
                listings_file=None,
                cap_override=3,
                dry_run=True,
                reconcile_inbox=False,
            )

        c = self.captured
        self.assertEqual(c["cap"], 3)  # --cap overrides
        self.assertEqual(c["listings_by_id"], {})
        self.assertEqual(c["passed"][0].title, "Dev")


if __name__ == "__main__":
    unittest.main()
