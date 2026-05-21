import tempfile
import unittest
from pathlib import Path

from tools.lib.reconcile import (
    parse_inbox,
    reconcile,
    slug_from_company,
)
from tools.lib.identity import BoardKey, ManualKey
from tools.lib.tracker import is_skipped_key, load_tracker, mark_skipped_key


class ParseInboxTests(unittest.TestCase):
    def test_parse_empty_inbox(self):
        items = parse_inbox(Path("/nonexistent"))
        self.assertEqual(items, [])

    def test_parse_submitted_item(self):
        inbox = Path("/tmp/test-inbox.md")
        inbox.write_text(
            "- [x] **Senior Python Engineer** @ Acme (score: 82) · [JD](./acme/job.md) · [CV](./acme/cv.pdf) · [Letter](./acme/cover.md) · [Apply ↗](https://acme.com/apply)"
        )
        items = parse_inbox(inbox)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "[x]")
        self.assertEqual(items[0].title, "Senior Python Engineer")
        self.assertEqual(items[0].company, "Acme")
        self.assertEqual(items[0].score, 82)
        self.assertEqual(items[0].slug, "Acme")

    def test_parse_skipped_item(self):
        inbox = Path("/tmp/test-inbox.md")
        inbox.write_text(
            "- [~] **Frontend Lead** @ Initech (score: 65) · [JD](./initech/job.md) · [CV](./initech/cv.pdf) · [Letter](./initech/cover.md) · [Apply ↗](https://initech.com/apply)"
        )
        items = parse_inbox(inbox)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "[~]")
        self.assertEqual(items[0].title, "Frontend Lead")
        self.assertEqual(items[0].company, "Initech")

    def test_parse_active_item(self):
        inbox = Path("/tmp/test-inbox.md")
        inbox.write_text(
            "- [ ] **Backend Dev** @ Globex (score: 78) · [JD](./globex/job.md) · [CV](./globex/cv.pdf) · [Letter](./globex/cover.md) · [Apply ↗](https://globex.com/apply)"
        )
        items = parse_inbox(inbox)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].status, "[ ]")
        self.assertEqual(items[0].company, "Globex")

    def test_parse_multiple_items(self):
        inbox = Path("/tmp/test-inbox.md")
        inbox.write_text(
            "- [ ] **Backend Dev** @ Globex (score: 78) · [JD](./globex/job.md) · [CV](./globex/cv.pdf) · [Letter](./globex/cover.md) · [Apply ↗](https://globex.com/apply)\n"
            "- [x] **Senior Python Engineer** @ Acme (score: 82) · [JD](./acme/job.md) · [CV](./acme/cv.pdf) · [Letter](./acme/cover.md) · [Apply ↗](https://acme.com/apply)\n"
            "- [~] **Frontend Lead** @ Initech (score: 65) · [JD](./initech/job.md) · [CV](./initech/cv.pdf) · [Letter](./initech/cover.md) · [Apply ↗](https://initech.com/apply)\n"
        )
        items = parse_inbox(inbox)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].status, "[ ]")
        self.assertEqual(items[1].status, "[x]")
        self.assertEqual(items[2].status, "[~]")

    def test_slug_no_jobid_uses_bare_company(self):
        """Rows without a parseable Apply URL job_id (manual flows) keep the
        bare company-name dir, matching workflow.create_application_package."""
        inbox = Path("/tmp/test-inbox.md")
        inbox.write_text(
            "- [x] **SWE** @ Contact Energy (score: 80) · [JD](./active/Contact%20Energy/research/job-description.md) · [CV](./active/Contact%20Energy/documents/resume.pdf) · [Letter](./active/Contact%20Energy/documents/cover-letter.md)\n"
        )
        items = parse_inbox(inbox)
        self.assertEqual(items[0].slug, "Contact Energy")
        self.assertIsNone(items[0].job_id)

    def test_slug_with_jobid_is_namespaced(self):
        """Rows with a recognised Apply URL gain a -{job_id} suffix so the
        dir matches what workflow.create_application_package writes."""
        inbox = Path("/tmp/test-inbox.md")
        inbox.write_text(
            "- [x] **SWE Agentic** @ Caruso Software Limited (score: 93) · [JD](./Caruso%20Software%20Limited-91491952/research/job-description.md) · [CV](./x/cv.pdf) · [Letter](./x/cover.md) · [Apply ↗](https://nz.seek.com/job/91491952?type=promoted)\n"
            "- [x] **SWE FP** @ Bellroy (score: 77) · [JD](./x/jd.md) · [CV](./x/cv.pdf) · [Letter](./x/cover.md) · [Apply ↗](https://hiring.cafe/viewjob/erdu1sl82w0643qb)\n"
        )
        items = parse_inbox(inbox)
        self.assertEqual(items[0].slug, "Caruso Software Limited-91491952")
        self.assertEqual(items[0].source, "seek")
        self.assertEqual(items[0].job_id, "91491952")
        self.assertEqual(items[1].slug, "Bellroy-erdu1sl8")
        self.assertEqual(items[1].source, "hiringcafe")
        self.assertEqual(items[1].job_id, "erdu1sl82w0643qb")


