import unittest
from pathlib import Path

from lib.app_state import ApplicationState
from lib.dedup import DedupGate
from lib.identity import ManualKey
from lib.inbox import InboxRow, format_row
from lib.scorer import JobScore


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
    return JobScore(**data)


def make_gate(
    tracker: dict | None = None,
    inbox_path: Path | None = None,
    skipped: set | None = None,
) -> DedupGate:
    """Build a DedupGate from an in-memory tracker dict and optional INBOX file."""
    tracker = tracker if tracker is not None else {"applications": {}}
    if skipped:
        tracker["skipped"] = [k.to_dict() for k in skipped]
    state = ApplicationState(Path("/nonexistent-tracker.json"), tracker)
    return DedupGate(state, inbox_path or Path("/nonexistent-inbox.md"))


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

        reason = make_gate(tracker).reason(score_result())

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

        reason = make_gate(inbox_path=Path(inbox_path)).reason(score_result())

        self.assertIn("already in INBOX", reason)

    def test_empty_company_does_not_crash(self):
        # Regression: a malformed score row with empty company/title used to
        # crash the gate via ManualKey's non-empty validation. It should fall
        # through to the board-key path and return None.
        reason = make_gate().reason(score_result(company="", title=""))
        self.assertIsNone(reason)

    def test_detects_previously_skipped_manual_duplicate(self):
        gate = make_gate(skipped={ManualKey("Acme", "Junior Developer")})
        reason = gate.reason(score_result(job_id="99999"))

        self.assertEqual(reason, "previously skipped by company/title")

    def test_whitespace_company_does_not_crash(self):
        # Regression: whitespace-only company is truthy, so the "not company"
        # guard in _score_manual_key didn't fire and ManualKey's normalize-then-
        # raise validation killed the whole batch. Now treated like empty.
        reason = make_gate().reason(score_result(company="   ", title="   "))
        self.assertIsNone(reason)

    def test_unknown_placeholder_does_not_collide(self):
        # Regression: run_from_scores defaults missing fields to "Unknown",
        # which would have made every malformed row collide under a single
        # ManualKey("unknown", "unknown") and false-positive each other.
        gate = make_gate(skipped={ManualKey("Unknown", "Unknown")})
        reason = gate.reason(
            score_result(company="Unknown", title="Unknown", job_id="42")
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
        reason = make_gate(tracker).reason(score_result())
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
        reason = make_gate(tracker).reason(
            score_result(company="Unknown", title="Unknown", job_id="42")
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
        reason = make_gate(inbox_path=Path(inbox_path)).reason(
            score_result(company="Unknown", title="Unknown", job_id="42")
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
