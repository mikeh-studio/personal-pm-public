import importlib.util
import json
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
SPEC = importlib.util.spec_from_file_location("pm_parser_analytics", MODULE_PATH)
pm_parser = importlib.util.module_from_spec(SPEC)
sys.modules["pm_parser_analytics"] = pm_parser
SPEC.loader.exec_module(pm_parser)


class AnalyticsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.previous_data_dir = os.environ.get("PERSONAL_PM_DATA_DIR")
        os.environ["PERSONAL_PM_DATA_DIR"] = self.tmp.name
        root = Path(self.tmp.name)
        (root / "tasks" / "archive").mkdir(parents=True)
        (root / "tasks").mkdir(exist_ok=True)
        (root / "data").mkdir(exist_ok=True)
        (root / "tasks" / "archive" / "log.md").write_text(
            """# Archive

## 2026-06-01

### Final Tasks
- [x] [P1] [30m] Done task | type:interview_prep | goal:data_owner | sub:decision_science

## 2026-06-02

### Final Tasks
- [ ] [P1] [30m] Missed task | type:project_work | goal:data_owner | sub:service_platform_eng

## 2026-06-03

### Final Tasks
- [x] [P1] [30m] Done again | type:project_work | goal:data_owner | sub:service_platform_eng
""",
            encoding="utf-8",
        )
        (root / "tasks" / "today.md").write_text(
            """# Today's Plan

## 2026-06-04 - Daily Plan

### Tasks
- [ ] [P1] [30m] Current anchor | type:interview_prep | goal:data_owner | sub:decision_science
- [x] [P2] [20m] Current support | type:project_work | goal:data_owner | sub:service_platform_eng
""",
            encoding="utf-8",
        )
        (root / "data" / "task_log.csv").write_text(
            "date,task_text,completed,priority,task_type,goal,sub_category,project,duration_minutes,source,source_date\n",
            encoding="utf-8",
        )
        run_records = [
            {
                "started_at": "2026-06-03T09:00:00+08:00",
                "ended_at": "2026-06-03T09:02:00+08:00",
                "run_id": "daily-autonomous-test",
                "mode": "daily_autonomous_local",
                "status": "success",
                "exit_code": 0,
                "focus": "Judgement",
                "actions": ["personal_pm_runner", "validate_today"],
                "errors": [],
            },
            {
                "started_at": "2026-06-04T10:00:00+08:00",
                "ended_at": "2026-06-04T10:02:00+08:00",
                "run_id": "browser-test",
                "mode": "browser_run_today",
                "status": "success",
                "exit_code": 0,
                "provider": "codex",
                "provider_label": "Codex",
                "run_type": "Normal planning",
                "focus": "Default",
                "actions": ["browser_run_today"],
                "errors": [],
                "token_usage": {"model_calls": 1, "total_tokens": 1234},
            },
        ]
        (root / "data" / "agent_runs.jsonl").write_text(
            "\n".join(json.dumps(record, sort_keys=True) for record in run_records) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        if self.previous_data_dir is None:
            os.environ.pop("PERSONAL_PM_DATA_DIR", None)
        else:
            os.environ["PERSONAL_PM_DATA_DIR"] = self.previous_data_dir

    def test_completion_streak_is_consecutive_from_latest_archive_day(self):
        stats = pm_parser.get_completion_streak()

        self.assertEqual(stats["completion_days"], 2)
        self.assertEqual(stats["streak"], 1)
        self.assertEqual(stats["last_completed"], "2026-06-03")

    def test_analytics_keeps_current_plan_separate_from_history(self):
        analytics = pm_parser.get_analytics_90d()

        self.assertEqual(len(analytics["days"]), 3)
        self.assertEqual(analytics["summary"]["total_completed"], 2)
        self.assertEqual(analytics["current_plan"]["date"], "2026-06-04")
        self.assertFalse(analytics["current_plan"]["included_in_history"])
        self.assertEqual(analytics["current_plan"]["planned"], 2)
        self.assertEqual(analytics["current_plan"]["completed"], 1)
        self.assertEqual(analytics["current_plan"]["planned_minutes"], 50)
        self.assertEqual(analytics["current_plan"]["completed_minutes"], 20)

    def test_analytics_includes_durable_planner_run_history(self):
        analytics = pm_parser.get_analytics_90d()
        run_history = analytics["run_history"]

        self.assertEqual(run_history["summary"]["total"], 2)
        self.assertEqual(run_history["summary"]["successful"], 2)
        self.assertEqual(run_history["summary"]["latest"]["run_id"], "browser-test")
        self.assertEqual(run_history["summary"]["latest"]["mode"], "browser_run_today")
        self.assertEqual(run_history["summary"]["latest"]["total_tokens"], 1234)


if __name__ == "__main__":
    unittest.main()
