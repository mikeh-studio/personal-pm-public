import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import server as pm_server  # noqa: E402


class OnboardingApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_data_dir = os.environ.get("PERSONAL_PM_DATA_DIR")
        os.environ["PERSONAL_PM_DATA_DIR"] = self.tmp.name
        self.client = pm_server.app.test_client()

    def tearDown(self):
        if self.previous_data_dir is None:
            os.environ.pop("PERSONAL_PM_DATA_DIR", None)
        else:
            os.environ["PERSONAL_PM_DATA_DIR"] = self.previous_data_dir

    def test_questions_require_managed_goals_first(self):
        response = self.client.post("/api/onboarding/questions", json={"provider": "codex"})

        self.assertEqual(response.status_code, 409)
        self.assertIn("save at least one goal", response.get_json()["error"].lower())

    def test_goal_save_unlocks_weekly_questions(self):
        goal_response = self.client.post(
            "/api/onboarding/goals", json={"goals": ["Build trustworthy planning systems"]}
        )
        self.assertEqual(goal_response.status_code, 200)

        questions = [
            {"id": f"q{i}", "label": f"Question {i}", "help": "", "placeholder": ""}
            for i in range(1, 7)
        ]
        with patch.object(pm_server.onboarding, "generate_questions", return_value=questions):
            response = self.client.post("/api/onboarding/questions", json={"provider": "codex"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["questions"]), 6)

    def test_goal_save_rejects_more_than_twelve_items(self):
        response = self.client.post(
            "/api/onboarding/goals",
            json={"goals": [f"Goal {index}" for index in range(13)]},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("12 items or fewer", response.get_json()["error"])

    def test_generate_requires_four_answered_questions(self):
        self.client.post("/api/onboarding/goals", json={"goals": ["Build good systems"]})
        response = self.client.post(
            "/api/onboarding/generate",
            json={
                "provider": "codex",
                "answers": [
                    {"label": "One", "answer": "A"},
                    {"label": "Two", "answer": "B"},
                    {"label": "Three", "answer": "C"},
                ],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("at least four", response.get_json()["error"].lower())

    def test_generate_reports_missing_goals_before_incomplete_answers(self):
        response = self.client.post(
            "/api/onboarding/generate",
            json={
                "provider": "codex",
                "answers": [{"label": "One", "answer": "A"}],
            },
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("save at least one goal", response.get_json()["error"].lower())


if __name__ == "__main__":
    unittest.main()
