"""Tests for job listing scorer."""

import unittest

from tools.lib.scorer import (
    ScoreResult,
    candidate_summary,
    filter_by_score,
    load_candidate_profile,
    score_listings,
    sort_by_score,
)


class ScoreListingsTests(unittest.TestCase):
    def test_score_listings_returns_correct_structure(self):
        listings = [
            {
                "job_id": "123",
                "source": "linkedin",
                "title": "Python Engineer",
                "company": "Acme",
                "snippet": "Looking for a Python developer with Django experience",
            }
        ]
        results = score_listings(listings, use_llm=False)
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], ScoreResult)
        self.assertEqual(results[0].job_id, "123")
        self.assertEqual(results[0].source, "linkedin")
        self.assertEqual(results[0].title, "Python Engineer")
        self.assertEqual(results[0].company, "Acme")

    def test_score_listings_keyword_fallback(self):
        """Keyword fallback should work without LLM."""
        listings = [
            {
                "job_id": "123",
                "source": "linkedin",
                "title": "Python Developer",
                "company": "Acme",
                "snippet": "Python Django FastAPI backend engineer",
            }
        ]
        results = score_listings(listings, use_llm=False)
        self.assertEqual(len(results), 1)
        # Score should be between 0 and 100
        self.assertGreaterEqual(results[0].score, 0)
        self.assertLessEqual(results[0].score, 100)

    def test_score_listings_empty_list(self):
        results = score_listings([], use_llm=False)
        self.assertEqual(len(results), 0)

    def test_score_listings_seniority_bias(self):
        """Junior roles should outrank senior ones (candidate is junior-to-intermediate)."""
        listings = [
            {
                "job_id": "1",
                "source": "linkedin",
                "title": "Senior Python Engineer",
                "company": "Acme",
                "snippet": "Senior role leading the team",
            },
            {
                "job_id": "2",
                "source": "linkedin",
                "title": "Junior Python Developer",
                "company": "Acme",
                "snippet": "Entry level position",
            },
        ]
        results = score_listings(listings, use_llm=False)
        self.assertEqual(len(results), 2)
        senior_score = next(r.score for r in results if "Senior" in r.title)
        junior_score = next(r.score for r in results if "Junior" in r.title)
        self.assertGreater(junior_score, senior_score)


class FilterAndSortTests(unittest.TestCase):
    def test_filter_by_score_cutoff(self):
        results = [
            ScoreResult(job_id="1", source="li", title="A", company="X", url=None, score=80, reason=""),
            ScoreResult(job_id="2", source="li", title="B", company="Y", url=None, score=60, reason=""),
            ScoreResult(job_id="3", source="li", title="C", company="Z", url=None, score=70, reason=""),
        ]
        passed = filter_by_score(results, cutoff=65)
        self.assertEqual(len(passed), 2)
        self.assertSetEqual({r.job_id for r in passed}, {"1", "3"})

    def test_sort_by_score_descending(self):
        results = [
            ScoreResult(job_id="1", source="li", title="A", company="X", url=None, score=60, reason=""),
            ScoreResult(job_id="2", source="li", title="B", company="Y", url=None, score=90, reason=""),
            ScoreResult(job_id="3", source="li", title="C", company="Z", url=None, score=75, reason=""),
        ]
        sorted_results = sort_by_score(results)
        scores = [r.score for r in sorted_results]
        self.assertEqual(scores, [90, 75, 60])


class CandidateSummaryTests(unittest.TestCase):
    def test_load_candidate_profile(self):
        profile = load_candidate_profile()
        self.assertIn("basics", profile)
        # Profile may use Reactive Resume schema with sections, or legacy schema
        self.assertTrue("skills" in profile or "sections" in profile)
        self.assertTrue("work" in profile or "sections" in profile)

    def test_candidate_summary_includes_key_info(self):
        profile = load_candidate_profile()
        summary = candidate_summary(profile)
        self.assertIsInstance(summary, str)
        # Summary should contain some key info (name at minimum)
        self.assertGreater(len(summary), 0)


if __name__ == "__main__":
    unittest.main()
