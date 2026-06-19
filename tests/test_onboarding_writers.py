import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = REPO_ROOT / "app"
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

MODULE_PATH = APP_ROOT / "parser.py"
SPEC = importlib.util.spec_from_file_location("pm_parser", MODULE_PATH)
pm_parser = importlib.util.module_from_spec(SPEC)
sys.modules["pm_parser"] = pm_parser
SPEC.loader.exec_module(pm_parser)


class OnboardingWriterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_data_dir = os.environ.get("PERSONAL_PM_DATA_DIR")
        os.environ["PERSONAL_PM_DATA_DIR"] = self.tmp.name
        self.root = Path(self.tmp.name)

    def tearDown(self):
        if self.previous_data_dir is None:
            os.environ.pop("PERSONAL_PM_DATA_DIR", None)
        else:
            os.environ["PERSONAL_PM_DATA_DIR"] = self.previous_data_dir

    def test_current_week_of_is_a_monday(self):
        from datetime import datetime

        week_of = pm_parser.current_week_of()
        self.assertRegex(week_of, r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(datetime.strptime(week_of, "%Y-%m-%d").weekday(), 0)

    def test_ensure_weekly_focus_file_creates_when_missing(self):
        path = pm_parser.ensure_weekly_focus_file()
        self.assertTrue(path.exists())
        self.assertIn("# Weekly Focus", path.read_text(encoding="utf-8"))
        # Idempotent: existing content is left alone.
        path.write_text("# Weekly Focus\n\n## Week of 2026-06-15\n1. [ ] Keep me.\n")
        pm_parser.ensure_weekly_focus_file()
        self.assertIn("Keep me.", path.read_text(encoding="utf-8"))

    def test_set_overall_goals_creates_file(self):
        ok, error = pm_parser.set_overall_goals(["Be a data owner", "* Ship a website"])
        self.assertTrue(ok, error)
        goals = pm_parser.parse_goals()
        self.assertEqual(goals["overall_goals"], ["Be a data owner", "Ship a website"])

    def test_set_overall_goals_replaces_section_and_preserves_others(self):
        (self.root / "goals").mkdir(parents=True)
        (self.root / "goals" / "goal.md").write_text(
            "## Overall Goals\n* Old goal\n\n## Current Near-Term Deadlines\n* Interview prep\n",
            encoding="utf-8",
        )
        ok, error = pm_parser.set_overall_goals(["New goal one", "New goal two"])
        self.assertTrue(ok, error)
        text = (self.root / "goals" / "goal.md").read_text(encoding="utf-8")
        self.assertIn("New goal one", text)
        self.assertNotIn("Old goal", text)
        # Other sections survive the rewrite.
        self.assertIn("## Current Near-Term Deadlines", text)
        self.assertIn("Interview prep", text)

    def test_set_overall_goals_rejects_empty(self):
        ok, error = pm_parser.set_overall_goals(["   ", ""])
        self.assertFalse(ok)
        self.assertTrue(error)


if __name__ == "__main__":
    unittest.main()
