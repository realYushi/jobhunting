import json
import tempfile
import unittest
from pathlib import Path

from tools.lib.tracker import (
    BoardKey,
    is_seen_key,
    load_tracker,
    mark_seen_key,
    mark_skipped_key,
    save_tracker,
)


class TrackerLedgerSplitTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.tracker_path = self.root / "application-tracker.json"
        self.ledger_path = self.root / "application-ledger.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_seen_goes_to_ledger_not_tracker_json(self):
        tracker = load_tracker(self.tracker_path)
        mark_seen_key(tracker, BoardKey("linkedin", "111"))
        mark_skipped_key(tracker, BoardKey("seek", "222"))
        save_tracker(self.tracker_path, tracker)

        main = json.loads(self.tracker_path.read_text())
        self.assertNotIn("seen", main)
        # skipped stays in the tracker file (human decisions, kept in git)
        self.assertEqual(len(main["skipped"]), 1)

        ledger = json.loads(self.ledger_path.read_text())
        self.assertEqual(ledger["seen"], [{"kind": "board", "source": "linkedin", "job_id": "111"}])

    def test_seen_round_trips_through_ledger(self):
        tracker = load_tracker(self.tracker_path)
        mark_seen_key(tracker, BoardKey("linkedin", "111"))
        save_tracker(self.tracker_path, tracker)

        reloaded = load_tracker(self.tracker_path)
        self.assertTrue(is_seen_key(reloaded, BoardKey("linkedin", "111")))

    def test_inline_seen_migrates_to_ledger_on_next_save(self):
        # Pre-v7 file: seen still inline, no sidecar yet.
        self.tracker_path.write_text(
            json.dumps(
                {
                    "applications": {"active": []},
                    "seen": [{"kind": "board", "source": "linkedin", "job_id": "999"}],
                    "skipped": [],
                }
            )
        )
        tracker = load_tracker(self.tracker_path)
        self.assertTrue(is_seen_key(tracker, BoardKey("linkedin", "999")))

        save_tracker(self.tracker_path, tracker)
        self.assertNotIn("seen", json.loads(self.tracker_path.read_text()))
        self.assertEqual(
            json.loads(self.ledger_path.read_text())["seen"],
            [{"kind": "board", "source": "linkedin", "job_id": "999"}],
        )

    def test_serialized_seen_order_is_deterministic(self):
        tracker = load_tracker(self.tracker_path)
        for jid in ("333", "111", "222"):
            mark_seen_key(tracker, BoardKey("linkedin", jid))
        save_tracker(self.tracker_path, tracker)
        first = self.ledger_path.read_text()

        # Reload (set order differs) and re-save with no changes: byte-identical.
        reloaded = load_tracker(self.tracker_path)
        save_tracker(self.tracker_path, reloaded)
        self.assertEqual(first, self.ledger_path.read_text())


if __name__ == "__main__":
    unittest.main()