class SlugGenerationTests(unittest.TestCase):
    def test_slug_from_simple_company(self):
        slug = slug_from_company("Acme", [])
        self.assertEqual(slug, "acme")

    def test_slug_from_multi_word_company(self):
        slug = slug_from_company("Acme Corp", [])
        self.assertEqual(slug, "acme-corp")

    def test_slug_handles_special_chars(self):
        slug = slug_from_company("O'Reilly & Associates", [])
        self.assertEqual(slug, "oreilly-associates")

    def test_slug_deduplicates_with_number(self):
        slug1 = slug_from_company("Acme", [])
        slug2 = slug_from_company("Acme", [slug1])
        self.assertEqual(slug2, "acme-2")


class SkippedJobsTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.tracker_path = self.root / "tracker.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_mark_and_check_skipped_by_id(self):
        tracker = load_tracker(self.tracker_path)
        mark_skipped_key(tracker, BoardKey("linkedin", "12345"))

        self.assertTrue(is_skipped_key(tracker, BoardKey("linkedin", "12345")))
        self.assertFalse(is_skipped_key(tracker, BoardKey("linkedin", "67890")))

    def test_mark_and_check_skipped_by_name(self):
        tracker = load_tracker(self.tracker_path)
        mark_skipped_key(tracker, ManualKey("Acme Corp", "Senior Engineer"))

        self.assertTrue(
            is_skipped_key(tracker, ManualKey("Acme Corp", "Senior Engineer"))
        )
        self.assertFalse(is_skipped_key(tracker, ManualKey("Acme Corp", "Junior Dev")))

    def test_is_skipped_falls_back_to_manual_when_called_with_source(self):
        """A job skipped manually (no source/id) should still match when it
        later reappears via a scraper that does know source+id — the caller
        passes the BoardKey as primary and a ManualKey as fallback."""
        tracker = load_tracker(self.tracker_path)
        mark_skipped_key(tracker, ManualKey("Acme Corp", "Senior Engineer"))

        # Same posting reappears via the Seek scraper with a real job_id.
        self.assertTrue(
            is_skipped_key(
                tracker,
                BoardKey("seek", "99999"),
                fallback=ManualKey("Acme Corp", "Senior Engineer"),
            )
        )

    def test_skipped_persists_across_loads(self):
        # First write
        tracker1 = load_tracker(self.tracker_path)
        mark_skipped_key(tracker1, BoardKey("seek", "job-slug"))
        from tools.lib.tracker import save_tracker

        save_tracker(self.tracker_path, tracker1)

        # Reload and check
        tracker2 = load_tracker(self.tracker_path)
        self.assertTrue(is_skipped_key(tracker2, BoardKey("seek", "job-slug")))


