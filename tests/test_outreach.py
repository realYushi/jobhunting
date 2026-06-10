import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from outreach import _prepare_target, prepare_targets


class OutreachPrepareTargetTests(unittest.TestCase):
    def test_prepare_target_resolves_archive_from_pdf_path_and_scaffolds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive_dir = root / "applications" / "archive" / "submitted" / "Acme-12345678"
            (archive_dir / "research").mkdir(parents=True)
            (archive_dir / "documents").mkdir(parents=True)
            (archive_dir / "research" / "job-description.md").write_text("JD text")
            (archive_dir / "research" / "analysis.md").write_text("Analysis")
            (archive_dir / "documents" / "resume.json").write_text("{}")
            (archive_dir / "research" / "contacts.json").write_text(json.dumps({"contacts": []}))

            app = {
                "company": "Acme",
                "position": "Software Engineer",
                "job_id": "1234567890",
                "pdf_path": "applications/archive/submitted/Acme-12345678/documents/resume.pdf",
            }

            with patch("outreach.top_contacts", return_value=[]), patch(
                "outreach.render_cold_email", return_value="email body"
            ):
                target = _prepare_target(root, app, scaffold=True)

            self.assertEqual(target["archive_path"], str(archive_dir))
            self.assertEqual(target["subagent_type"], "outreach-company")
            self.assertIn("agent_prompt", target)
            self.assertTrue((archive_dir / "documents" / "cold-email.md").exists())
            self.assertEqual(
                (archive_dir / "documents" / "cold-email.md").read_text(), "email body"
            )

    def test_prepare_target_raises_when_archive_missing(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            app = {
                "company": "Missing Co",
                "position": "Engineer",
                "job_id": "abc123",
                "pdf_path": "applications/archive/submitted/Missing Co-abc123/documents/resume.pdf",
            }
            with self.assertRaises(FileNotFoundError):
                _prepare_target(root, app, scaffold=False)


class OutreachPrepareCommandTests(unittest.TestCase):
    def test_prepare_targets_writes_queue_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            archive_dir = root / "applications" / "archive" / "submitted" / "Acme-12345678"
            (archive_dir / "research").mkdir(parents=True)
            (archive_dir / "documents").mkdir(parents=True)
            (archive_dir / "research" / "job-description.md").write_text("JD text")
            (archive_dir / "research" / "analysis.md").write_text("Analysis")
            (archive_dir / "documents" / "resume.json").write_text("{}")
            tracker_path = root / "applications" / "application-tracker.json"
            tracker_path.parent.mkdir(parents=True, exist_ok=True)
            tracker_path.write_text(
                json.dumps(
                    {
                        "applications": {
                            "active": [
                                {
                                    "company": "Acme",
                                    "position": "Software Engineer",
                                    "status": "Submitted",
                                    "job_id": "1234567890",
                                    "pdf_path": "applications/archive/submitted/Acme-12345678/documents/resume.pdf",
                                }
                            ]
                        }
                    }
                )
            )
            out = root / "tmp.json"

            with patch("outreach.project_root", return_value=root), patch(
                "outreach.top_contacts", return_value=[]
            ), patch("outreach.render_cold_email", return_value="email body"):
                count, targets = prepare_targets([1], output=str(out), no_scaffold=False)

            self.assertEqual(count, 1)
            payload = json.loads(out.read_text())
            self.assertEqual(len(payload["targets"]), 1)
            self.assertEqual(payload["targets"][0]["company"], "Acme")
            self.assertEqual(targets[0]["subagent_type"], "outreach-company")


if __name__ == "__main__":
    unittest.main()
