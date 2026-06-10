import shutil
import sys
import unittest
from pathlib import Path

from lib.pdf import (  # noqa: E402
    PdfRenderError,
    _normalize_resume,
    html_to_text,
    render_resume_pdf,
)


class HtmlToTextTests(unittest.TestCase):
    def test_empty_input_returns_empty_string(self):
        self.assertEqual(html_to_text(""), "")
        self.assertEqual(html_to_text(None), "")

    def test_paragraphs_become_blank_line_separated(self):
        html = "<p>First paragraph.</p><p>Second paragraph.</p>"
        out = html_to_text(html)
        self.assertEqual(out, "First paragraph.\n\nSecond paragraph.")

    def test_br_becomes_newline(self):
        out = html_to_text("Line one<br>Line two<br/>Line three")
        self.assertEqual(out.splitlines(), ["Line one", "Line two", "Line three"])

    def test_inline_tags_are_stripped_but_text_preserved(self):
        out = html_to_text("<p>Shipped <strong>10x</strong> faster.</p>")
        self.assertEqual(out, "Shipped 10x faster.")

    def test_html_entities_are_decoded(self):
        # Per-line whitespace collapses, so &nbsp; (→ space) merges with
        # adjacent spaces; what we care about is that the named entities decode.
        out = html_to_text("<p>Tom &amp; Jerry &lt;3 done</p>")
        self.assertEqual(out, "Tom & Jerry <3 done")

    def test_excess_blank_lines_collapse(self):
        out = html_to_text("<p>A</p><p></p><p></p><p>B</p>")
        # Should not pile up more than one blank line between text blocks.
        self.assertNotIn("\n\n\n", out)


class NormalizeResumeTests(unittest.TestCase):
    def _resume(self, **overrides) -> dict:
        base = {
            "basics": {
                "name": "Jane Doe",
                "headline": "Engineer",
                "email": "j@example.com",
                "phone": "+1",
                "location": "Remote",
                "website": {"url": "https://example.com"},
                "customFields": [{"link": "https://github.com/jd"}],
            },
            "summary": {"name": "Summary", "content": "<p>Hi.</p>"},
            "sections": {},
        }
        base.update(overrides)
        return base

    def test_basics_flatten_to_contact_list(self):
        # The http(s):// scheme is stripped from display URLs so the contact
        # line in the PDF doesn't wrap inside the protocol.
        out = _normalize_resume(self._resume())
        self.assertEqual(out["name"], "Jane Doe")
        self.assertEqual(out["headline"], "Engineer")
        self.assertEqual(
            out["contact"],
            [
                "j@example.com",
                "+1",
                "Remote",
                "example.com",
                "github.com/jd",
            ],
        )

    def test_hidden_summary_renders_empty(self):
        out = _normalize_resume(
            self._resume(summary={"hidden": True, "content": "<p>hi</p>"})
        )
        self.assertEqual(out["summary"], "")

    def test_visible_summary_is_html_stripped(self):
        out = _normalize_resume(self._resume())
        self.assertEqual(out["summary"], "Hi.")

    def test_hidden_section_is_skipped(self):
        out = _normalize_resume(
            self._resume(
                sections={
                    "experience": {
                        "hidden": True,
                        "items": [{"company": "Acme", "position": "Eng"}],
                    }
                }
            )
        )
        self.assertEqual(out["sections"], [])

    def test_empty_section_is_skipped(self):
        out = _normalize_resume(
            self._resume(sections={"experience": {"hidden": False, "items": []}})
        )
        self.assertEqual(out["sections"], [])

    def test_hidden_items_within_section_are_filtered(self):
        out = _normalize_resume(
            self._resume(
                sections={
                    "experience": {
                        "items": [
                            {"company": "Visible Co", "position": "Eng"},
                            {"company": "Hidden Co", "position": "Eng", "hidden": True},
                        ]
                    }
                }
            )
        )
        self.assertEqual(len(out["sections"]), 1)
        items = out["sections"][0]["items"]
        self.assertEqual(len(items), 1)
        self.assertIn("Visible Co", items[0]["title"])

    def test_education_uses_raw_grade_field(self):
        # Regression: GPA prefix duplication. The grade field already contains
        # "GPA: ..." in the canonical resume; the normalizer must not add its own.
        out = _normalize_resume(
            self._resume(
                sections={
                    "education": {
                        "items": [
                            {
                                "school": "MIT",
                                "degree": "BS",
                                "grade": "GPA: 4.0/4.0",
                            }
                        ]
                    }
                }
            )
        )
        subtitle = out["sections"][0]["items"][0]["subtitle"]
        self.assertIn("GPA: 4.0/4.0", subtitle)
        self.assertNotIn("GPA GPA", subtitle)

    def test_sections_render_in_canonical_order(self):
        out = _normalize_resume(
            self._resume(
                sections={
                    "skills": {"items": [{"name": "Backend", "keywords": ["Go"]}]},
                    "experience": {
                        "items": [{"company": "Acme", "position": "Eng"}]
                    },
                    "education": {
                        "items": [{"school": "MIT", "degree": "BS"}]
                    },
                }
            )
        )
        titles = [s["title"] for s in out["sections"]]
        # _SECTION_ORDER puts experience first, then skills, then education.
        self.assertEqual(
            titles.index("Experience") < titles.index("Skills") < titles.index("Education"),
            True,
        )


@unittest.skipIf(shutil.which("typst") is None, "typst not installed")
class RenderResumePdfSmokeTests(unittest.TestCase):
    def test_renders_a_non_empty_pdf(self):
        repo_root = Path(__file__).resolve().parents[1]
        resume = {
            "basics": {
                "name": "Jane Doe",
                "headline": "Engineer",
                "email": "j@example.com",
            },
            "summary": {"name": "Summary", "content": "<p>A short summary.</p>"},
            "sections": {
                "experience": {
                    "items": [
                        {
                            "company": "Acme",
                            "position": "Engineer",
                            "period": "2020 — Present",
                            "description": "<p>Did things.</p>",
                        }
                    ]
                }
            },
        }
        out_dir = repo_root / ".typst-tmp" / "test-out"
        out_dir.mkdir(parents=True, exist_ok=True)
        output = out_dir / "smoke.pdf"
        if output.exists():
            output.unlink()
        try:
            render_resume_pdf(resume, output, project_dir=repo_root)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 0)
            with open(output, "rb") as f:
                head = f.read(4)
            self.assertEqual(head, b"%PDF")
        finally:
            if output.exists():
                output.unlink()

    def test_missing_template_raises(self):
        repo_root = Path(__file__).resolve().parents[1]
        with self.assertRaises(PdfRenderError):
            render_resume_pdf(
                {"basics": {"name": "X"}, "sections": {}},
                Path("/tmp/should-not-be-written.pdf"),
                template_path=repo_root / "templates" / "does-not-exist.typ",
                project_dir=repo_root,
            )


if __name__ == "__main__":
    unittest.main()
