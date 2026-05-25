from flask import Flask, jsonify, request, send_from_directory
from pathlib import Path

import os
import shutil
import subprocess
import threading

from parser import (
    data_dir,
    parse_today,
    parse_goals,
    parse_projects,
    parse_weekly_focus,
    parse_daily_outcomes,
    parse_recent_drive_docs,
    toggle_task,
    update_feedback,
    get_completion_streak,
    get_analytics_90d,
    get_available_dates,
    parse_archive_day,
    add_task,
    delete_task,
    edit_task,
)

app = Flask(__name__, static_folder="static")

RUN_PROVIDERS = {
    "codex": {
        "label": "Codex",
        "env": "PERSONAL_PM_CODEX_BIN",
        "command": "codex",
    },
    "claude": {
        "label": "Claude Code",
        "env": "PERSONAL_PM_CLAUDE_BIN",
        "command": "claude",
    },
    "gemini": {
        "label": "Gemini CLI",
        "env": "PERSONAL_PM_GEMINI_BIN",
        "command": "gemini",
    },
}


def _resolve_bin(provider: dict) -> str:
    override = os.environ.get(provider["env"], "").strip()
    if override:
        return override

    command = shutil.which(provider["command"])
    if command:
        return command

    raise FileNotFoundError(f"{provider['label']} command not found. Set {provider['env']} to its executable path.")


def _run_prompt(provider_label: str) -> str:
    root = data_dir()
    return f"""Read public/skill/personal-pm/SKILL.md and AGENTS.md, then run normal planning for today's personal-pm workflow.

Runner: {provider_label}
Data root: {root}
Selected mode: Normal planning

Rules:
- Treat "Normal planning" as explicit launcher-provided input; do not ask the daily-start mode/focus questions.
- Resolve planner files relative to the configured data root, not hard-coded private/ paths.
- Keep public code/package files separate from planner data.
- Keep the workflow local-only. Do not call Google Drive, Google Docs, Google Sheets, or external mirror sync helpers.
- Do not update research or reading-list files unless the user explicitly requested research work.
- If the current plan belongs to a prior date, perform the normal rollover into the configured data root before writing the new day.
- Add compact `| type:... | goal:... | sub:...` metadata to every task line.
- For carried-forward tasks from prior runs, archive entries, or backlog items, add `| backlog:Nd` to show how many calendar days the task has remained available and unresolved.
- If a carried-forward `P1` or `P2` task has missed multiple runs and is still broad, rewrite it as a smaller actionable next step instead of repeating the broad block.
- If the current plan is already current and satisfies the workflow, prefer verify-only over a cosmetic rewrite.
- Keep the final response concise and operational.
"""


def _provider_command(provider_key: str, prompt: str, project_root: str) -> list[str]:
    provider = RUN_PROVIDERS[provider_key]
    executable = _resolve_bin(provider)

    if provider_key == "codex":
        return [executable, "exec", "--full-auto", "-C", project_root, prompt]
    if provider_key == "claude":
        return [executable, "-p", prompt, "--allowedTools", "Read,Write,Edit,Bash"]
    if provider_key == "gemini":
        return [executable, "--prompt", prompt, "--approval-mode", "yolo"]

    raise ValueError(f"Unsupported provider: {provider_key}")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/today")
def api_today():
    data = parse_today()
    return jsonify(data)


@app.route("/api/goals")
def api_goals():
    return jsonify(parse_goals())


@app.route("/api/projects")
def api_projects():
    return jsonify(parse_projects())


@app.route("/api/weekly-focus")
def api_weekly_focus():
    return jsonify(parse_weekly_focus())


@app.route("/api/outcomes")
def api_outcomes():
    return jsonify(parse_daily_outcomes())


@app.route("/api/recent-docs")
def api_recent_docs():
    return jsonify(parse_recent_drive_docs())


@app.route("/api/stats")
def api_stats():
    return jsonify(get_completion_streak())


@app.route("/api/analytics")
def api_analytics():
    return jsonify(get_analytics_90d())


@app.route("/api/available-dates")
def api_available_dates():
    return jsonify(get_available_dates())


