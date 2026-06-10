"""Tests for the unified scoring library.

These cover behaviors that matter for the apply/skip gate and the ATS pass:
- A keyword the candidate doesn't have lowers the score and flips the verdict.
- Plus-sign / hash-sign language names ("C++", "C#") match correctly, not
  partially against "C" (regression risk from the old `\\b` word boundary).
- ATS coverage uses synonym normalization so "tailwind" hits "tailwind css".
- Red-flag scan picks up rockstar/ninja AND the missing-salary signal.
- Auto-discovery falls back to role-config keywords when --critical is empty.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from lib.keyword_match import (  # noqa: E402
    compute_ats_coverage,
    compute_match_score,
    count_occurrences,
    has_keyword,
    scan_red_flags,
)


class KeywordMatchTests(unittest.TestCase):
    def test_verdict_flips_when_required_keyword_missing(self):
        text = "React, TypeScript, Node.js"
        score = compute_match_score(text, ["React", "Rust"], [])
        self.assertEqual(score.required_pct, 50)
        self.assertIn("SKIP", score.verdict)

    def test_preferred_only_uses_preferred_pct_as_overall(self):
        text = "React only"
        score = compute_match_score(text, [], ["React"])
        self.assertEqual(score.overall_pct, 100)
        self.assertIn("OVERQUALIFIED", score.verdict)

    def test_required_weights_more_than_preferred(self):
        text = "React, TypeScript"
        # Required 100%, preferred 0% — weighted 0.7*100 + 0.3*0 = 70
        score = compute_match_score(text, ["React"], ["Rust"])
        self.assertEqual(score.overall_pct, 70)
        self.assertIn("APPLY WITH STRONG COVER LETTER", score.verdict)


class KeywordBoundaryTests(unittest.TestCase):
    def test_c_plus_plus_does_not_match_c(self):
        # The pre-merge ats_check used \\b which broke around `+`; this is the
        # regression we explicitly fixed by switching to lookarounds on \\w.
        self.assertTrue(has_keyword("Built service in C++ and Rust", "C++"))
        self.assertEqual(count_occurrences("Built service in C and Rust", "C++"), 0)

    def test_c_sharp_matches(self):
        self.assertTrue(has_keyword(".NET and C# experience", "C#"))

    def test_keyword_does_not_match_inside_word(self):
        self.assertEqual(count_occurrences("javascripted", "java"), 0)


class RedFlagTests(unittest.TestCase):
    def test_culture_flag_detected(self):
        hits = scan_red_flags("We need a rockstar ninja engineer")
        self.assertIn("culture", hits)

    def test_missing_salary_range_flagged(self):
        hits = scan_red_flags("Great team, big mission, send your CV.")
        comp = [p for p, _ in hits.get("compensation", [])]
        self.assertIn("no salary range present", comp)

    def test_salary_range_present_suppresses_missing_flag(self):
        hits = scan_red_flags("Salary $80k-100k DOE")
        comp = [p for p, _ in hits.get("compensation", [])]
        self.assertNotIn("no salary range present", comp)


class AtsCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.resume = Path(self.tmp.name) / "resume.json"
        # Minimal resume.json that mentions react + tailwind css (canonical form).
        self.resume.write_text(
            json.dumps(
                {
                    "basics": {"summary": "Frontend dev using React and Tailwind CSS"},
                    "sections": {
                        "skills": {
                            "items": [
                                {"name": "Frontend", "keywords": ["React", "Tailwind CSS"]}
                            ]
                        }
                    },
                }
            )
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_supplied_critical_keywords_count_present(self):
        result = compute_ats_coverage(
            self.resume,
            jd_text="React role",
            critical=["React", "Vue"],
            threshold=50,
        )
        self.assertEqual(result.coverage_pct, 50)
        # Result entries appear in the order they were supplied.
        statuses = {r["keyword"]: r["present"] for r in result.results}
        self.assertTrue(statuses["React"])
        self.assertFalse(statuses["Vue"])

    def test_synonym_resolves_to_canonical_form(self):
        # Passing "tailwind" (synonym) should still find "tailwind css" in the resume.
        result = compute_ats_coverage(
            self.resume,
            jd_text="tailwind expert wanted",
            critical=["tailwind"],
            threshold=50,
        )
        self.assertTrue(result.results[0]["present"])

    def test_auto_discovery_when_no_critical_supplied(self):
        jd = "We use React heavily, plus Tailwind CSS and TypeScript every day."
        result = compute_ats_coverage(self.resume, jd_text=jd, threshold=50)
        self.assertEqual(result.critical_source, "auto-discovered from role-configs")
        keywords = {r["keyword"] for r in result.results}
        # role-configs.json maps react/typescript/tailwind css to Frontend.
        self.assertIn("react", keywords)


if __name__ == "__main__":
    unittest.main()
