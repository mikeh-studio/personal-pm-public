import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "github_sync.py"
SPEC = importlib.util.spec_from_file_location("github_sync", MODULE_PATH)
github_sync = importlib.util.module_from_spec(SPEC)
sys.modules["github_sync"] = github_sync
SPEC.loader.exec_module(github_sync)


class GithubSyncTests(unittest.TestCase):
    def make_data_root(self, today_text: str, projects_text: str = "") -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "goals").mkdir(parents=True)
        (root / "tasks").mkdir(parents=True)
        (root / "data").mkdir(parents=True)
        (root / "config").mkdir(parents=True)
        (root / "goals" / "projects.md").write_text(projects_text, encoding="utf-8")
        (root / "tasks" / "today.md").write_text(today_text, encoding="utf-8")
        return root

    def test_durable_task_policy_filters_noise_and_honors_overrides(self):
        today = """# Today's Plan

## 2026-06-18 - Daily Plan

### Tasks
- [ ] [P1] [50m] Build the anchor artifact - Data foundation | type:skill_practice | goal:data_owner | sub:data_foundation
- [ ] [P2] [30m] Ship a project slice - App | type:project_work | goal:data_owner | sub:service_platform_eng
- [ ] [P2] [30m] Carry a prior task - App | type:writing | goal:data_owner | sub:writing | backlog:3d
- [ ] [P3] [10m] Explicitly sync this task - Admin | type:career | goal:data_owner | sub:career_assets | sync:github
- [ ] [P3] [10m] Skip this project task - App | type:project_work | goal:data_owner | sub:service_platform_eng | sync:false
- [ ] [P2] [20m] Keep this local - Admin | type:career | goal:data_owner | sub:career_assets
"""
        data_root = self.make_data_root(today)

        _, tasks = github_sync.parse_today_tasks(data_root, "durable")
        titles = [task["title"] for task in tasks]

        self.assertEqual(
            titles,
            [
                "Build the anchor artifact - Data foundation",
                "Ship a project slice - App",
                "Carry a prior task - App",
                "Explicitly sync this task - Admin",
            ],
        )

    def test_dynamic_labels_and_truncated_titles_fit_github_limits(self):
        today = """# Today's Plan

## 2026-06-18 - Daily Plan

### Tasks
- [ ] [P1] [50m] This title is intentionally long enough to require truncation before it is sent to GitHub because concise issue titles are easier to scan in the private mirror - Data foundation | type:skill_practice | goal:data_owner | sub:an_extremely_long_sub_category_name_that_would_otherwise_exceed_github_label_limits
"""
        projects = """# Projects

| Project | Priority | Status | Discipline | Next Action | Notes |
| --- | --- | --- | --- | --- | --- |
| Long Label Project | Now | Active | Data foundation / service platform eng / evaluation | Ship one slice. | Keep moving. |
"""
        data_root = self.make_data_root(today, projects)

        records = github_sync.build_records(data_root, "all", "durable")
        labels = [label for record in records for label in record.labels]

        self.assertTrue(all(len(label) <= 50 for label in labels))
        self.assertTrue(all(len(record.title) <= 120 for record in records))

    def test_closed_project_is_open_mode_filtered_and_all_mode_closed(self):
        projects = """# Projects

| Project | Priority | Status | Discipline | Next Action | Notes |
| --- | --- | --- | --- | --- | --- |
| Active Build | Now | Active | Data foundation | Ship one slice. | Keep moving. |
| Closed Build | Later | Closed | Writing | Archive it. | Done. |
"""
        data_root = self.make_data_root("", projects)

        open_projects = github_sync.build_records(data_root, "open", "none")
        all_projects = github_sync.build_records(data_root, "all", "none")

        self.assertEqual([record.title for record in open_projects], ["Project: Active Build"])
        closed = [record for record in all_projects if record.sync_id == "project:closed-build"][0]
        self.assertEqual(closed.state, "closed")

    def test_sync_map_stays_under_data_root_by_default(self):
        data_root = self.make_data_root("")
        with patch.object(sys, "argv", ["github_sync.py", "--data-dir", str(data_root), "--json"]):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 0)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertEqual(
            payload["sync_map"],
            str((data_root / "data" / "github_sync_map.json").resolve()),
        )
        self.assertTrue(payload["dry_run"])

    def test_apply_requires_private_repo_target(self):
        data_root = self.make_data_root("")
        with patch.object(
            sys,
            "argv",
            ["github_sync.py", "--data-dir", str(data_root), "--apply", "--json"],
        ):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        self.assertIn("--repo is required with --apply", output)

    def test_public_repo_is_refused(self):
        class FakeClient:
            def repo_info(self, repo):
                return {"full_name": repo, "private": False}

        with self.assertRaises(github_sync.SyncError):
            github_sync.ensure_private_repo(FakeClient(), "owner/public-repo")

    def test_preflight_validates_private_targets_and_missing_project_fields(self):
        project = {
            "id": "PVT_1",
            "title": "Personal PM",
            "public": False,
            "fields": {
                "nodes": [
                    {"__typename": "ProjectV2Field", "id": "field-1", "name": "PM Status"},
                    {"__typename": "ProjectV2Field", "id": "field-2", "name": "Sync ID"},
                ]
            },
        }

        class FakeClient:
            def auth_status(self):
                return "Logged in"

            def repo_info(self, repo):
                return {"full_name": repo, "private": True, "has_issues": True}

            def graphql(self, query, variables=None):
                return {"data": {"user": {"projectV2": project}}}

        with patch.object(github_sync, "GhClient", return_value=FakeClient()):
            result, warnings, errors = github_sync.preflight_checks(
                records=[],
                repo="owner/private-repo",
                project_owner="owner",
                project_number=1,
                project_owner_type="user",
            )

        self.assertEqual(errors, [])
        self.assertEqual(result["auth"], "ok")
        self.assertTrue(result["repo"]["private"])
        self.assertIn("Project Priority", result["project"]["missing_recommended_fields"])
        self.assertTrue(any("field sync will be partial" in warning for warning in warnings))

    def test_preflight_refuses_public_project_without_override(self):
        project = {
            "id": "PVT_1",
            "title": "Public Project",
            "public": True,
            "fields": {"nodes": []},
        }

        class FakeClient:
            def auth_status(self):
                return "Logged in"

            def repo_info(self, repo):
                return {"full_name": repo, "private": True, "has_issues": True}

            def graphql(self, query, variables=None):
                return {"data": {"user": {"projectV2": project}}}

        with patch.object(github_sync, "GhClient", return_value=FakeClient()):
            _, _, errors = github_sync.preflight_checks(
                records=[],
                repo="owner/private-repo",
                project_owner="owner",
                project_number=1,
                project_owner_type="user",
            )

        self.assertTrue(any("public GitHub Project" in error for error in errors))

    def test_preflight_cli_does_not_require_apply_or_write_sync_map(self):
        data_root = self.make_data_root("")

        class FakeClient:
            def auth_status(self):
                return "Logged in"

        with patch.object(github_sync, "GhClient", return_value=FakeClient()):
            with patch.object(
                sys,
                "argv",
                ["github_sync.py", "--data-dir", str(data_root), "--preflight", "--json"],
            ):
                with patch("sys.stdout") as stdout:
                    result = github_sync.main()

        self.assertEqual(result, 0)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["preflight"]["auth"], "ok")
        self.assertFalse((data_root / "data" / "github_sync_map.json").exists())

    def test_private_config_can_set_sync_policy_and_map_path(self):
        today = """# Today's Plan

## 2026-06-18 - Daily Plan

### Tasks
- [ ] [P1] [50m] Sync by default - Data foundation | type:skill_practice | goal:data_owner | sub:data_foundation
- [ ] [P3] [10m] Sync only with all - Admin | type:career | goal:data_owner | sub:career_assets
"""
        data_root = self.make_data_root(today)
        (data_root / "config" / "github_sync.json").write_text(
            json.dumps({"tasks": "all", "projects": "none", "map_path": "data/custom_map.json"}),
            encoding="utf-8",
        )

        with patch.object(sys, "argv", ["github_sync.py", "--data-dir", str(data_root), "--json"]):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 0)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertEqual(payload["counts"], {"create": 2})
        self.assertEqual(payload["sync_map"], str((data_root / "data" / "custom_map.json").resolve()))

    def test_private_config_rejects_unknown_and_sensitive_keys(self):
        data_root = self.make_data_root("")
        (data_root / "config" / "github_sync.json").write_text(
            json.dumps({"repo": "owner/private-repo", "notes": "unused"}),
            encoding="utf-8",
        )

        with patch.object(sys, "argv", ["github_sync.py", "--data-dir", str(data_root), "--json"]):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertIn("Unsupported GitHub sync config key", payload["error"])

        (data_root / "config" / "github_sync.json").write_text(
            json.dumps({"repo": "owner/private-repo", "access_token": "do-not-store"}),
            encoding="utf-8",
        )
        with patch.object(sys, "argv", ["github_sync.py", "--data-dir", str(data_root), "--json"]):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertIn("is not allowed", payload["error"])

    def test_sync_map_path_must_stay_under_data_root(self):
        data_root = self.make_data_root("")
        (data_root / "config" / "github_sync.json").write_text(
            json.dumps({"map_path": "../github_sync_map.json"}),
            encoding="utf-8",
        )

        with patch.object(sys, "argv", ["github_sync.py", "--data-dir", str(data_root), "--json"]):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertIn("must stay under the active data root", payload["error"])

    def test_cli_overrides_private_config_policy(self):
        today = """# Today's Plan

## 2026-06-18 - Daily Plan

### Tasks
- [ ] [P1] [50m] Sync by default - Data foundation | type:skill_practice | goal:data_owner | sub:data_foundation
- [ ] [P3] [10m] Do not sync by default - Admin | type:career | goal:data_owner | sub:career_assets
"""
        data_root = self.make_data_root(today)
        (data_root / "config" / "github_sync.json").write_text(
            json.dumps({"tasks": "all", "projects": "none"}),
            encoding="utf-8",
        )

        with patch.object(
            sys,
            "argv",
            [
                "github_sync.py",
                "--data-dir",
                str(data_root),
                "--tasks",
                "durable",
                "--json",
            ],
        ):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 0)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertEqual(payload["counts"], {"create": 1})

    def test_config_supplies_preflight_repo_target(self):
        data_root = self.make_data_root("")
        (data_root / "config" / "github_sync.json").write_text(
            json.dumps({"repo": "owner/private-repo"}),
            encoding="utf-8",
        )

        class FakeClient:
            def auth_status(self):
                return "Logged in"

            def repo_info(self, repo):
                return {"full_name": repo, "private": True, "has_issues": True}

        with patch.object(github_sync, "GhClient", return_value=FakeClient()):
            with patch.object(
                sys,
                "argv",
                ["github_sync.py", "--data-dir", str(data_root), "--preflight", "--json"],
            ):
                with patch("sys.stdout") as stdout:
                    result = github_sync.main()

        self.assertEqual(result, 0)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertEqual(payload["preflight"]["repo"]["name"], "owner/private-repo")

    def test_explicit_missing_config_fails(self):
        data_root = self.make_data_root("")
        missing_config = data_root / "config" / "missing.json"

        with patch.object(
            sys,
            "argv",
            [
                "github_sync.py",
                "--data-dir",
                str(data_root),
                "--config",
                str(missing_config),
                "--json",
            ],
        ):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertIn("config not found", payload["error"])

    def test_init_config_writes_private_config_from_flags(self):
        data_root = self.make_data_root("")
        config_path = data_root / "config" / "github_sync.json"

        with patch.object(
            sys,
            "argv",
            [
                "github_sync.py",
                "--data-dir",
                str(data_root),
                "--repo",
                "owner/private-repo",
                "--project-owner",
                "owner",
                "--project-number",
                "3",
                "--tasks",
                "durable",
                "--projects",
                "open",
                "--init-config",
                "--json",
            ],
        ):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 0)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertEqual(payload["config"], str(config_path.resolve()))
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["repo"], "owner/private-repo")
        self.assertEqual(config["project_number"], 3)
        self.assertEqual(config["projects"], "open")
        self.assertNotIn("allow_public_repo", config)

    def test_cli_rejects_public_target_override_flags(self):
        data_root = self.make_data_root("")

        with patch.object(
            sys,
            "argv",
            [
                "github_sync.py",
                "--data-dir",
                str(data_root),
                "--allow-public-repo",
                "--json",
            ],
        ):
            with patch("sys.stderr"):
                with self.assertRaises(SystemExit) as exc:
                    github_sync.main()

        self.assertEqual(exc.exception.code, 2)

    def test_init_config_refuses_overwrite_without_flag(self):
        data_root = self.make_data_root("")
        config_path = data_root / "config" / "github_sync.json"
        config_path.write_text(json.dumps({"repo": "owner/old-private-repo"}), encoding="utf-8")

        with patch.object(
            sys,
            "argv",
            [
                "github_sync.py",
                "--data-dir",
                str(data_root),
                "--repo",
                "owner/new-private-repo",
                "--init-config",
                "--json",
            ],
        ):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertIn("already exists", payload["error"])
        config = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertEqual(config["repo"], "owner/old-private-repo")

    def test_init_config_requires_repo(self):
        data_root = self.make_data_root("")

        with patch.object(
            sys,
            "argv",
            ["github_sync.py", "--data-dir", str(data_root), "--init-config", "--json"],
        ):
            with patch("sys.stdout") as stdout:
                result = github_sync.main()

        self.assertEqual(result, 1)
        output = "".join(call.args[0] for call in stdout.write.call_args_list)
        payload = json.loads(output)
        self.assertIn("--repo is required", payload["error"])


if __name__ == "__main__":
    unittest.main()