@app.route("/api/archive/<date>")
def api_archive_day(date):
    data = parse_archive_day(date)
    if data is None:
        return jsonify(None), 404
    return jsonify(data)


@app.route("/api/workspace")
def api_workspace():
    return jsonify({"data_root": str(data_dir())})


_run_state = {"running": False, "log": "", "provider": "", "provider_label": ""}
_run_lock = threading.Lock()


@app.route("/api/run-today", methods=["POST"])
def api_run_today():
    body = request.get_json(silent=True) or {}
    provider_key = body.get("provider", "codex")
    if provider_key not in RUN_PROVIDERS:
        return jsonify({"ok": False, "error": f"Unsupported runner: {provider_key}"}), 400

    provider_label = RUN_PROVIDERS[provider_key]["label"]

    with _run_lock:
        if _run_state["running"]:
            return jsonify({"ok": False, "error": "Already running"}), 409
        _run_state["running"] = True
        _run_state["log"] = f"Starting PM flow with {provider_label}...\n"
        _run_state["provider"] = provider_key
        _run_state["provider_label"] = provider_label

    def _run():
        try:
            project_root = str(Path(__file__).resolve().parent.parent)
            env = dict(os.environ, PERSONAL_PM_DATA_DIR=str(data_dir()))
            prompt = _run_prompt(provider_label)
            command = _provider_command(provider_key, prompt, project_root)

            with _run_lock:
                _run_state["log"] += f"Data root: {data_dir()}\n"
                _run_state["log"] += f"Command: {Path(command[0]).name}\n\n"

            proc = subprocess.Popen(
                command,
                cwd=project_root,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            for line in proc.stdout or []:
                with _run_lock:
                    _run_state["log"] += line
            return_code = proc.wait(timeout=600)
            if return_code != 0:
                with _run_lock:
                    _run_state["log"] += f"\n{provider_label} exited with code {return_code}.\n"
        except subprocess.TimeoutExpired:
            proc.kill()
            with _run_lock:
                _run_state["log"] += f"\n{provider_label} timed out after 10 minutes and was stopped.\n"
        except Exception as e:
            with _run_lock:
                _run_state["log"] += f"\nError: {e}"
        finally:
            with _run_lock:
                _run_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True, "provider": provider_key, "provider_label": provider_label})


@app.route("/api/run-status")
def api_run_status():
    with _run_lock:
        return jsonify({
            "running": _run_state["running"],
            "log": _run_state["log"],
            "provider": _run_state["provider"],
            "provider_label": _run_state["provider_label"],
        })


@app.route("/api/toggle-task", methods=["POST"])
def api_toggle_task():
    body = request.get_json()
    idx = body.get("index", -1)
    ok = toggle_task(idx)
    return jsonify({"ok": ok, "today": parse_today()})


@app.route("/api/update-feedback", methods=["POST"])
def api_update_feedback():
    body = request.get_json()
    field = body.get("field", "")
    value = body.get("value", "")
    ok = update_feedback(field, value)
    return jsonify({"ok": ok, "today": parse_today()})


@app.route("/api/add-task", methods=["POST"])
def api_add_task():
    body = request.get_json()
    ok = add_task(
        priority=body.get("priority", 3),
        duration=body.get("duration", 30),
        title=body.get("title", ""),
        discipline=body.get("discipline", ""),
        meta=body.get("meta", {}),
    )
    return jsonify({"ok": ok, "today": parse_today()})


@app.route("/api/delete-task", methods=["POST"])
def api_delete_task():
    body = request.get_json()
    idx = body.get("index", -1)
    ok = delete_task(idx)
    return jsonify({"ok": ok, "today": parse_today()})


@app.route("/api/edit-task", methods=["POST"])
def api_edit_task():
    body = request.get_json()
    ok = edit_task(
        task_index=body.get("index", -1),
        priority=body.get("priority", 3),
        duration=body.get("duration", 30),
        title=body.get("title", ""),
        discipline=body.get("discipline", ""),
        meta=body.get("meta", {}),
    )
    return jsonify({"ok": ok, "today": parse_today()})


if __name__ == "__main__":
    port = int(os.environ.get("PERSONAL_PM_PORT", "5151"))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
