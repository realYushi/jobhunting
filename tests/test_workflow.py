import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from lib.app_state import ApplicationState
from lib.tracker import (
    ApplicationRecord,
    empty_tracker,
    upsert_active_application,
)
from lib.workflow import WorkflowOptions, create_application_package


class TrackerTests(unittest.TestCase):
    def test_upsert_active_application_replaces_same_company_position(self):
        tracker = empty_tracker()
        first = ApplicationRecord("Acme", "Engineer", "2026-01-01", priority="Low")
        second = ApplicationRecord("Acme", "Engineer", "2026-01-02", priority="High")

        upsert_active_application(tracker, first)
        upsert_active_application(tracker, second)

        active = tracker["applications"]["active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["priority"], "High")
        self.assertEqual(active[0]["date_applied"], "2026-01-02")

    def test_upsert_treats_company_variants_as_same_when_job_id_matches(self):
        tracker = empty_tracker()
        upsert_active_application(
            tracker,
            ApplicationRecord(
                "Caruso", "Engineer", "2026-01-01",
                source="linkedin", job_id="L-1",
            ),
        )
        upsert_active_application(
            tracker,
            ApplicationRecord(
                "Caruso Corp", "Engineer", "2026-01-02",
                source="linkedin", job_id="L-1",
            ),
        )
        active = tracker["applications"]["active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["company"], "Caruso Corp")

    def test_upsert_keeps_different_job_ids_separate(self):
        tracker = empty_tracker()
        upsert_active_application(
            tracker,
            ApplicationRecord(
                "Acme", "Engineer", "2026-01-01",
                source="linkedin", job_id="L-1",
            ),
        )
        upsert_active_application(
            tracker,
            ApplicationRecord(
                "Acme", "Engineer", "2026-01-02",
                source="linkedin", job_id="L-2",
            ),
        )
        active = tracker["applications"]["active"]
        self.assertEqual(len(active), 2)

    def test_upsert_does_not_add_seen_field(self):
        """upsert_active_application no longer marks seen — no seen key in tracker."""
        tracker = empty_tracker()
        upsert_active_application(
            tracker,
            ApplicationRecord(
                "Acme", "Engineer", "2026-01-01",
                source="linkedin", job_id="L-1",
            ),
        )
        self.assertNotIn("seen", tracker)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.source_root = Path(__file__).resolve().parents[1]
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "templates").mkdir()
        for name in (
            "base-resume.json",
            "cover-letter.md",
            "analysis-template.md",
            "cold-email.md",
        ):
            shutil.copyfile(
                self.source_root / "templates" / name,
                self.root / "templates" / name,
            )
        (self.root / "applications").mkdir()
        (self.root / ".env").write_text("HUNTER_API_KEY=test-key\n")
        self.job_path = self.root / "job.md"
        self.job_path.write_text("We need React, TypeScript, and FastAPI.")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_dry_run_does_not_write_application_directory(self):
        options = WorkflowOptions(
            project_root=self.root,
            job_path=self.job_path,
            company="Acme",
            position="Frontend Engineer",
            role="frontend",
            keywords=("React", "FastAPI"),
            dry_run=True,
        )
        result = create_application_package(options)

        self.assertIn("Acme", str(result.application_dir))
        self.assertFalse((self.root / "applications" / "active" / "Acme").exists())

    def test_create_application_package_writes_expected_files_and_tracker(self):
        options = WorkflowOptions(
            project_root=self.root,
            job_path=self.job_path,
            company="Acme",
            position="Frontend Engineer",
            role="frontend",
            keywords=("React", "FastAPI"),
            dry_run=False,
        )
        create_application_package(options)

        app_dir = self.root / "applications" / "active" / "Acme"
        self.assertTrue((app_dir / "research" / "job-description.md").exists())
        self.assertTrue((app_dir / "research" / "analysis.md").exists())
        self.assertTrue((app_dir / "documents" / "resume.json").exists())
        self.assertTrue((app_dir / "documents" / "cover-letter.md").exists())
        # Cold email + contact discovery are deferred to submit time (reconcile):
        # the email needs a resolved recipient, and this conserves Hunter quota.
        self.assertFalse((app_dir / "documents" / "cold-email.md").exists())
        self.assertFalse((app_dir / "research" / "contacts.json").exists())

        tracker_path = self.root / "applications" / "application-tracker.json"
        tracker = json.loads(tracker_path.read_text())
        self.assertEqual(tracker["applications"]["active"][0]["company"], "Acme")

    def test_cover_letter_substitutes_placeholders_and_uses_default_salutation(self):
        options = WorkflowOptions(
            project_root=self.root,
            job_path=self.job_path,
            company="Acme",
            position="Frontend Engineer",
            role="frontend",
            keywords=("React", "FastAPI"),
            dry_run=False,
        )
        create_application_package(options)

        cover_text = (
            self.root
            / "applications"
            / "active"
            / "Acme"
            / "documents"
            / "cover-letter.md"
        ).read_text()

        self.assertIn("Acme", cover_text)
        self.assertIn("Frontend Engineer", cover_text)
        self.assertIn(date.today().isoformat(), cover_text)
        self.assertNotIn("[Company Name]", cover_text)
        self.assertNotIn("[Job Title]", cover_text)
        self.assertNotIn("[YYYY-MM-DD]", cover_text)
        self.assertIn("Hi Hiring Team,", cover_text)

    def test_unfilled_editor_prompts_surface_as_warnings(self):
        options = WorkflowOptions(
            project_root=self.root,
            job_path=self.job_path,
            company="Acme",
            position="Frontend Engineer",
            role="frontend",
            keywords=("React",),
            dry_run=False,
        )
        result = create_application_package(options)

        joined = "\n".join(result.warnings)
        self.assertIn("[Add one specific sentence", joined)
        self.assertIn("[Paragraph 2 should", joined)


class ApplicationStateTests(unittest.TestCase):
    """ApplicationState: load → upsert → save → reload verifies the full cycle."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.tracker_path = Path(self.tempdir.name) / "application-tracker.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_load_creates_default_when_missing(self):
        state = ApplicationState.load(self.tracker_path)
        self.assertFalse(self.tracker_path.exists())  # not written until save
        self.assertIn("applications", state.tracker)

    def test_upsert_and_save_persist_to_disk(self):
        state = ApplicationState.load(self.tracker_path)
        state.upsert_active(
            ApplicationRecord("Acme", "Engineer", "2026-06-01", priority="High")
        )
        state.save()

        reloaded = ApplicationState.load(self.tracker_path)
        active = reloaded.tracker["applications"]["active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["company"], "Acme")
        self.assertEqual(active[0]["priority"], "High")

    def test_two_upserts_one_save(self):
        # The whole point of ApplicationState: load once, upsert N times, save once.
        state = ApplicationState.load(self.tracker_path)
        state.upsert_active(ApplicationRecord("AlphaCo", "Dev A", "2026-06-01"))
        state.upsert_active(ApplicationRecord("BetaCo", "Dev B", "2026-06-01"))
        state.save()

        reloaded = ApplicationState.load(self.tracker_path)
        companies = {r["company"] for r in reloaded.tracker["applications"]["active"]}
        self.assertEqual(companies, {"AlphaCo", "BetaCo"})

    def test_keyset_roundtrip(self):
        from lib.identity import ManualKey

        state = ApplicationState.load(self.tracker_path)
        keys = {ManualKey("Acme", "Engineer")}
        state.store_keyset("skipped", keys)
        state.save()

        reloaded = ApplicationState.load(self.tracker_path)
        result = reloaded.keyset("skipped")
        self.assertIn(ManualKey("Acme", "Engineer"), result)

    def test_iter_applications_all_buckets(self):
        state = ApplicationState.load(self.tracker_path)
        state.upsert_active(ApplicationRecord("AlphaCo", "Dev", "2026-06-01"))
        apps = state.iter_applications()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["company"], "AlphaCo")

    def test_iter_applications_specific_bucket(self):
        state = ApplicationState.load(self.tracker_path)
        state.upsert_active(ApplicationRecord("AlphaCo", "Dev", "2026-06-01"))
        apps = state.iter_applications(buckets=("active",))
        self.assertEqual(len(apps), 1)
        apps_rejected = state.iter_applications(buckets=("rejected",))
        self.assertEqual(len(apps_rejected), 0)


if __name__ == "__main__":
    unittest.main()
