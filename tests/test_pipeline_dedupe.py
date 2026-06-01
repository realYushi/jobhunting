import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from lib.identity import ManualKey
from lib.inbox import InboxRow, format_row
from lib.reconcile import parse_inbox
from lib.scorer import ScoreResult
from lib.dedup import (
    _build_application_key_index,
    _build_company_title_index,
    _build_inbox_indexes,
    _duplicate_reason,
)


def score_result(**overrides):
    data = {
        "job_id": "12345",
        "source": "seek",
        "title": "Junior Developer",
        "company": "Acme",
        "url": "https://nz.seek.com/job/12345",
        "score": 90,
        "reason": "test",
    }
    data.update(overrides)
    return ScoreResult(**data)


class PipelineDedupeTests(unittest.TestCase):
    def test_detects_exact_tracker_duplicate_before_company_title(self):
        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Acme",
                        "position": "Junior Developer",
                        "status": "Submitted",
                        "source": "seek",
                        "job_id": "12345",
                    }
                ]
            }
        }

        reason = _duplicate_reason(
            score_result(),
            application_key_index=_build_application_key_index(tracker),
            company_title_index=_build_company_title_index(tracker),
            inbox_key_index={},
            inbox_company_title_index={},
            skipped_set=set(),
        )

        self.assertIn("existing tracker row", reason)
        self.assertIn("Submitted", reason)

    def test_detects_current_inbox_duplicate(self):
        inbox_path = "/tmp/test-pipeline-dedupe-inbox.md"
        with open(inbox_path, "w") as f:
            f.write(
                format_row(
                    InboxRow(
                        title="Junior Developer",
                        company="Acme",
                        slug="Acme-12345",
                        score=90,
                        url="https://nz.seek.com/job/12345",
                    )
                )
            )
        inbox_key_index, inbox_company_title_index = _build_inbox_indexes(
            parse_inbox(Path(inbox_path))
        )

        reason = _duplicate_reason(
            score_result(),
            application_key_index={},
            company_title_index={},
            inbox_key_index=inbox_key_index,
            inbox_company_title_index=inbox_company_title_index,
            skipped_set=set(),
        )

        self.assertIn("already in INBOX", reason)

    def test_empty_company_does_not_crash(self):
        # Regression: a malformed score row with empty company/title used to
        # crash _duplicate_reason via ManualKey's non-empty validation. It
        # should fall through to the board-key path and return None.
        reason = _duplicate_reason(
            score_result(company="", title=""),
            application_key_index={},
            company_title_index={},
            inbox_key_index={},
            inbox_company_title_index={},
            skipped_set=set(),
        )
        self.assertIsNone(reason)

    def test_detects_previously_skipped_manual_duplicate(self):
        reason = _duplicate_reason(
            score_result(job_id="99999"),
            application_key_index={},
            company_title_index={},
            inbox_key_index={},
            inbox_company_title_index={},
            skipped_set={ManualKey("Acme", "Junior Developer")},
        )

        self.assertEqual(reason, "previously skipped by company/title")

    def test_whitespace_company_does_not_crash(self):
        # Regression: whitespace-only company is truthy, so the "not company"
        # guard in _score_manual_key didn't fire and ManualKey's normalize-then-
        # raise validation killed the whole batch. Now treated like empty.
        reason = _duplicate_reason(
            score_result(company="   ", title="   "),
            application_key_index={},
            company_title_index={},
            inbox_key_index={},
            inbox_company_title_index={},
            skipped_set=set(),
        )
        self.assertIsNone(reason)

    def test_unknown_placeholder_does_not_collide(self):
        # Regression: run_from_scores defaults missing fields to "Unknown",
        # which would have made every malformed row collide under a single
        # ManualKey("unknown", "unknown") and false-positive each other.
        skipped = {ManualKey("Unknown", "Unknown")}
        reason = _duplicate_reason(
            score_result(company="Unknown", title="Unknown", job_id="42"),
            application_key_index={},
            company_title_index={},
            inbox_key_index={},
            inbox_company_title_index={},
            skipped_set=skipped,
        )
        # Board key still applies if present, but the manual sentinel must not
        # match the "Unknown" placeholder in the skipped set.
        self.assertIsNone(reason)

    def test_active_bucket_wins_over_archived_for_same_key(self):
        # Regression: setdefault across non-deterministic dict iteration could
        # report a stale archived status. _build_application_key_index now
        # walks buckets in priority order with active first.
        tracker = {
            "applications": {
                # Order chosen to expose the bug: rejected is first in dict
                # insertion order, but active should still win.
                "rejected": [
                    {
                        "company": "Acme",
                        "position": "Junior Developer",
                        "status": "Rejected",
                        "source": "seek",
                        "job_id": "12345",
                    }
                ],
                "active": [
                    {
                        "company": "Acme",
                        "position": "Junior Developer",
                        "status": "In Progress",
                        "source": "seek",
                        "job_id": "12345",
                    }
                ],
            }
        }
        reason = _duplicate_reason(
            score_result(),
            application_key_index=_build_application_key_index(tracker),
            company_title_index=_build_company_title_index(tracker),
            inbox_key_index={},
            inbox_company_title_index={},
            skipped_set=set(),
        )
        self.assertIn("In Progress", reason)

    def test_unknown_placeholder_does_not_collide_via_company_title_index(self):
        # Regression: sentinel filter applied only to manual_key earlier let
        # "Unknown" score rows still false-match against any tracker app with
        # the same placeholder via _existing_company_title_matches.
        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Unknown",
                        "position": "Unknown",
                        "status": "In Progress",
                        "source": "seek",
                        "job_id": "777",
                    }
                ]
            }
        }
        reason = _duplicate_reason(
            score_result(company="Unknown", title="Unknown", job_id="42"),
            application_key_index=_build_application_key_index(tracker),
            company_title_index=_build_company_title_index(tracker),
            inbox_key_index={},
            inbox_company_title_index={},
            skipped_set=set(),
        )
        self.assertIsNone(reason)

    def test_unknown_placeholder_does_not_collide_via_inbox_index(self):
        # Regression: same sentinel hole on the INBOX-side company/title path.
        inbox_path = "/tmp/test-pipeline-dedupe-inbox-unknown.md"
        with open(inbox_path, "w") as f:
            f.write(
                format_row(
                    InboxRow(
                        title="Unknown",
                        company="Unknown",
                        slug="Unknown-1",
                        score=50,
                        url="https://example.com/1",
                    )
                )
            )
        inbox_key_index, inbox_company_title_index = _build_inbox_indexes(
            parse_inbox(Path(inbox_path))
        )
        reason = _duplicate_reason(
            score_result(company="Unknown", title="Unknown", job_id="42"),
            application_key_index={},
            company_title_index={},
            inbox_key_index=inbox_key_index,
            inbox_company_title_index=inbox_company_title_index,
            skipped_set=set(),
        )
        self.assertIsNone(reason)

    def test_whitespace_board_job_id_does_not_collapse(self):
        # Regression: _score_board_key tested truthiness before BoardKey's
        # stripping, so "   " yielded BoardKey('seek', '') and let distinct
        # malformed rows alias each other.
        from lib.dedup import _score_board_key

        self.assertIsNone(_score_board_key(score_result(job_id="   ")))
        self.assertIsNone(_score_board_key(score_result(source="   ", job_id="9")))


if __name__ == "__main__":
    unittest.main()
