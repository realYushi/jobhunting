import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "json-resume-manager.py"
spec = importlib.util.spec_from_file_location("json_resume_manager", MODULE_PATH)
json_resume_manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(json_resume_manager)


class JsonResumeManagerTests(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]

    def create_resume(self, role, keywords):
        return json_resume_manager.create_resume(
            self.repo_root,
            "Acme",
            role=role,
            keywords=keywords,
        )

    def skill_group(self, resume, keyword):
        return [
            skill["name"]
            for skill in resume["sections"]["skills"]["items"]
            if keyword in skill.get("keywords", [])
        ]

    def test_frontend_role_sets_explicit_summary(self):
        resume = self.create_resume("frontend", [])
        self.assertIn("Frontend-focused product engineer", resume["summary"]["content"])

    def test_unmapped_keywords_are_not_dropped(self):
        resume = self.create_resume("frontend", ["Solidity"])
        self.assertEqual(self.skill_group(resume, "Solidity"), ["Frontend"])

    def test_mapped_keywords_land_in_expected_groups(self):
        resume = self.create_resume("frontend", ["FastAPI", "Kubernetes"])
        self.assertEqual(self.skill_group(resume, "FastAPI"), ["Backend"])
        self.assertEqual(self.skill_group(resume, "Kubernetes"), ["DevOps"])

    def test_devops_role_hides_interests(self):
        resume = self.create_resume("devops", [])
        self.assertTrue(resume["sections"]["interests"]["hidden"])

    def test_role_boosts_match_existing_skill_groups(self):
        resume = self.create_resume("backend", [])
        levels = {
            skill["name"]: skill["level"]
            for skill in resume["sections"]["skills"]["items"]
        }
        self.assertEqual(levels["Backend"], 5)
        self.assertEqual(levels["Database"], 5)


if __name__ == "__main__":
    unittest.main()
