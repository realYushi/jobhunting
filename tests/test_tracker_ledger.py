import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from tools.lib.tracker import (
    load_last_scrape,
    load_tracker,
    mark_skipped_key,
    save_last_scrape,
    save_tracker,
)
from tools.lib.identity import BoardKey


class WatermarkTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.tracker_path = self.root / "application-tracker.json"
        self.ledger_path = self.root / "application-ledger.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_watermark_round_trips_to_sidecar(self):
        """last_scrape is written to the sidecar and read back correctly."""
        watermark = {"linkedin": "2026-06-01", "seek": "2026-06-01"}
        save_last_scrape(self.tracker_path, watermark)

        ledger = json.loads(self.ledger_path.read_text())
        self.assertEqual(ledger["last_scrape"], watermark)

        reloaded = load_last_scrape(self.tracker_path)
        self.assertEqual(reloaded, watermark)

    def test_missing_sidecar_returns_empty_dict(self):
        """load_last_scrape returns {} when no sidecar exists."""
        self.assertFalse(self.ledger_path.exists())
        self.assertEqual(load_last_scrape(self.tracker_path), {})

    def test_sidecar_keys_are_sorted(self):
        """Keys in the sidecar are sorted so output is deterministic."""
        watermark = {"seek": "2026-06-01", "linkedin": "2026-06-01"}
        save_last_scrape(self.tracker_path, watermark)
        ledger = json.loads(self.ledger_path.read_text())
        self.assertEqual(list(ledger["last_scrape"].keys()), ["linkedin", "seek"])

    def test_noop_write_guard_for_watermark(self):
        """save_last_scrape skips the write when content is byte-identical."""
        watermark = {"linkedin": "2026-06-01"}
        save_last_scrape(self.tracker_path, watermark)
        mtime_before = self.ledger_path.stat().st_mtime

        save_last_scrape(self.tracker_path, watermark)
        self.assertEqual(self.ledger_path.stat().st_mtime, mtime_before)

    def test_ledger_only_write_does_not_bump_tracker_last_updated(self):
        """Writing the watermark sidecar must not change tracker.json's last_updated."""
        tracker = load_tracker(self.tracker_path)
        save_tracker(self.tracker_path, tracker)
        first_text = self.tracker_path.read_text()

        # Writing the watermark sidecar should not touch tracker.json.
        save_last_scrape(self.tracker_path, {"seek": "2026-06-01"})
        self.assertEqual(self.tracker_path.read_text(), first_text)

    def test_skipped_stays_in_tracker_not_sidecar(self):
        """skipped keys remain in tracker.json; the sidecar holds last_scrape only."""
        tracker = load_tracker(self.tracker_path)
        mark_skipped_key(tracker, BoardKey("seek", "222"))
        save_tracker(self.tracker_path, tracker)

        main = json.loads(self.tracker_path.read_text())
        self.assertEqual(len(main["skipped"]), 1)
        # Sidecar should not exist (we didn't save a watermark).
        self.assertFalse(self.ledger_path.exists())

    def test_legacy_seen_stripped_on_load(self):
        """Pre-v8 inline 'seen' lists are stripped from the tracker on load."""
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
        self.assertNotIn("seen", tracker)

    def test_legacy_sidecar_with_seen_key_returns_empty_watermark(self):
        """An old v7 sidecar {\"seen\": [...]} has no last_scrape → returns {}."""
        self.ledger_path.write_text(
            json.dumps({"seen": [{"kind": "board", "source": "linkedin", "job_id": "1"}]})
        )
        self.assertEqual(load_last_scrape(self.tracker_path), {})


if __name__ == "__main__":
    unittest.main()
