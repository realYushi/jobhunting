import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.lib.hunter import (
    HunterError,
    _domain_hint_from_url,
    best_contact_summary,
    discover_company_contacts,
    discover_contacts,
    top_contact_summaries,
)


class HunterTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / ".env").write_text("HUNTER_API_KEY=test-key\n")

    def tearDown(self):
        self.tempdir.cleanup()

    def test_discover_company_contacts_prefers_recruiter(self):
        payload = {
            "data": {
                "domain": "acme.com",
                "organization": "Acme",
                "emails": [
                    {
                        "value": "eng@acme.com",
                        "first_name": "Eve",
                        "last_name": "Engineer",
                        "position": "Engineering Manager",
                        "department": "it",
                        "seniority": "senior",
                        "type": "personal",
                        "confidence": 80,
                        "verification": {"status": "valid"},
                        "sources": [],
                    },
                    {
                        "value": "jane@acme.com",
                        "first_name": "Jane",
                        "last_name": "Recruiter",
                        "position": "Talent Partner",
                        "department": "hr",
                        "seniority": "senior",
                        "type": "personal",
                        "confidence": 75,
                        "verification": {"status": "valid"},
                        "sources": [],
                    },
                ],
            }
        }
        with patch("tools.lib.hunter._http_get_json", return_value=payload):
            result = discover_company_contacts("Acme", root=self.root, url="https://jobs.acme.com")

        self.assertEqual(result["top_contact"]["email"], "jane@acme.com")
        self.assertEqual(result["top_contacts"][0]["email"], "jane@acme.com")
        self.assertEqual(result["domain"], "acme.com")
        self.assertEqual(result["query"]["domain"], "acme.com")

    def test_discover_contacts_writes_files(self):
        payload = {
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
        app_dir = self.root / "applications" / "active" / "Acme"
        with patch("tools.lib.hunter.discover_company_contacts", return_value=payload):
            result = discover_contacts(app_dir, "Acme", root=self.root, url="https://acme.com/jobs")

        self.assertEqual(result["top_contact"]["email"], "jane@acme.com")
        self.assertTrue((app_dir / "research" / "contacts.json").exists())
        self.assertTrue((app_dir / "research" / "contacts.md").exists())
        stored = json.loads((app_dir / "research" / "contacts.json").read_text())
        self.assertEqual(stored["top_contact"]["email"], "jane@acme.com")

    def test_top_contact_summaries_reads_three_contacts(self):
        app_dir = self.root / "applications" / "archive" / "submitted" / "Acme"
        research = app_dir / "research"
        research.mkdir(parents=True)
        (research / "contacts.json").write_text(
            json.dumps(
                {
                    "contacts": [
                        {
                            "full_name": "Jane Recruiter",
                            "position": "Talent Partner",
                            "email": "jane@acme.com",
                        },
                        {
                            "full_name": "Eve Manager",
                            "position": "Engineering Manager",
                            "email": "eve@acme.com",
                        },
                        {
                            "full_name": "Sam HR",
                            "position": "HR Business Partner",
                            "email": "sam@acme.com",
                        },
                    ]
                }
            )
        )

        summaries = top_contact_summaries(app_dir)
        self.assertEqual(len(summaries), 3)
        self.assertIn("Jane Recruiter", summaries[0])
        self.assertIn("Eve Manager", summaries[1])
        self.assertIn("Sam HR", summaries[2])

    def test_domain_hint_reduces_subdomains_to_apex(self):
        # Hunter indexes apex domains; a careers/jobs subdomain would return
        # nothing, so the hint must be reduced to the registrable domain.
        self.assertEqual(_domain_hint_from_url("https://careers.acme.com/x"), "acme.com")
        self.assertEqual(_domain_hint_from_url("https://jobs.acme.co.nz/x"), "acme.co.nz")
        self.assertEqual(_domain_hint_from_url("https://www.acme.com"), "acme.com")
        # ATS hosts and job-board aggregators yield no hint (fall back to
        # company-name search) — never the board's own domain.
        self.assertIsNone(_domain_hint_from_url("https://boards.greenhouse.io/acme"))
        self.assertIsNone(_domain_hint_from_url("https://nz.seek.com/job/123"))

    def test_network_timeout_is_wrapped_and_soft_fails(self):
        # A read timeout (socket.timeout/TimeoutError) is not a URLError; it must
        # be wrapped as HunterError and degrade to a "skipped/error" result
        # rather than crashing the caller.
        with patch("tools.lib.hunter._http_get_json", side_effect=TimeoutError("timed out")):
            with self.assertRaises(HunterError):
                discover_company_contacts("Acme", root=self.root, url="https://acme.com")

        app_dir = self.root / "applications" / "active" / "Acme"
        with patch("tools.lib.hunter._http_get_json", side_effect=TimeoutError("timed out")):
            result = discover_contacts(app_dir, "Acme", root=self.root, url="https://acme.com")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["contacts"], [])

    def test_best_contact_summary_reads_saved_contact(self):
        app_dir = self.root / "applications" / "archive" / "submitted" / "Acme"
        research = app_dir / "research"
        research.mkdir(parents=True)
        (research / "contacts.json").write_text(
            json.dumps(
                {
                    "top_contact": {
                        "full_name": "Jane Recruiter",
                        "position": "Talent Partner",
                        "email": "jane@acme.com",
                    }
                }
            )
        )

        summary = best_contact_summary(app_dir)
        self.assertEqual(summary, "Jane Recruiter — Talent Partner <jane@acme.com>")


if __name__ == "__main__":
    unittest.main()
