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


class WeeklyFocusTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_data_dir = os.environ.get("PERSONAL_PM_DATA_DIR")
        os.environ["PERSONAL_PM_DATA_DIR"] = self.tmp.name
        root = Path(self.tmp.name)
        (root / "context").mkdir(parents=True)
        (root / "context" / "weekly-focus.md").write_text(
            """# Weekly Focus

<!-- template stays here -->

## Week of 2026-06-15

**Why this week:** Close the loop.

1. [ ] Ship the UI.
2. [x] Validate the backend.

### Notes

- Keep scope tight.
""",
            encoding="utf-8",
        )

    def tearDown(self):
        if self.previous_data_dir is None:
            os.environ.pop("PERSONAL_PM_DATA_DIR", None)
        else:
            os.environ["PERSONAL_PM_DATA_DIR"] = self.previous_data_dir

    def test_parse_weekly_focus_returns_latest_and_weeks(self):
        weekly = pm_parser.parse_weekly_focus()

        self.assertEqual(weekly["week_of"], "2026-06-15")
        self.assertEqual(weekly["priorities"], ["Ship the UI.", "Validate the backend."])
        self.assertTrue(weekly["priority_items"][1]["checked"])
        self.assertEqual(len(weekly["weeks"]), 1)

    def test_add_edit_delete_weekly_focus_preserves_header(self):
        ok, error = pm_parser.add_weekly_focus(
            "2026-06-22",
            why="Shift to project planning.",
            priorities=[{"text": "Pick one project.", "checked": False}],
            notes="Carry the smallest useful next step.",
        )
        self.assertTrue(ok, error)
        weekly = pm_parser.parse_weekly_focus()
        self.assertEqual(weekly["week_of"], "2026-06-22")
        self.assertEqual(len(weekly["weeks"]), 2)

        ok, error = pm_parser.edit_weekly_focus(
            weekly["index"],
            "2026-06-22",
            why="Rebalance around execution.",
            priorities=[{"text": "Pick one execution slice.", "checked": True}],
            notes="No broad planning.",
        )
        self.assertTrue(ok, error)
        weekly = pm_parser.parse_weekly_focus()
        self.assertEqual(weekly["why"], "Rebalance around execution.")
        self.assertTrue(weekly["priority_items"][0]["checked"])

        ok, error = pm_parser.delete_weekly_focus(weekly["index"])
        self.assertTrue(ok, error)
        weekly = pm_parser.parse_weekly_focus()
        self.assertEqual(weekly["week_of"], "2026-06-15")

        text = (Path(self.tmp.name) / "context" / "weekly-focus.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("<!-- template stays here -->", text)


if __name__ == "__main__":
    unittest.main()
