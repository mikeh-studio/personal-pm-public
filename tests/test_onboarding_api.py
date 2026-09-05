import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
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
        token = self.client.get("/api/session").get_json()["csrf"]
        self.client.environ_base["HTTP_X_PM_CSRF"] = token

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

    def test_goal_context_is_validated_before_any_section_is_changed(self):
        root = Path(self.tmp.name)
        path = root / "goals/goal.md"
        path.parent.mkdir()
        original = (REPO_ROOT / "templates/goals/goal.md").read_text()
        path.write_text(original)
        for context in (
            {},
            {"deadlines": "No fixed deadlines"},
            {"disciplines": ["Invalid shape"]},
            {"unknown": "Unsupported field"},
        ):
            with self.subTest(context=context):
                response = self.client.post(
                    "/api/onboarding/goals", json={"goals": ["New goal"], "context": context}
                )
                self.assertEqual(response.status_code, 400)
                self.assertEqual(path.read_text(), original)

    def test_setup_only_collects_missing_context_and_preserves_saved_sections(self):
        path = Path(self.tmp.name) / "goals/goal.md"
        path.parent.mkdir()
        saved = "## Current Near-Term Deadlines\n* Review on Friday\n\n## Key Disciplines\n| Discipline Area | Why It Matters |\n| --- | --- |\n| Writing | Share useful ideas |\n\n## Personal Notes\nKeep this section verbatim.\n"
        path.write_text("## Overall Goals\n* Old goal\n\n" + saved)
        fields = self.client.get("/api/goals").get_json()["setup_fields"]
        self.assertEqual([field["key"] for field in fields], ["daily_practice"])
        response = self.client.post(
            "/api/onboarding/goals",
            json={
                "goals": ["Write clearly"],
                "context": {"daily_practice": "One paragraph in 15 minutes"},
            },
        )
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["goals"]["setup_fields"], [])
        self.assertIn(saved, path.read_text())

    def test_empty_workspace_exposes_all_missing_setup_fields(self):
        fields = self.client.get("/api/goals").get_json()["setup_fields"]
        self.assertEqual(
            [field["key"] for field in fields], ["deadlines", "disciplines", "daily_practice"]
        )

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

    def test_ui_reads_skill_artifacts_and_feedback_survives_headless_rollover(self):
        from pm_core import workflow
        from pm_core.weekly import save_weekly

        root = Path(self.tmp.name)
        (root / "goals").mkdir()
        (root / "goals/goal.md").write_text(
            "## Overall Goals\n* Learn Spanish\n\n## Current Near-Term Deadlines\n"
            "* No fixed deadlines\n\n## Key Disciplines\n* Speaking\n\n"
            "## Suggested Daily Practice\n* One recording\n",
            encoding="utf-8",
        )
        today = date.today()
        week = today - timedelta(days=today.weekday())
        weekly = {
            "weekly": {
                "why": "Small daily practice",
                "priorities": ["Record a short response"],
                "notes": "20 minutes",
            }
        }
        save_weekly(week.isoformat(), weekly)
        self.assertEqual(
            self.client.get("/api/weekly-focus").get_json()["priorities"],
            weekly["weekly"]["priorities"],
        )
        draft = root / "draft.md"
        draft.write_text(
            f"# Today's Plan\n\n## {today.isoformat()} — Daily Plan\n\n### Tasks\n"
            "- [ ] [P1] [20m] Record a response | type:skill_practice | goal:data_owner | sub:writing\n\n"
            "### Carry-forward\n\n### Heads-up\n\n### Feedback For Tomorrow\n"
            "- What worked:\n- What did not work:\n- New goal or constraint:\n",
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"PERSONAL_PM_TODAY_DATE": today.isoformat()}):
            workflow.save_plan(draft)
        self.assertEqual(
            self.client.get("/api/today").get_json()["tasks"][0]["title"], "Record a response"
        )
        self.client.post("/api/toggle-task", json={"index": 0})
        self.client.post(
            "/api/update-feedback", json={"field": "worked", "value": "Short first step"}
        )
        workflow.rollover((today + timedelta(days=1)).isoformat())
        archived = self.client.get(f"/api/archive/{today.isoformat()}").get_json()
        self.assertTrue(archived["tasks"][0]["checked"])
        outcomes = self.client.get("/api/outcomes").get_json()
        self.assertEqual(outcomes[-1]["completed"], ["Record a response"])
        self.assertIn("Short first step", (root / "tasks/archive/log.md").read_text())


if __name__ == "__main__":
    unittest.main()
