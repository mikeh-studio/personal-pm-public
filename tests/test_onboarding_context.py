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

MODULE_PATH = APP_ROOT / "onboarding.py"
SPEC = importlib.util.spec_from_file_location("pm_onboarding", MODULE_PATH)
pm_onboarding = importlib.util.module_from_spec(SPEC)
sys.modules["pm_onboarding"] = pm_onboarding
SPEC.loader.exec_module(pm_onboarding)


class OnboardingContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_data_dir = os.environ.get("PERSONAL_PM_DATA_DIR")
        os.environ["PERSONAL_PM_DATA_DIR"] = self.tmp.name
        self.root = Path(self.tmp.name)
        (self.root / "goals").mkdir(parents=True)
        (self.root / "context").mkdir(parents=True)
        (self.root / "goals" / "goal.md").write_text(
            "## Overall Goals\n* Build good systems\n\n## Key Disciplines\n| Discipline area | Details |\n| --- | --- |\n| Execution | Ship useful slices |\n",
            encoding="utf-8",
        )
        (self.root / "context" / "weekly-focus.md").write_text(
            "# Weekly Focus\n\n## Week of 2026-06-15\n1. [ ] Keep focus tight.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        if self.previous_data_dir is None:
            os.environ.pop("PERSONAL_PM_DATA_DIR", None)
        else:
            os.environ["PERSONAL_PM_DATA_DIR"] = self.previous_data_dir

    def test_planner_context_excludes_paused_and_closed_projects(self):
        (self.root / "goals" / "projects.md").write_text(
            """# Projects

| Project | Priority | Status | Discipline | Next Action | Notes |
| --- | --- | --- | --- | --- | --- |
| Active now | Now | Active | Execution | Ship a slice | Keep |
| Idea next | Next | Idea | Design | Pick a wedge | Keep |
| Paused now | Now | Paused | Research | Do not include | Hold |
| Closed now | Now | Closed | Ops | Do not include | Done |
""",
            encoding="utf-8",
        )

        context = pm_onboarding.build_planner_context()

        self.assertIn("Active now", context)
        self.assertIn("Idea next", context)
        self.assertNotIn("Paused now", context)
        self.assertNotIn("Closed now", context)


if __name__ == "__main__":
    unittest.main()