class ReconcileTests(unittest.TestCase):
    def setUp(self):
        self.source_root = Path(__file__).resolve().parents[1]
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

        # Set up directory structure
        (self.root / "applications" / "active").mkdir(parents=True)
        (self.root / "applications" / "archive" / "submitted").mkdir(parents=True)
        (self.root / "applications" / "archive" / "skipped").mkdir(parents=True)

        # Set up tracker (legacy v5 shape — load_tracker auto-migrates to v6)
        (self.root / "applications" / "application-tracker.json").write_text(
            '{"applications": {"active": []}, "seen_jobs": {}, "skipped_jobs": {}}'
        )

        # Create fake application directories (names match company_dirname)
        (self.root / "applications" / "active" / "Acme").mkdir()
        (self.root / "applications" / "active" / "Globex").mkdir()
        (self.root / "applications" / "active" / "Initech").mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_reconcile_moves_submitted_to_archive(self):
        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text(
            "- [x] **Senior Python Engineer** @ Acme (score: 82) · [JD](./acme/job.md) · [CV](./acme/cv.pdf) · [Letter](./acme/cover.md) · [Apply ↗](https://acme.com/apply)\n"
            "- [ ] **Backend Dev** @ Globex (score: 78) · [JD](./globex/job.md) · [CV](./globex/cv.pdf) · [Letter](./globex/cover.md) · [Apply ↗](https://globex.com/apply)\n"
        )

        result = reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        self.assertEqual(len(result.submitted), 1)
        self.assertIn("Acme — Senior Python Engineer", result.submitted)
        self.assertFalse((self.root / "applications" / "active" / "Acme").exists())
        self.assertTrue(
            (self.root / "applications" / "archive" / "submitted" / "Acme").exists()
        )

    def test_reconcile_moves_skipped_to_archive(self):
        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text(
            "- [~] **Frontend Lead** @ Initech (score: 65) · [JD](./initech/job.md) · [CV](./initech/cv.pdf) · [Letter](./initech/cover.md) · [Apply ↗](https://initech.com/apply)\n"
            "- [ ] **Backend Dev** @ Globex (score: 78) · [JD](./globex/job.md) · [CV](./globex/cv.pdf) · [Letter](./globex/cover.md) · [Apply ↗](https://globex.com/apply)\n"
        )

        result = reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        self.assertEqual(len(result.skipped), 1)
        self.assertIn("Initech — Frontend Lead", result.skipped)
        self.assertFalse((self.root / "applications" / "active" / "Initech").exists())
        self.assertTrue(
            (self.root / "applications" / "archive" / "skipped" / "Initech").exists()
        )

    def test_reconcile_keeps_active_items(self):
        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text(
            "- [ ] **Backend Dev** @ Globex (score: 78) · [JD](./globex/job.md) · [CV](./globex/cv.pdf) · [Letter](./globex/cover.md) · [Apply ↗](https://globex.com/apply)\n"
        )

        result = reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        self.assertEqual(len(result.kept), 1)
        self.assertTrue((self.root / "applications" / "active" / "Globex").exists())

    def test_reconcile_dry_run_does_not_move(self):
        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text(
            "- [x] **Senior Python Engineer** @ Acme (score: 82) · [JD](./acme/job.md) · [CV](./acme/cv.pdf) · [Letter](./acme/cover.md) · [Apply ↗](https://acme.com/apply)\n"
        )

        result = reconcile(self.root, inbox_path=inbox_path, dry_run=True)

        self.assertEqual(len(result.submitted), 1)
        self.assertTrue((self.root / "applications" / "active" / "Acme").exists())
        self.assertFalse(
            (self.root / "applications" / "archive" / "submitted" / "Acme").exists()
        )

    def test_reconcile_removes_archived_rows_from_inbox(self):
        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text(
            "- [x] **Senior Python Engineer** @ Acme (score: 82) · [JD](./acme/job.md) · [CV](./acme/cv.pdf) · [Letter](./acme/cover.md) · [Apply ↗](https://acme.com/apply)\n"
            "- [ ] **Backend Dev** @ Globex (score: 78) · [JD](./globex/job.md) · [CV](./globex/cv.pdf) · [Letter](./globex/cover.md) · [Apply ↗](https://globex.com/apply)\n"
        )

        reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        remaining = inbox_path.read_text()
        self.assertNotIn("Acme", remaining)
        self.assertIn("Globex", remaining)

    def test_reconcile_sets_submitted_status_for_byid_tracker_row(self):
        """Tracker rows scraped from job boards carry source+job_id, so the
        InboxItem must surface those (parsed from Apply URL) so item.key
        builds a BoardKey that matches the tracker row's key."""
        tracker_path = self.root / "applications" / "application-tracker.json"
        import json

        tracker = json.loads(tracker_path.read_text())
        tracker["applications"]["active"].append(
            {
                "company": "Acme",
                "position": "Senior Python Engineer",
                "date_applied": "2026-05-10",
                "status": "In Progress",
                "source": "seek",
                "job_id": "12345678",
                "url": "https://nz.seek.com/job/12345678?type=standard",
            }
        )
        tracker_path.write_text(json.dumps(tracker))

        # Recreate the active dir under the namespaced name
        (self.root / "applications" / "active" / "Acme-12345678").mkdir()

        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text(
            "- [x] **Senior Python Engineer** @ Acme (score: 82) · [JD](./x/job.md) · [CV](./x/cv.pdf) · [Letter](./x/cover.md) · [Apply ↗](https://nz.seek.com/job/12345678?type=standard)\n"
        )

        reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        tracker_after = json.loads(tracker_path.read_text())
        row = next(
            a for a in tracker_after["applications"]["active"] if a["company"] == "Acme"
        )
        self.assertEqual(row["status"], "Submitted")
        self.assertIsNotNone(row.get("submitted_at"))

    def test_reconcile_marks_skipped_in_tracker(self):
        """Verify that skipped items are added to skipped_jobs for dedup."""
        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text(
            "- [~] **Frontend Lead** @ Initech (score: 65) · [JD](./initech/job.md) · [CV](./initech/cv.pdf) · [Letter](./initech/cover.md) · [Apply ↗](https://initech.com/apply)\n"
        )

        tracker_path = self.root / "applications" / "application-tracker.json"
        tracker_before = load_tracker(tracker_path)

        self.assertFalse(
            is_skipped_key(tracker_before, ManualKey("Initech", "Frontend Lead"))
        )

        reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        tracker_after = load_tracker(tracker_path)
        self.assertTrue(
            is_skipped_key(tracker_after, ManualKey("Initech", "Frontend Lead"))
        )

    def test_reconcile_archives_orphan_active_dirs(self):
        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text("# Job INBOX\n\n")

        result = reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        self.assertEqual(len(result.cleaned_active), 3)
        self.assertFalse((self.root / "applications" / "active" / "Acme").exists())
        self.assertTrue(
            (self.root / "applications" / "archive" / "orphaned" / "Acme").exists()
        )

    def test_reconcile_keeps_tracker_active_dir_without_inbox_row(self):
        import json

        tracker_path = self.root / "applications" / "application-tracker.json"
        tracker = json.loads(tracker_path.read_text())
        tracker["applications"]["active"].append(
            {
                "company": "Acme",
                "position": "Backend Dev",
                "date_applied": "2026-05-10",
                "status": "In Progress",
            }
        )
        tracker_path.write_text(json.dumps(tracker))

        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text("# Job INBOX\n\n")

        reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        self.assertTrue((self.root / "applications" / "active" / "Acme").exists())

    def test_reconcile_archives_submitted_tracker_active_dir(self):
        import json

        tracker_path = self.root / "applications" / "application-tracker.json"
        tracker = json.loads(tracker_path.read_text())
        tracker["applications"]["active"].append(
            {
                "company": "Acme",
                "position": "Backend Dev",
                "date_applied": "2026-05-10",
                "status": "Submitted",
            }
        )
        tracker_path.write_text(json.dumps(tracker))

        inbox_path = self.root / "applications" / "INBOX.md"
        inbox_path.write_text("# Job INBOX\n\n")

        result = reconcile(self.root, inbox_path=inbox_path, dry_run=False)

        self.assertIn("Acme → archive/submitted/Acme", result.cleaned_active)
        self.assertFalse((self.root / "applications" / "active" / "Acme").exists())
        self.assertTrue(
            (self.root / "applications" / "archive" / "submitted" / "Acme").exists()
        )


if __name__ == "__main__":
    unittest.main()
