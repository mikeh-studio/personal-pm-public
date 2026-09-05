"""Credential boundaries and real file behavior, with outbound provider calls replaced by fixtures."""

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "app"))
import server  # noqa: E402
from pm_core import api_planning, api_provider, connections  # noqa: E402

SECRET = "sk-synthetic-only-never-a-real-key"
DAY = "2026-09-07"


class ApiConnectionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.env = patch.dict(
            os.environ, {"PERSONAL_PM_DATA_DIR": str(self.root), "PERSONAL_PM_TODAY_DATE": DAY}
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        connections._MEMORY.clear()
        api_planning._DRAFTS.clear()
        self.client = server.app.test_client()
        self.token = self.client.get("/api/session").get_json()["csrf"]
        self.client.environ_base["HTTP_X_PM_CSRF"] = self.token
        (self.root / "goals").mkdir()
        (self.root / "goals/goal.md").write_text(
            "## Overall Goals\n* Learn data engineering\n\n## Current Near-Term Deadlines\n"
            "* None this week\n\n## Key Disciplines\n* Data foundation\n\n"
            "## Suggested Daily Practice\n* One small test\n"
        )

    def save(self, provider="openai", **overrides):
        body = {"model": "example-model", "storage": "memory", "api_key": SECRET, **overrides}
        return self.client.post(f"/api/connections/{provider}/save", json=body)

    def plan(self, task="Check a sample; done when one finding is recorded", day=DAY):
        return (
            f"# Today's Plan\n\n## {day} — Daily Plan\n\n### Tasks\n"
            f"- [ ] [P1] [20m] {task} | type:skill_practice | goal:data_owner | sub:data_foundation\n"
            "\n### Carry-forward\n\n### Heads-up\n- Time is unconfirmed.\n\n### Feedback For Tomorrow\n"
            "- What worked:\n- What did not work:\n- New goal or constraint:\n"
        )

    def snapshot(self):
        return {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }

    def result(self, markdown=None, questions=None):
        return {
            "summary": "One bounded next action.",
            "questions": questions or [],
            "plan_markdown": self.plan() if markdown is None else markdown,
        }

    def draft(self, result):
        with patch.object(api_provider, "generate_json", return_value=result):
            return self.client.post(
                "/api/plan/draft",
                json={"provider": "openai", "context": "Normal planning, 20 minutes."},
            )

    def test_session_origin_host_and_csrf_are_enforced(self):
        anonymous = server.app.test_client()
        self.assertEqual(anonymous.get("/api/connections").status_code, 403)
        self.assertEqual(
            self.client.post(
                "/api/connections/openai/save", json={}, headers={"Origin": "https://evil.example"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/connections/openai/save", json={}, headers={"X-PM-CSRF": "wrong"}
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.get("/api/session", headers={"Host": "evil.example"}).status_code, 403
        )
        self.assertEqual(
            self.client.get("/api/session", headers={"Origin": "null"}).status_code, 403
        )
        self.assertEqual(
            self.client.get("/api/session", headers={"Sec-Fetch-Site": "cross-site"}).status_code,
            403,
        )
        bootstrap = anonymous.get("/api/session")
        cookie = bootstrap.headers["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertEqual(bootstrap.headers["Cache-Control"], "no-store")
        self.assertEqual(
            self.client.post("/api/run-today", json={}, headers={"X-PM-CSRF": "wrong"}).status_code,
            403,
        )

    def test_temporary_key_never_reaches_files_or_settings_and_disconnect_forgets_it(self):
        self.assertEqual(self.save().status_code, 200)
        settings = self.client.get("/api/connections")
        self.assertNotIn(SECRET, settings.get_data(as_text=True))
        self.assertTrue(all(SECRET.encode() not in data for data in self.snapshot().values()))
        self.assertEqual(connections.credential("openai")[0], SECRET)
        self.assertEqual(
            self.client.post("/api/connections/openai/disconnect", json={}).status_code, 200
        )
        with self.assertRaises(ValueError):
            connections.credential("openai")

    def test_temporary_key_expiry_and_workspace_isolation(self):
        self.save()
        with patch.dict(os.environ, {"PERSONAL_PM_DATA_DIR": str(self.root / "other")}):
            with self.assertRaises(ValueError):
                connections.credential("openai")
        connections._MEMORY.clear()
        info = self.client.get("/api/connections").get_json()["connections"][0]
        self.assertFalse(info["available"])
        self.assertEqual(self.save(api_key="").status_code, 400)

    def test_environment_storage_and_invalid_settings_never_persist_a_key(self):
        before = self.snapshot()
        self.assertEqual(self.save(base_url="https://evil.example").status_code, 400)
        self.assertEqual(self.save(api_key="key\r\nInjected: header").status_code, 400)
        self.assertEqual(self.save(provider="unknown").status_code, 400)
        self.assertEqual(before, self.snapshot())
        with patch.dict(os.environ, {"OPENAI_API_KEY": SECRET}):
            self.assertEqual(self.save(storage="environment", api_key="").status_code, 200)
            self.assertEqual(connections.credential("openai")[0], SECRET)
            self.client.post("/api/connections/openai/disconnect", json={})
            self.assertEqual(os.environ["OPENAI_API_KEY"], SECRET)
        self.assertTrue(all(SECRET.encode() not in data for data in self.snapshot().values()))

    def test_keychain_uses_os_backend_without_plaintext_fallback(self):
        store = {}
        backend = MagicMock()
        backend.set_password.side_effect = lambda service, user, value: store.__setitem__(
            (service, user), value
        )
        backend.get_password.side_effect = lambda service, user: store.get((service, user))
        backend.delete_password.side_effect = lambda service, user: store.pop((service, user))
        with patch.object(connections, "_keychain", return_value=backend):
            self.assertEqual(self.save(storage="keychain").status_code, 200)
            self.assertEqual(connections.credential("openai")[0], SECRET)
            self.assertEqual(self.save(storage="memory").status_code, 200)
            self.assertFalse(store)
        before = self.snapshot()
        with patch.object(connections, "_keychain", side_effect=RuntimeError(SECRET)):
            response = self.save(storage="keychain")
            self.assertEqual(response.status_code, 400)
            self.assertNotIn(SECRET, response.get_data(as_text=True))
        self.assertEqual(before, self.snapshot())

    def test_provider_error_and_redirect_do_not_disclose_credentials(self):
        self.save()
        opener = MagicMock()
        opener.open.side_effect = HTTPError(
            "https://api.openai.com/v1/models", 401, SECRET, {}, io.BytesIO(SECRET.encode())
        )
        with patch.object(api_provider.request, "build_opener", return_value=opener):
            response = self.client.post("/api/connections/openai/test", json={})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(SECRET, response.get_data(as_text=True))
        with self.assertRaises(api_provider.ProviderError):
            api_provider.NoRedirect().redirect_request(
                None, None, 302, "", {}, "https://evil.example"
            )

    def test_openrouter_authentication_and_upstream_routing_are_explicit(self):
        self.assertEqual(self.save(provider="openrouter").status_code, 400)
        self.assertEqual(self.save(provider="openrouter", upstream="openai").status_code, 200)
        with patch.object(
            api_provider,
            "_request",
            side_effect=[{"data": {}}, {"data": [{"id": "example-model"}]}],
        ) as send:
            result = api_provider.test_connection("openrouter")
            self.assertTrue(result["authenticated"])
            self.assertEqual([call.args[1] for call in send.call_args_list], ["/key", "/models"])
        fixture = {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}],
            "usage": {"total_tokens": 10, "raw": SECRET},
        }
        with patch.object(api_provider, "_request", return_value=fixture) as send:
            api_provider.generate_json("openrouter", "Return JSON", "test")
            payload = send.call_args.args[3]
            self.assertEqual(payload["provider"]["only"], ["openai"])
            self.assertFalse(payload["provider"]["allow_fallbacks"])
            self.assertEqual(payload["provider"]["data_collection"], "deny")
            self.assertEqual(payload["max_tokens"], 4096)
        self.assertNotIn(SECRET, (self.root / "data/api_usage.jsonl").read_text())

    def test_supported_adapters_use_fixed_hosts_and_bounded_payloads(self):
        fixture = {"choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        for key in ("openai", "xai", "sakana"):
            with self.subTest(provider=key):
                self.assertEqual(self.save(provider=key).status_code, 200)
                opener = MagicMock()
                opener.open.return_value.__enter__.return_value.read.return_value = json.dumps(
                    fixture
                ).encode()
                with patch.object(api_provider.request, "build_opener", return_value=opener):
                    self.assertTrue(api_provider.generate_json(key, "Return JSON", "test")["ok"])
                req = opener.open.call_args.args[0]
                self.assertEqual(
                    req.full_url, connections.PROVIDERS[key]["base_url"] + "/chat/completions"
                )
                payload = json.loads(req.data)
                self.assertEqual(
                    payload.get("max_completion_tokens", payload.get("max_tokens")), 4096
                )
                self.assertNotIn("tools", payload)
                self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_headless_connections_need_no_ui_or_secret_arguments(self):
        command = [
            sys.executable,
            "-S",
            str(REPO / "public/skill/personal-pm/scripts/pm.py"),
            "--data-dir",
            str(self.root),
        ]
        with patch.dict(os.environ, {"OPENAI_API_KEY": SECRET}):
            result = subprocess.run(
                command
                + [
                    "connect",
                    "--provider",
                    "openai",
                    "--model",
                    "example-model",
                    "--storage",
                    "environment",
                ],
                capture_output=True,
                text=True,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        listed = subprocess.run(command + ["connections"], capture_output=True, text=True)
        self.assertEqual(listed.returncode, 0, listed.stderr)
        self.assertNotIn(SECRET, listed.stdout + result.stdout)
        self.assertNotIn(SECRET, json.dumps(self.snapshot(), default=str))
        prompt = subprocess.run(
            command + ["connect", "--provider", "xai", "--model", "example-model"],
            input="",
            capture_output=True,
            text=True,
        )
        self.assertEqual(prompt.returncode, 1)
        self.assertIn("interactive terminal", prompt.stdout)

    def test_truncated_tool_and_non_json_responses_are_rejected(self):
        self.save()
        fixtures = [
            {"finish_reason": "length", "message": {"content": "{}"}},
            {"finish_reason": "stop", "message": {"content": "[]"}},
            {"finish_reason": "stop", "message": {"content": "{}", "tool_calls": [{}]}},
            {"finish_reason": "stop", "message": {"content": "run this command"}},
        ]
        before = self.snapshot()
        for choice in fixtures:
            with patch.object(api_provider, "_request", return_value={"choices": [choice]}):
                with self.assertRaises(api_provider.ProviderError):
                    api_provider.generate_json("openai", "Return JSON", "test")
        self.assertEqual(before, self.snapshot())

    def test_questions_do_not_modify_planner_files(self):
        before = self.snapshot()
        response = self.draft(self.result(markdown="", questions=["Which outcome still matters?"]))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("draft_id", response.get_json())
        self.assertEqual(before, self.snapshot())

    def test_daily_plan_is_reviewed_before_apply_and_same_day_state_is_preserved(self):
        before = self.snapshot()
        response = self.draft(self.result())
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(before, self.snapshot())
        token = response.get_json()["draft_id"]
        result = self.client.post("/api/plan/apply", json={"draft_id": token})
        self.assertEqual(result.status_code, 200, result.get_json())
        self.assertEqual((self.root / "tasks/today.md").read_text(), self.plan())
        self.assertEqual(
            self.client.post("/api/plan/apply", json={"draft_id": token}).status_code, 400
        )

    def test_stale_and_invalid_drafts_cannot_write(self):
        before = self.snapshot()
        invalid = self.draft(
            self.result(markdown=self.plan().replace("goal:data_owner", "goal:unknown"))
        )
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(before, self.snapshot())
        token = self.draft(self.result()).get_json()["draft_id"]
        (self.root / "goals/goal.md").write_text(
            (self.root / "goals/goal.md").read_text() + "\nNew constraint.\n"
        )
        before = self.snapshot()
        self.assertEqual(
            self.client.post("/api/plan/apply", json={"draft_id": token}).status_code, 400
        )
        self.assertEqual(before, self.snapshot())

    def test_apply_rolls_over_prior_day_once_and_preserves_unknown_outcomes(self):
        (self.root / "tasks").mkdir()
        (self.root / "tasks/today.md").write_text(self.plan(day="2026-09-06"))
        token = self.draft(self.result()).get_json()["draft_id"]
        self.assertFalse((self.root / "tasks/archive/log.md").exists())
        applied = self.client.post("/api/plan/apply", json={"draft_id": token})
        self.assertEqual(applied.status_code, 200, applied.get_json())
        archive = (self.root / "tasks/archive/log.md").read_text()
        self.assertEqual(archive.count("## 2026-09-06"), 1)
        self.assertIn("- [ ] [P1]", archive)
        with (self.root / "data/task_log.csv").open() as ledger:
            self.assertEqual(list(csv.DictReader(ledger)), [])

    def test_model_cannot_erase_completion_or_feedback(self):
        (self.root / "tasks").mkdir()
        current = (
            self.plan()
            .replace("- [ ]", "- [x]")
            .replace("- What worked:", "- What worked: Short scope")
        )
        (self.root / "tasks/today.md").write_text(current)
        before = self.snapshot()
        self.assertEqual(self.draft(self.result()).status_code, 400)
        self.assertEqual(before, self.snapshot())

    def test_feedback_must_survive_in_its_original_field(self):
        (self.root / "tasks").mkdir()
        current = self.plan().replace("- What worked:", "- What worked: Short scope")
        (self.root / "tasks/today.md").write_text(current)
        before = self.snapshot()
        for draft in (
            self.plan().replace("- Time is unconfirmed.", "- Short scope"),
            self.plan().replace("- What did not work:", "- What did not work: Short scope"),
        ):
            with self.subTest(draft=draft):
                response = self.draft(self.result(markdown=draft))
                self.assertEqual(response.status_code, 400)
                self.assertIn("feedback", response.get_json()["error"])
                self.assertEqual(before, self.snapshot())
        token = self.draft(self.result(markdown=current)).get_json()["draft_id"]
        self.assertEqual(
            self.client.post("/api/plan/apply", json={"draft_id": token}).status_code, 200
        )
        self.assertEqual(
            self.client.get("/api/today").get_json()["feedback"]["worked"], "Short scope"
        )

    def test_completed_work_cannot_be_moved_out_of_the_tasks_section(self):
        (self.root / "tasks").mkdir()
        current = self.plan().replace("- [ ]", "- [x]")
        (self.root / "tasks/today.md").write_text(current)
        completed = next(line for line in current.splitlines() if line.startswith("- [x]"))
        draft = self.plan(task="A new next action").replace("- Time is unconfirmed.", completed)
        before = self.snapshot()
        self.assertEqual(self.draft(self.result(markdown=draft)).status_code, 400)
        self.assertEqual(before, self.snapshot())

    def test_draft_uses_post_rollover_limits_without_writing_history(self):
        (self.root / "tasks").mkdir()
        previous = self.plan(day="2026-09-06").replace(
            "sub:data_foundation", "sub:data_foundation | outcome:incomplete"
        )
        (self.root / "tasks/today.md").write_text(previous)
        tasks = "\n".join(
            f"- [ ] [P{1 if i == 0 else 2}] [30m] Sample action {i} | type:skill_practice | goal:data_owner | sub:data_foundation"
            for i in range(5)
        )
        line = next(line for line in self.plan().splitlines() if line.startswith("- [ ]"))
        oversized = self.plan().replace(line, tasks)
        before = self.snapshot()
        with patch.object(
            api_provider, "generate_json", return_value=self.result(markdown=oversized)
        ) as model:
            response = self.client.post(
                "/api/plan/draft", json={"provider": "openai", "context": "150 minutes"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("at most 4", model.call_args.args[1])
        self.assertIn("at most 4", response.get_json()["error"])
        self.assertEqual(before, self.snapshot())
        token = self.draft(self.result()).get_json()["draft_id"]
        self.assertEqual(before, self.snapshot())
        applied = self.client.post("/api/plan/apply", json={"draft_id": token})
        self.assertEqual(applied.status_code, 200, applied.get_json())
        self.assertEqual(self.client.get("/api/today").get_json()["date"], DAY)
        self.assertEqual((self.root / "tasks/archive/log.md").read_text().count("## 2026-09-06"), 1)

    def test_fresh_onboarding_unlocks_daily_drafting_and_apply(self):
        shutil.copytree(REPO / "templates", self.root, dirs_exist_ok=True)
        starter = self.root / "tasks/today.md"
        starter.write_text(starter.read_text().replace("{{YYYY-MM-DD}}", "2026-09-06"))
        fields = self.client.get("/api/goals").get_json()["setup_fields"]
        self.assertEqual(
            {field["key"] for field in fields}, {"deadlines", "disciplines", "daily_practice"}
        )
        saved = self.client.post(
            "/api/onboarding/goals",
            json={
                "goals": ["Learn data engineering"],
                "context": {
                    "deadlines": "No fixed deadlines",
                    "disciplines": "Data engineering — Build reliable reports",
                    "daily_practice": "One small query in 20 minutes",
                },
            },
        )
        self.assertEqual(saved.status_code, 200, saved.get_json())
        self.assertEqual(saved.get_json()["goals"]["setup_fields"], [])
        weekly = {
            "weekly": {
                "why": "Practice",
                "priorities": ["Run one small query"],
                "notes": "20 minutes daily",
            }
        }
        with patch.object(api_provider, "generate_json", return_value=weekly):
            response = self.client.post(
                "/api/onboarding/generate",
                json={
                    "provider": "api:openai",
                    "answers": [{"label": str(i), "answer": "Specific answer"} for i in range(4)],
                },
            )
        self.assertEqual(response.status_code, 200, response.get_json())
        draft = self.draft(self.result())
        self.assertEqual(draft.status_code, 200, draft.get_json())
        applied = self.client.post(
            "/api/plan/apply", json={"draft_id": draft.get_json()["draft_id"]}
        )
        self.assertEqual(applied.status_code, 200, applied.get_json())
        self.assertEqual(self.client.get("/api/today").get_json()["date"], DAY)
        self.assertNotIn("2026-09-06", (self.root / "tasks/archive/log.md").read_text())

    def test_weekly_api_uses_shared_contract_and_never_starts_cli(self):
        self.save()
        payload = {"questions": [{"id": f"q{i}", "label": f"Question {i}"} for i in range(6)]}
        with (
            patch.object(api_provider, "generate_json", return_value=payload) as model,
            patch.object(server.onboarding, "_resolve_bin") as cli,
        ):
            response = self.client.post(
                "/api/onboarding/questions", json={"provider": "api:openai"}
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn("weekly planning contract", model.call_args.args[1])
            cli.assert_not_called()
        before = self.snapshot()
        with patch.object(
            api_provider, "generate_json", return_value={"weekly": {"priorities": "execute code"}}
        ):
            response = self.client.post(
                "/api/onboarding/generate",
                json={
                    "provider": "api:openai",
                    "answers": [{"label": str(i), "answer": "Specific answer"} for i in range(4)],
                },
            )
            self.assertEqual(response.status_code, 502)
        self.assertEqual(before, self.snapshot())

    def test_ui_does_not_load_third_party_scripts(self):
        from html.parser import HTMLParser

        scripts = []

        class Sources(HTMLParser):
            def handle_starttag(self, tag, attrs):
                if tag == "script":
                    scripts.extend(value for key, value in attrs if key == "src")

        with self.client.get("/") as response:
            Sources().feed(response.get_data(as_text=True))
        self.assertTrue(scripts)
        self.assertTrue(all(source.startswith("/static/") for source in scripts))


if __name__ == "__main__":
    unittest.main()
