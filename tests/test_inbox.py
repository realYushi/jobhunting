import tempfile
import unittest
from pathlib import Path

from tools.lib.inbox import (
    InboxRow,
    clear_inbox,
    format_row,
    write_inbox_row,
    write_inbox_rows,
)


class FormatRowTests(unittest.TestCase):
    def test_format_row_with_score(self):
        row = InboxRow(
            title="Senior Python Engineer",
            company="Acme",
            slug="acme",
            score=82,
            url="https://acme.com/apply",
        )
        line = format_row(row)
        self.assertIn("[ ]", line)
        self.assertIn("**Senior Python Engineer**", line)
        self.assertIn("@ Acme", line)
        self.assertIn("(score: 82)", line)
        self.assertIn("[JD](./active/acme/research/job-description.md)", line)
        self.assertIn("[CV](./active/acme/documents/resume.pdf)", line)
        self.assertIn("[Letter](./active/acme/documents/cover-letter.pdf)", line)
        self.assertIn("[Apply ↗](https://acme.com/apply)", line)
        self.assertIn(" · ", line)

    def test_format_row_without_score(self):
        row = InboxRow(
            title="Backend Dev",
            company="Globex",
            slug="globex",
        )
        line = format_row(row)
        self.assertNotIn("(score:", line)
        self.assertIn("**Backend Dev**", line)
        self.assertIn("@ Globex", line)

    def test_format_row_submitted(self):
        row = InboxRow(
            title="Frontend Lead",
            company="Initech",
            slug="initech",
            score=65,
            status="[x]",
        )
        line = format_row(row)
        self.assertIn("[x]", line)
        self.assertNotIn("[ ]", line)


class WriteInboxTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.inbox_path = Path(self.tempdir.name) / "INBOX.md"

    def tearDown(self):
        self.tempdir.cleanup()

    def test_write_creates_new_inbox(self):
        row = InboxRow(
            title="Senior Python Engineer",
            company="Acme",
            slug="acme",
            score=82,
        )
        write_inbox_row(self.inbox_path, row)

        self.assertTrue(self.inbox_path.exists())
        content = self.inbox_path.read_text()
        self.assertIn("# Job INBOX", content)
        self.assertIn("Senior Python Engineer", content)

    def test_write_appends_to_existing_inbox(self):
        # First row
        write_inbox_row(
            self.inbox_path,
            InboxRow(
                title="Senior Python Engineer", company="Acme", slug="acme", score=82
            ),
        )
        # Second row
        write_inbox_row(
            self.inbox_path,
            InboxRow(title="Backend Dev", company="Globex", slug="globex", score=78),
        )

        content = self.inbox_path.read_text()
        self.assertIn("Acme", content)
        self.assertIn("Globex", content)
        # Should only have one header
        self.assertEqual(content.count("# Job INBOX"), 1)

    def test_write_does_not_duplicate(self):
        row = InboxRow(
            title="Senior Python Engineer",
            company="Acme",
            slug="acme",
            score=82,
        )
        write_inbox_row(self.inbox_path, row)
        write_inbox_row(self.inbox_path, row)  # Same row again

        content = self.inbox_path.read_text()
        # Count occurrences of the company name (should be 1, not 2)
        lines = [line for line in content.splitlines() if "Acme" in line]
        self.assertEqual(len(lines), 1)

    def test_write_keeps_titles_that_are_substrings(self):
        write_inbox_row(
            self.inbox_path,
            InboxRow(
                title="Java Developer",
                company="Evolve Recruitment Group",
                slug="evolve-java",
                score=82,
            ),
        )
        write_inbox_row(
            self.inbox_path,
            InboxRow(
                title="Developer",
                company="Evolve Recruitment Group",
                slug="evolve-developer",
                score=80,
            ),
        )

        content = self.inbox_path.read_text()
        lines = [line for line in content.splitlines() if "Evolve Recruitment Group" in line]
        self.assertEqual(len(lines), 2)

    def test_write_multiple_rows(self):
        rows = [
            InboxRow(
                title="Senior Python Engineer", company="Acme", slug="acme", score=82
            ),
            InboxRow(title="Backend Dev", company="Globex", slug="globex", score=78),
            InboxRow(
                title="Frontend Lead", company="Initech", slug="initech", score=65
            ),
        ]
        write_inbox_rows(self.inbox_path, rows)

        content = self.inbox_path.read_text()
        self.assertIn("Acme", content)
        self.assertIn("Globex", content)
        self.assertIn("Initech", content)

    def test_clear_inbox(self):
        write_inbox_row(
            self.inbox_path,
            InboxRow(
                title="Senior Python Engineer", company="Acme", slug="acme", score=82
            ),
        )
        self.assertIn("Acme", self.inbox_path.read_text())

        clear_inbox(self.inbox_path)
        content = self.inbox_path.read_text()
        self.assertIn("# Job INBOX", content)
        self.assertNotIn("Acme", content)


if __name__ == "__main__":
    unittest.main()
