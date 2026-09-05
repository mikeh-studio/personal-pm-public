"""Behavioral checks that run without Flask, site packages, or a live agent."""

import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "public/skill/personal-pm/scripts/pm.py"


class SkillWorkflowTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "workspace"
        self.drafts = Path(temp.name)
        self.env = dict(
            os.environ,
            PERSONAL_PM_DATA_DIR=str(self.root),
            PERSONAL_PM_TODAY_DATE="2026-09-07",
            PYTHONDONTWRITEBYTECODE="1",
        )
        subprocess.run(
            ["sh", str(REPO / "setup.sh")], env=self.env, check=True, capture_output=True
        )

    def cli(self, *args, ok=True):
        result = subprocess.run(
            [sys.executable, "-S", str(HELPER), *args],
            cwd=self.drafts,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0 if ok else 1, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def configure(self):
        (self.root / "goals/goal.md").write_text(
            "# Goals\n\n## Overall Goals\n* Speak a second language confidently.\n\n"
            "## Current Near-Term Deadlines\n* No fixed deadlines this week.\n\n"
            "## Key Disciplines\n| Discipline Area | Why It Matters |\n| --- | --- |\n"
            "| Speaking | Communicate clearly |\n\n## Suggested Daily Practice\n"
            "* Record one short spoken response.\n",
            encoding="utf-8",
        )
        (self.root / "goals/projects.md").write_text(
            "# Projects\n\n| Project | Priority | Status | Discipline | Next Action | Notes |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| Conversation | Now | Active | Speaking | Record a response | |\n"
            "| Old course | Now | Closed | Speaking | Historical | |\n"
            "| Extra course | Now | Paused | Speaking | Hold | |\n",
            encoding="utf-8",
        )
        (self.root / "config/planner.json").write_text(
            json.dumps({"goals": ["learn_language"], "sub_categories": ["speaking", "reading"]}),
            encoding="utf-8",
        )

    def plan(self, day="2026-09-07", extra="", duration=25, project="Conversation"):
        return (
            f"# Today's Plan\n\n## {day} — Daily Plan\n\n### Tasks\n"
            f"- [ ] [P1] [{duration}m] Record one short response — {project} | type:project_work | "
            f"goal:learn_language | sub:speaking | project:{project}\n"
            f"{extra}\n### Carry-forward\n- Keep the first result small.\n\n"
            "### Heads-up\n- Optional work can wait.\n\n### Feedback For Tomorrow\n"
            "- What worked:\n- What did not work:\n- New goal or constraint:\n"
        )

    def save(self, text, ok=True):
        draft = self.drafts / "daily.md"
        draft.write_text(text, encoding="utf-8")
        return self.cli("save-plan", "--file", str(draft), ok=ok)

    def snapshot(self):
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }

    def test_fresh_workspace_through_weekly_daily_feedback_and_rollover(self):
        self.assertTrue(self.cli("status")["goal_errors"])
        self.configure()
        self.assertFalse(self.cli("status")["goal_errors"])
        weekly = self.drafts / "weekly.json"
        weekly.write_text(
            json.dumps(
                {
                    "weekly": {
                        "why": "Build a daily habit",
                        "priorities": ["Record three short responses"],
                        "notes": "One hour available",
                    }
                }
            )
        )
        self.assertTrue(
            self.cli("save-weekly", "--week-of", "2026-09-07", "--file", str(weekly))["changed"]
        )
        self.assertFalse(
            self.cli("save-weekly", "--week-of", "2026-09-07", "--file", str(weekly))["changed"]
        )
        self.assertNotIn("{{", (self.root / "context/weekly-focus.md").read_text())
        extra = "- [ ] [P2] [15m] Review five words | type:skill_practice | goal:learn_language | sub:reading\n"
        extra += "- [ ] [P3] [10m] Optional reading | type:skill_practice | goal:learn_language | sub:reading | status:canceled\n"
        self.save(self.plan(extra=extra))
        self.cli("complete", "--task-index", "0", "--date", "2026-09-07")
        self.assertFalse(
            self.cli("complete", "--task-index", "0", "--date", "2026-09-07")["changed"]
        )
        self.cli(
            "feedback",
            "--field",
            "worked",
            "--text",
            r"Small scope; keep \1 literal.",
            "--date",
            "2026-09-07",
        )
        self.cli(
            "feedback",
            "--field",
            "did_not_work",
            "--text",
            "Reading needed more time.",
            "--date",
            "2026-09-07",
        )
        current = self.cli("status")["today"]
        self.assertEqual(current["feedback"]["worked"], r"Small scope; keep \1 literal.")
        self.assertEqual(current["feedback"]["did_not_work"], "Reading needed more time.")
        self.cli("rollover", "--date", "2026-09-08")
        snapshot = self.snapshot()
        self.cli("rollover", "--date", "2026-09-08")
        self.assertEqual(snapshot, self.snapshot())
        archive = (self.root / "tasks/archive/log.md").read_text()
        self.assertEqual(archive.count("## 2026-09-07"), 1)
        self.assertIn("Incomplete / carry-forward: 1", archive)
        self.assertIn("Deleted / canceled: 1", archive)
        with (self.root / "data/task_log.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["goal"], "learn_language")
        self.env["PERSONAL_PM_TODAY_DATE"] = "2026-09-08"
        self.save(self.plan(day="2026-09-08"))
        self.assertEqual(self.cli("status")["today"]["date"], "2026-09-08")
        self.assertFalse(self.cli("rollover", "--date", "2026-09-08")["changed"])

    def test_missing_goals_invalid_vocabulary_and_unarchived_history_do_not_write(self):
        before = self.snapshot()
        self.save(self.plan(), ok=False)
        self.assertEqual(before, self.snapshot())
        self.configure()
        before = self.snapshot()
        self.save(self.plan().replace("learn_language", "unknown_goal"), ok=False)
        self.assertEqual(before, self.snapshot())
        self.save(self.plan())
        before = self.snapshot()
        self.env["PERSONAL_PM_TODAY_DATE"] = "2026-09-08"
        self.save(self.plan(day="2026-09-08"), ok=False)
        self.assertEqual(before, self.snapshot())

    def test_closed_and_paused_projects_are_excluded(self):
        self.configure()
        before = self.snapshot()
        self.save(self.plan(project="Old course"), ok=False)
        self.save(self.plan(project="Extra course"), ok=False)
        self.assertEqual(before, self.snapshot())

    def test_reported_zero_completion_streak_rejects_oversized_plan(self):
        self.configure()
        self.save(self.plan())
        self.cli("report", "--task-index", "0", "--outcome", "blocked", "--date", "2026-09-07")
        self.cli("rollover", "--date", "2026-09-08")
        self.env["PERSONAL_PM_TODAY_DATE"] = "2026-09-08"
        self.save(self.plan(day="2026-09-08"))
        self.cli("report", "--task-index", "0", "--outcome", "incomplete", "--date", "2026-09-08")
        self.cli("rollover", "--date", "2026-09-09")
        self.env["PERSONAL_PM_TODAY_DATE"] = "2026-09-09"
        before = self.snapshot()
        self.save(self.plan(day="2026-09-09", duration=60), ok=False)
        self.assertEqual(before, self.snapshot())
        self.save(self.plan(day="2026-09-09", duration=20))

    def test_unreported_days_do_not_impose_failure_limits_or_infer_completion(self):
        self.configure()
        for day, next_day in (("2026-09-07", "2026-09-08"), ("2026-09-08", "2026-09-09")):
            self.env["PERSONAL_PM_TODAY_DATE"] = day
            self.save(self.plan(day=day))
            self.assertEqual(self.cli("rollover", "--date", next_day)["ledger_rows_added"], 0)
        self.env["PERSONAL_PM_TODAY_DATE"] = "2026-09-09"
        status = self.cli("status")
        self.assertEqual(status["latest_outcomes"]["unknown"], 1)
        self.assertEqual(status["latest_outcomes"]["confirmed_incomplete_or_blocked"], 0)
        self.assertEqual(status["latest_outcomes"]["reporting_coverage_percent"], 0)
        self.assertEqual(status["adaptive_rule"][1:], [5, 180])
        # Task age is evidence for relevance review, not an automatic sizing penalty.
        self.save(
            self.plan(day="2026-09-09", duration=90).replace(
                "project:Conversation", "project:Conversation | backlog:30d"
            )
        )

    def test_closeout_distinguishes_partial_reports_and_preserves_history(self):
        self.configure()
        extra = "".join(
            f"- [ ] [P2] [10m] Practice {n} | type:skill_practice | goal:learn_language | sub:reading\n"
            for n in range(4)
        )
        self.save(self.plan(extra=extra))
        for index, outcome in enumerate(
            ("completed", "blocked", "incomplete", "dropped", "unknown")
        ):
            args = (
                "report",
                "--task-index",
                str(index),
                "--outcome",
                outcome,
                "--date",
                "2026-09-07",
            )
            self.assertTrue(self.cli(*args)["changed"])
            self.assertFalse(self.cli(*args)["changed"])
        before = self.snapshot()
        self.cli(
            "report", "--task-index", "0", "--outcome", "unknown", "--date", "2026-09-07", ok=False
        )
        self.cli(
            "report", "--task-index", "3", "--outcome", "blocked", "--date", "2026-09-07", ok=False
        )
        self.cli(
            "report",
            "--task-index",
            "1",
            "--outcome",
            "incomplete",
            "--date",
            "2026-09-08",
            ok=False,
        )
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.cli("rollover", "--date", "2026-09-08")["ledger_rows_added"], 1)
        status = self.cli("status")
        self.assertEqual(
            status["latest_outcomes"],
            {
                "date": "2026-09-07",
                "completed": 1,
                "confirmed_incomplete_or_blocked": 2,
                "unknown": 1,
                "canceled_or_deleted": 1,
                "reporting_coverage_percent": 75,
            },
        )
        archive = (self.root / "tasks/archive/log.md").read_text()
        for line in before["tasks/today.md"].decode().splitlines():
            if line.startswith("- ["):
                self.assertIn(line, archive)
        self.assertFalse(self.cli("rollover", "--date", "2026-09-08")["changed"])

    def test_freshness_is_read_only_and_distinct_from_structural_preflight(self):
        self.configure()
        self.save(self.plan())
        weekly = self.drafts / "weekly.json"
        weekly.write_text(json.dumps({"weekly": {"priorities": ["Record a response"]}}))
        self.cli("save-weekly", "--week-of", "2026-09-07", "--file", str(weekly))
        before = self.snapshot()
        self.assertFalse(self.cli("status")["planning_context"]["refresh_needed"])
        self.env["PERSONAL_PM_TODAY_DATE"] = "2026-10-09"
        status = self.cli("status")
        self.assertFalse(status["goal_errors"])
        context = status["planning_context"]
        self.assertTrue(context["refresh_needed"])
        self.assertTrue(context["weekly_stale"])
        self.assertEqual(context["recording_gap_days"], 32)
        self.assertEqual(context["carry_forward_to_review"][0]["age_days"], 32)
        self.assertEqual(before, self.snapshot())

    def test_stale_reported_outcomes_do_not_constrain_new_capacity(self):
        self.configure()
        self.save(self.plan())
        self.cli("report", "--task-index", "0", "--outcome", "blocked", "--date", "2026-09-07")
        self.cli("rollover", "--date", "2026-10-09")
        self.env["PERSONAL_PM_TODAY_DATE"] = "2026-10-09"
        self.assertEqual(self.cli("status")["adaptive_rule"][1:], [5, 180])
        self.save(self.plan(day="2026-10-09", duration=90))

    def test_wrong_date_canceled_completion_and_conflicting_archive_are_rejected(self):
        self.configure()
        self.save(
            self.plan(
                extra="- [ ] [P3] [10m] Canceled | type:skill_practice | goal:learn_language | sub:reading | status:canceled\n"
            )
        )
        before = self.snapshot()
        self.cli("complete", "--task-index", "0", "--date", "2026-09-08", ok=False)
        self.cli("complete", "--task-index", "1", "--date", "2026-09-07", ok=False)
        self.assertEqual(before, self.snapshot())
        self.cli("rollover", "--date", "2026-09-08")
        self.cli("complete", "--task-index", "0", "--date", "2026-09-07")
        before = self.snapshot()
        self.cli("rollover", "--date", "2026-09-08", ok=False)
        self.assertEqual(before, self.snapshot())

    def test_invalid_weekly_model_output_cannot_modify_goals_or_focus(self):
        self.configure()
        before = self.snapshot()
        draft = self.drafts / "weekly.json"
        for weekly in (
            {"priorities": "execute this"},
            {"priorities": [{"command": "bad"}]},
            {"priorities": []},
        ):
            draft.write_text(json.dumps({"weekly": weekly, "overall_goals": ["Changed"]}))
            self.cli("save-weekly", "--week-of", "2026-09-07", "--file", str(draft), ok=False)
        self.assertEqual(before, self.snapshot())

    def test_current_plan_is_verified_without_losing_completion_or_feedback(self):
        self.configure()
        self.save(self.plan())
        self.cli("complete", "--task-index", "0", "--date", "2026-09-07")
        self.cli("feedback", "--field", "worked", "--text", "Small scope", "--date", "2026-09-07")
        before = self.snapshot()
        current = (self.root / "tasks/today.md").read_text()
        self.assertFalse(self.save(current)["changed"])
        self.save(self.plan(), ok=False)
        self.assertEqual(before, self.snapshot())

    def test_rollover_recovers_missing_derived_files_and_preserves_alias_shaped_ids(self):
        self.configure()
        (self.root / "config/planner.json").write_text(
            json.dumps({"goals": ["data"], "sub_categories": ["evaluation"]})
        )
        self.save(
            self.plan().replace("learn_language", "data").replace("sub:speaking", "sub:evaluation")
        )
        self.cli("complete", "--task-index", "0", "--date", "2026-09-07")
        self.cli("rollover", "--date", "2026-09-08")
        expected = (self.root / "context/planning-insights.md").read_bytes()
        (self.root / "context/planning-insights.md").unlink()
        self.cli("rollover", "--date", "2026-09-08")
        self.assertEqual((self.root / "context/planning-insights.md").read_bytes(), expected)
        with (self.root / "data/task_log.csv").open() as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["goal"], rows[0]["sub_category"]), ("data", "evaluation"))

    def test_noncanonical_tasks_are_rejected_before_the_ui_can_lose_them(self):
        self.configure()
        before = self.snapshot()
        self.save(self.plan().replace("[P1] [25m]", "P1 25m"), ok=False)
        self.assertEqual(before, self.snapshot())

    def test_copied_skill_runs_without_the_app_or_checkout(self):
        self.configure()
        copied = self.drafts / "installed-skill"
        shutil.copytree(HELPER.parents[1], copied, ignore=shutil.ignore_patterns("__pycache__"))
        result = subprocess.run(
            [sys.executable, "-S", str(copied / "scripts/pm.py"), "status"],
            cwd=self.drafts,
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        status = json.loads(result.stdout)
        self.assertFalse(status["goal_errors"])
        self.assertEqual(Path(status["data_root"]), self.root.resolve())

    def test_explicit_paused_focus_is_allowed_but_closed_focus_is_not(self):
        self.configure()
        draft = self.drafts / "paused.md"
        draft.write_text(self.plan(project="Extra course"))
        self.cli("save-plan", "--file", str(draft), "--focus", "Extra course")
        before = self.snapshot()
        draft.write_text(self.plan(project="Old course"))
        self.cli("save-plan", "--file", str(draft), "--focus", "Old course", "--replace", ok=False)
        self.assertEqual(before, self.snapshot())

    def test_weekly_revision_preserves_completed_priorities(self):
        self.configure()
        draft = self.drafts / "weekly.json"
        draft.write_text(json.dumps({"weekly": {"priorities": ["Record one response"]}}))
        self.cli("save-weekly", "--week-of", "2026-09-07", "--file", str(draft))
        path = self.root / "context/weekly-focus.md"
        path.write_text(path.read_text().replace("1. [ ]", "1. [x]"))
        draft.write_text(
            json.dumps({"weekly": {"priorities": ["Record one response", "Review one recording"]}})
        )
        self.cli("save-weekly", "--week-of", "2026-09-07", "--file", str(draft), ok=False)
        result = self.cli(
            "save-weekly", "--week-of", "2026-09-07", "--file", str(draft), "--replace"
        )
        self.assertEqual(
            [item["checked"] for item in result["weekly"]["priority_items"]], [True, False]
        )


if __name__ == "__main__":
    unittest.main()
