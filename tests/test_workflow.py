import json
import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from tools.lib.identity import BoardKey
from tools.lib.tracker import (
    ApplicationRecord,
    empty_tracker,
    is_seen_key,
    mark_seen_key,
    upsert_active_application,
)
from tools.lib.workflow import WorkflowOptions, create_application_package


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

    def test_upsert_marks_seen_when_source_and_job_id_present(self):
        tracker = empty_tracker()
        upsert_active_application(
            tracker,
            ApplicationRecord(
                "Acme", "Engineer", "2026-01-01",
                source="linkedin", job_id="L-1",
            ),
        )
        self.assertTrue(is_seen_key(tracker, BoardKey("linkedin", "L-1")))
        upsert_active_application(
            tracker,
            ApplicationRecord("Bravo", "Engineer", "2026-01-01"),
        )
        self.assertFalse(is_seen_key(tracker, BoardKey("linkedin", "L-2")))

    def test_mark_seen_is_idempotent(self):
        from tools.lib.identity import from_dict

        tracker = empty_tracker()
        mark_seen_key(tracker, BoardKey("seek", "abc"))
        mark_seen_key(tracker, BoardKey("seek", "abc"))
        keys = [from_dict(d) for d in tracker["seen"]]
        self.assertEqual(keys, [BoardKey("seek", "abc")])


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
        self.assertTrue((app_dir / "research" / "contacts.json").exists())
        self.assertTrue((app_dir / "research" / "contacts.md").exists())
        self.assertTrue((app_dir / "documents" / "resume.json").exists())
        self.assertTrue((app_dir / "documents" / "cover-letter.md").exists())
        self.assertTrue((app_dir / "documents" / "cold-email.md").exists())

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

    def test_cold_email_is_generated_from_template(self):
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

        cold_email_text = (
            self.root
            / "applications"
            / "active"
            / "Acme"
            / "documents"
            / "cold-email.md"
        ).read_text()

        self.assertIn("Quick question about Frontend Engineer at Acme", cold_email_text)
        self.assertIn("GrowLab Technologies", cold_email_text)
        self.assertNotIn("[Company Name]", cold_email_text)
        self.assertNotIn("[Job Title]", cold_email_text)

    def test_cold_email_uses_recruiter_style_for_job_board_source(self):
        options = WorkflowOptions(
            project_root=self.root,
            job_path=self.job_path,
            company="Acme",
            position="Frontend Engineer",
            role="frontend",
            keywords=("React", "FastAPI"),
            source="seek",
            job_id="12345678",
            url="https://nz.seek.com/job/12345678",
            dry_run=False,
        )
        create_application_package(options)

        cold_email_text = (
            self.root
            / "applications"
            / "active"
            / "Acme-12345678"
            / "documents"
            / "cold-email.md"
        ).read_text()

        self.assertIn(
            "happy to be pointed to whoever handles hiring for this role",
            cold_email_text,
        )
        self.assertIn("recruiter-style", cold_email_text)

    def test_cold_email_uses_hiring_manager_style_for_direct_company_role(self):
        options = WorkflowOptions(
            project_root=self.root,
            job_path=self.job_path,
            company="Acme",
            position="Frontend Engineer",
            role="frontend",
            keywords=("React", "FastAPI"),
            url="https://acme.com/careers/frontend-engineer",
            dry_run=False,
        )
        create_application_package(options)

        cold_email_text = (
            self.root
            / "applications"
            / "active"
            / "Acme"
            / "documents"
            / "cold-email.md"
        ).read_text()

        self.assertIn(
            "I’d be glad to share a few relevant examples of my work",
            cold_email_text,
        )
        self.assertIn("hiring-manager-style", cold_email_text)

    def test_contact_discovery_is_written_when_available(self):
        options = WorkflowOptions(
            project_root=self.root,
            job_path=self.job_path,
            company="Acme",
            position="Frontend Engineer",
            role="frontend",
            keywords=("React", "FastAPI"),
            dry_run=False,
        )
        hunter_payload = {
            "status": "ok",
            "company": "Acme",
            "domain": "acme.com",
            "contacts": [
                {
                    "full_name": "Jane Recruiter",
                    "email": "jane@acme.com",
                    "position": "Talent Partner",
                    "verification_status": "valid",
                    "confidence": 90,
                }
            ],
            "top_contact": {
                "full_name": "Jane Recruiter",
                "email": "jane@acme.com",
                "position": "Talent Partner",
            },
        }
        with patch("tools.lib.hunter.discover_company_contacts", return_value=hunter_payload):
            create_application_package(options)

        contacts_json = json.loads(
            (
                self.root
                / "applications"
                / "active"
                / "Acme"
                / "research"
                / "contacts.json"
            ).read_text()
        )
        self.assertEqual(contacts_json["top_contact"]["email"], "jane@acme.com")

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


if __name__ == "__main__":
    unittest.main()
