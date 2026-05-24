import tempfile
import unittest
from pathlib import Path

from tools.lib.linkedin_status import (
    StatusUpdate,
    apply_status_updates,
    detect_status_updates,
)


class LinkedInStatusTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "applications" / "active").mkdir(parents=True)
        (self.root / "applications" / "archive" / "rejected").mkdir(parents=True)
        (self.root / "applications" / "archive" / "withdrawn").mkdir(parents=True)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_detect_rejection_for_linkedin_active_application(self):
        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Kami",
                        "position": "Software Engineer",
                        "source": "linkedin",
                        "job_id": "4395941390",
                        "status": "In Progress",
                    }
                ],
                "interviews": [],
                "offers": [],
                "rejected": [],
                "withdrawn": [],
            }
        }
        payload = {
            "notifications": "Application update from Kami We are not moving forward with your application.",
            "messaging": "",
        }

        updates = detect_status_updates(tracker, payload)

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].company, "Kami")
        self.assertEqual(updates[0].position, "Software Engineer")
        self.assertEqual(updates[0].to_bucket, "rejected")

    def test_detect_requires_position_when_company_has_multiple_roles(self):
        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Kami",
                        "position": "Software Engineer",
                        "source": "linkedin",
                        "job_id": "1",
                        "status": "In Progress",
                    },
                    {
                        "company": "Kami",
                        "position": "Product Manager",
                        "source": "linkedin",
                        "job_id": "2",
                        "status": "In Progress",
                    },
                ],
                "interviews": [],
                "offers": [],
                "rejected": [],
                "withdrawn": [],
            }
        }
        payload = {
            "notifications": "Application update from Kami for the Software Engineer role. We are not moving forward with your application.",
            "messaging": "",
        }

        updates = detect_status_updates(tracker, payload)

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].position, "Software Engineer")

    def test_detect_does_not_match_company_substring(self):
        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Ai",
                        "position": "Engineer",
                        "source": "linkedin",
                        "job_id": "1",
                        "status": "In Progress",
                    }
                ],
                "interviews": [],
                "offers": [],
                "rejected": [],
                "withdrawn": [],
            }
        }
        payload = {
            "notifications": "Thanks for maintaining your profile. Your application was not selected.",
            "messaging": "",
        }

        updates = detect_status_updates(tracker, payload)

        self.assertEqual(updates, [])

    def test_detect_ignores_non_linkedin_application(self):
        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Evolve Recruitment Group",
                        "position": "Java Developer",
                        "source": "seek",
                        "job_id": "92100682",
                        "status": "In Progress",
                    }
                ],
                "interviews": [],
                "offers": [],
                "rejected": [],
                "withdrawn": [],
            }
        }
        payload = {
            "notifications": "Application update from Evolve Recruitment Group We are not moving forward with your application.",
            "messaging": "",
        }

        updates = detect_status_updates(tracker, payload)

        self.assertEqual(updates, [])

    def test_apply_rejection_moves_tracker_row_and_directory(self):
        app_dir = self.root / "applications" / "active" / "Kami-43959413"
        (app_dir / "documents").mkdir(parents=True)
        (app_dir / "research").mkdir(parents=True)
        (app_dir / "documents" / "resume.pdf").write_text("pdf")

        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Kami",
                        "position": "Software Engineer",
                        "source": "linkedin",
                        "job_id": "4395941390",
                        "status": "In Progress",
                        "pdf_path": "applications/active/Kami-43959413/documents/resume.pdf",
                    }
                ],
                "interviews": [],
                "offers": [],
                "rejected": [],
                "withdrawn": [],
            }
        }
        updates = [
            StatusUpdate(
                company="Kami",
                position="Software Engineer",
                from_bucket="active",
                to_bucket="rejected",
                status="Rejected",
                evidence="Application update from Kami We are not moving forward with your application.",
            )
        ]

        applied = apply_status_updates(tracker, updates, root=self.root, today=None)

        self.assertEqual(len(applied), 1)
        self.assertEqual(tracker["applications"]["active"], [])
        self.assertEqual(len(tracker["applications"]["rejected"]), 1)
        row = tracker["applications"]["rejected"][0]
        self.assertEqual(row["status"], "Rejected")
        self.assertIn("rejected_at", row)
        self.assertEqual(
            row["pdf_path"],
            "applications/archive/rejected/Kami-43959413/documents/resume.pdf",
        )
        self.assertFalse(app_dir.exists())
        self.assertTrue(
            (self.root / "applications" / "archive" / "rejected" / "Kami-43959413").exists()
        )

    def test_apply_dry_run_leaves_directory_in_place(self):
        app_dir = self.root / "applications" / "active" / "Kami-43959413"
        app_dir.mkdir(parents=True)
        tracker = {
            "applications": {
                "active": [
                    {
                        "company": "Kami",
                        "position": "Software Engineer",
                        "source": "linkedin",
                        "job_id": "4395941390",
                        "status": "In Progress",
                    }
                ],
                "interviews": [],
                "offers": [],
                "rejected": [],
                "withdrawn": [],
            }
        }
        updates = [
            StatusUpdate(
                company="Kami",
                position="Software Engineer",
                from_bucket="active",
                to_bucket="rejected",
                status="Rejected",
                evidence="Application update from Kami We are not moving forward with your application.",
            )
        ]

        apply_status_updates(tracker, updates, root=self.root, dry_run=True)

        self.assertTrue(app_dir.exists())
        self.assertEqual(len(tracker["applications"]["rejected"]), 1)


if __name__ == "__main__":
    unittest.main()
