import json
import os
import shutil
import subprocess
import threading
import uuid
from datetime import date, datetime
from pathlib import Path

import onboarding
from flask import Flask, jsonify, request, send_from_directory
from parser import (
    add_project,
    add_task,
    add_weekly_focus,
    current_week_of,
    delete_project,
    delete_task,
    delete_weekly_focus,
    edit_project,
    edit_task,
    edit_weekly_focus,
    get_analytics_90d,
    get_available_dates,
    get_completion_streak,
    parse_archive_day,
    parse_daily_outcomes,
    parse_goals,
    parse_projects,
    parse_recent_drive_docs,
    parse_today,
    parse_weekly_focus,
    project_daily_flow_partition,
    toggle_task,
    update_feedback,
)
from paths import data_dir
from token_usage import (
    append_jsonl,
    codex_display_lines,
    codex_token_record,
    model_from_event,
    parse_json_event,
    summarize_records,
    token_summary_line,
    token_usage_log_path,
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

RUN_FOCUS_OPTIONS = {
    "Default",
    "Judgement",
    "Data foundation",
    "Decision science",
    "Evaluation discipline",
    "Service / platform engineering",
    "Physical AI",
    "Experience Design",
}

AUTONOMOUS_RUN_MODES = {"daily_autonomous", "daily_autonomous_local"}


def _resolve_bin(provider: dict) -> str:
    override = os.environ.get(provider["env"], "").strip()
    if override:
        return override

    command = shutil.which(provider["command"])
    if command:
        return command

    raise FileNotFoundError(
        f"{provider['label']} command not found. Set {provider['env']} to its executable path."
    )


def _provider_model_hint(provider_key: str) -> str:
    provider_env = f"PERSONAL_PM_{provider_key.upper()}_MODEL_HINT"
    return (
        os.environ.get(provider_env, "").strip()
        or os.environ.get("PERSONAL_PM_MODEL_HINT", "").strip()
    )


def _clean_run_focus(value: str) -> str:
    focus = " ".join(str(value or "").split())
    if len(focus) > 80:
        raise ValueError("Focus must be 80 characters or fewer.")
    return focus


def _run_selection(body: dict) -> dict:
    mode = str(body.get("mode", "normal")).strip().lower()
    if mode not in {"normal", "focus"}:
        raise ValueError(f"Unsupported run type: {mode}")

    if mode == "normal":
        return {
            "mode": "normal",
            "focus": "",
            "label": "Normal planning",
            "prompt_mode": "Normal planning",
        }

    focus = _clean_run_focus(body.get("focus", "Default")) or "Default"
    focus_note = "" if focus in RUN_FOCUS_OPTIONS else "\nCustom focus: yes"
    return {
        "mode": "focus",
        "focus": focus,
        "label": f"Specific focus: {focus}",
        "prompt_mode": f"Specific focus\nSelected focus: {focus}{focus_note}",
    }


def _run_prompt(provider_label: str, selection: dict) -> str:
    root = data_dir()
    selected_label = selection["label"]
    project_partition = project_daily_flow_partition()
    eligible_project_names = [p["name"] for p in project_partition["eligible"]]
    paused_project_names = [p["name"] for p in project_partition["paused"]]
    closed_project_names = [p["name"] for p in project_partition["closed"]]
    eligible_projects = ", ".join(eligible_project_names) or "none"
    paused_projects = ", ".join(paused_project_names) or "none"
    closed_projects = ", ".join(closed_project_names) or "none"
    if selection["mode"] == "normal":
        focus_rule = (
            '- Treat "Normal planning" as explicit launcher-provided input; do not ask '
            "the daily-start mode/focus questions."
        )
    else:
        focus_rule = (
            f'- Treat "{selected_label}" as explicit launcher-provided input; do not ask '
            "the daily-start mode/focus questions.\n"
            f"- Bias today toward the selected focus area: {selection['focus']}."
        )

    rules = "\n".join(
        [
            focus_rule,
            "- Resolve planner files relative to the configured data root, not "
            "hard-coded private/ paths.",
            "- Keep public code/package files separate from planner data.",
            "- Treat `goals/projects.md` rows with `Status` = `Paused` or `Closed` as "
            "ineligible for daily-flow generation unless the selected focus explicitly "
            "names that project. Do not create, carry forward, or justify daily tasks "
            "from paused or closed projects by default.",
            "- Paused and closed projects are also ineligible when selecting recent-doc "
            "tasks; a document matched only to paused or closed projects is not a "
            "project-work reason for today's plan.",
            "- Keep the workflow local-only. Do not call Google Drive, Google Docs, "
            "Google Sheets, or external mirror sync helpers.",
            "- Do not update research or reading-list files unless the user explicitly "
            "requested research work.",
            "- If the current plan belongs to a prior date, perform the normal rollover "
            "into the configured data root before writing the new day.",
            "- Add compact `| type:... | goal:... | sub:...` metadata to every task line.",
            "- For carried-forward tasks from prior runs, archive entries, or backlog "
            "items, add `| backlog:Nd` to show how many calendar days the task has "
            "remained available and unresolved.",
            "- If a carried-forward `P1` or `P2` task has missed multiple runs and is "
            "still broad, rewrite it as a smaller actionable next step instead of "
            "repeating the broad block.",
            "- If the current plan is already current and satisfies the workflow, "
            "prefer verify-only over a cosmetic rewrite.",
            "- Keep the final response concise and operational.",
        ]
    )

    return (
        "Read public/skill/personal-pm/SKILL.md and AGENTS.md, then run today's "
        "personal-pm workflow using the selected launcher mode.\n\n"
        f"Runner: {provider_label}\n"
        f"Data root: {root}\n"
        f"Selected mode: {selection['prompt_mode']}\n"
        f"Daily-flow eligible projects: {eligible_projects}\n"
        f"Paused projects excluded unless explicitly selected: {paused_projects}\n"
        f"Closed projects excluded from daily flow: {closed_projects}\n\n"
        f"Rules:\n{rules}\n"
    )


def _provider_command(provider_key: str, prompt: str, project_root: str) -> list[str]:
    provider = RUN_PROVIDERS[provider_key]
    executable = _resolve_bin(provider)

    if provider_key == "codex":
        return [executable, "exec", "--full-auto", "--json", "-C", project_root, prompt]
    if provider_key == "claude":
        return [executable, "-p", prompt, "--allowedTools", "Read,Write,Edit,Bash"]
    if provider_key == "gemini":
        return [executable, "--prompt", prompt, "--approval-mode", "yolo"]

    raise ValueError(f"Unsupported provider: {provider_key}")


def _run_log_path() -> Path:
    override = os.environ.get("PERSONAL_PM_RUN_LOG", "").strip()
    if override:
        path = Path(override).expanduser()
        if not path.is_absolute():
            path = data_dir() / path
        return path
    return data_dir() / "data" / "agent_runs.jsonl"


def _record_date(record: dict) -> str:
    started_at = str(record.get("started_at", ""))
    return started_at[:10] if len(started_at) >= 10 else ""


def _latest_autonomous_run() -> dict | None:
    path = _run_log_path()
    if not path.exists():
        return None

    latest = None
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None

    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("mode") in AUTONOMOUS_RUN_MODES:
            latest = record

    return latest


def _append_browser_run_record(
    *,
    run_id: str,
    provider_key: str,
    provider_label: str,
    selection: dict,
    started_at: str,
    status: str,
    exit_code: int,
    errors: list[str],
    token_summary: dict,
) -> None:
    record = {
        "started_at": started_at,
        "ended_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "run_id": run_id,
        "mode": "browser_run_today",
        "status": status,
        "exit_code": exit_code,
        "provider": provider_key,
        "provider_label": provider_label,
        "run_type": selection["label"],
        "focus": selection.get("focus") or "Default",
        "actions": ["browser_run_today"],
        "errors": errors,
        "token_usage_log_path": str(token_usage_log_path(data_dir())),
    }
    if token_summary and token_summary.get("model_calls"):
        record["token_usage"] = token_summary
    append_jsonl(_run_log_path(), record)


def _morning_status_payload() -> dict:
    today = parse_today()
    today_date = date.today().isoformat()
    plan_date = today.get("date") if today else ""
    plan_current = plan_date == today_date
    latest_run = _latest_autonomous_run()
    latest_run_date = _record_date(latest_run or {})
    latest_run_status = str((latest_run or {}).get("status", ""))

    with _run_lock:
        browser_run_active = _run_state["running"]
        browser_run_label = _run_state["run_type"]
        browser_provider = _run_state["provider_label"]

    if browser_run_active:
        status = "running"
        label = "Running"
        recommended_action = "Wait for run"
    elif not today:
        status = "missing"
        label = "No plan yet"
        recommended_action = "Run today's flow"
    elif not plan_current:
        status = "stale"
        label = "Stale"
        recommended_action = "Run today's flow"
    elif latest_run_date == today_date and latest_run_status == "failed":
        status = "failed"
        label = "Run failed"
        recommended_action = "Review logs"
    elif latest_run_date == today_date and latest_run_status in {"success", "skipped"}:
        status = "ready"
        label = "Ready"
        recommended_action = "Review plan"
    elif latest_run:
        status = "ready"
        label = "Ready"
        recommended_action = "Review plan"
    else:
        status = "no_run"
        label = "No run yet"
        recommended_action = "Review current plan"

    return {
        "status": status,
        "label": label,
        "today_date": today_date,
        "plan_date": plan_date,
        "plan_current": plan_current,
        "data_root": str(data_dir()),
        "run_log_path": str(_run_log_path()),
        "token_usage_log_path": str(token_usage_log_path(data_dir())),
        "latest_run": latest_run,
        "latest_run_date": latest_run_date,
        "recommended_action": recommended_action,
        "browser_run": {
            "running": browser_run_active,
            "provider_label": browser_provider,
            "run_type": browser_run_label,
        },
    }


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


_run_state = {
    "running": False,
    "log": "",
    "provider": "",
    "provider_label": "",
    "run_type": "",
    "run_id": "",
    "token_summary": {},
    "token_usage_log_path": "",
}
_run_lock = threading.Lock()


@app.route("/api/morning-status")
def api_morning_status():
    return jsonify(_morning_status_payload())


@app.route("/api/run-today", methods=["POST"])
def api_run_today():
    body = request.get_json(silent=True) or {}
    provider_key = body.get("provider", "codex")
    if provider_key not in RUN_PROVIDERS:
        return jsonify({"ok": False, "error": f"Unsupported runner: {provider_key}"}), 400
    try:
        selection = _run_selection(body)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400

    provider_label = RUN_PROVIDERS[provider_key]["label"]
    run_id = f"browser-{datetime.now().strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:8]}"
    usage_log = token_usage_log_path(data_dir())

    with _run_lock:
        if _run_state["running"]:
            return jsonify({"ok": False, "error": "Already running"}), 409
        _run_state["running"] = True
        _run_state["log"] = (
            f"Starting PM flow with {provider_label}...\nRun type: {selection['label']}\n"
        )
        _run_state["provider"] = provider_key
        _run_state["provider_label"] = provider_label
        _run_state["run_type"] = selection["label"]
        _run_state["run_id"] = run_id
        _run_state["token_summary"] = {}
        _run_state["token_usage_log_path"] = str(usage_log)

    def _run():
        proc = None
        token_sequence = 0
        token_records = []
        model_name = _provider_model_hint(provider_key)
        model_source = "configured_hint" if model_name else ""
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        return_code = 1
        status = "failed"
        errors = []
        try:
            project_root = str(Path(__file__).resolve().parent.parent)
            env = dict(
                os.environ,
                PERSONAL_PM_DATA_DIR=str(data_dir()),
                PERSONAL_PM_RUN_ID=run_id,
                PERSONAL_PM_TOKEN_USAGE_LOG=str(usage_log),
            )
            prompt = _run_prompt(provider_label, selection)
            command = _provider_command(provider_key, prompt, project_root)

            with _run_lock:
                _run_state["log"] += f"Data root: {data_dir()}\n"
                _run_state["log"] += f"Run id: {run_id}\n"
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
                if provider_key == "codex":
                    event = parse_json_event(line)
                    event_model = model_from_event(event or {})
                    if event_model:
                        model_name = event_model
                        model_source = "codex_event"
                    record = codex_token_record(
                        event or {},
                        run_id=run_id,
                        flow="personal_pm",
                        provider=provider_key,
                        step="browser_run_today",
                        sequence=token_sequence + 1,
                        source="codex_exec_json",
                        model=model_name,
                        model_source=model_source,
                    )
                    if record:
                        token_sequence += 1
                        token_records.append(record)
                        append_jsonl(usage_log, record)
                        with _run_lock:
                            _run_state["log"] += (
                                f"Tokens browser_run_today#{token_sequence}: "
                                f"{record.get('model', 'unknown model')}, "
                                f"{record['total_tokens']} total "
                                f"({record['input_tokens']} input, "
                                f"{record['output_tokens']} output, "
                                f"{record['reasoning_output_tokens']} reasoning)\n"
                            )
                        continue

                    display_lines = codex_display_lines(event, line)
                    if display_lines:
                        with _run_lock:
                            _run_state["log"] += "\n".join(display_lines) + "\n"
                    continue

                with _run_lock:
                    _run_state["log"] += line
            return_code = proc.wait(timeout=600)
            if return_code != 0:
                errors.append(f"{provider_label} exited with code {return_code}")
                with _run_lock:
                    _run_state["log"] += f"\n{provider_label} exited with code {return_code}.\n"
            else:
                status = "success"
        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            return_code = 124
            errors.append(f"{provider_label} timed out after 10 minutes")
            with _run_lock:
                _run_state["log"] += (
                    f"\n{provider_label} timed out after 10 minutes and was stopped.\n"
                )
        except Exception as e:
            errors.append(str(e))
            with _run_lock:
                _run_state["log"] += f"\nError: {e}"
        finally:
            summary = summarize_records(token_records)
            _append_browser_run_record(
                run_id=run_id,
                provider_key=provider_key,
                provider_label=provider_label,
                selection=selection,
                started_at=started_at,
                status=status,
                exit_code=return_code,
                errors=errors,
                token_summary=summary,
            )
            with _run_lock:
                _run_state["token_summary"] = summary
                if provider_key == "codex":
                    _run_state["log"] += f"\n{token_summary_line(summary)}\n"
                    _run_state["log"] += f"Token log: {usage_log}\n"
                _run_state["running"] = False

    threading.Thread(target=_run, daemon=True).start()
    return jsonify(
        {
            "ok": True,
            "provider": provider_key,
            "provider_label": provider_label,
            "run_type": selection["label"],
            "run_id": run_id,
            "token_usage_log_path": str(usage_log),
        }
    )


@app.route("/api/run-status")
def api_run_status():
    with _run_lock:
        return jsonify(
            {
                "running": _run_state["running"],
                "log": _run_state["log"],
                "provider": _run_state["provider"],
                "provider_label": _run_state["provider_label"],
                "run_type": _run_state["run_type"],
                "run_id": _run_state["run_id"],
                "token_summary": _run_state["token_summary"],
                "token_usage_log_path": _run_state["token_usage_log_path"],
            }
        )


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


def _project_args(body):
    return {
        "name": body.get("name", ""),
        "priority": body.get("priority", "Now"),
        "status": body.get("status", "Idea"),
        "discipline": body.get("discipline", ""),
        "next_action": body.get("next_action", ""),
        "notes": body.get("notes", ""),
    }


def _project_result(ok, error=""):
    status = 200 if ok else 400
    return jsonify({"ok": ok, "error": error, "projects": parse_projects()}), status


def _weekly_focus_args(body):
    return {
        "week_of": body.get("week_of", ""),
        "why": body.get("why", ""),
        "priorities": body.get("priorities", []),
        "notes": body.get("notes", ""),
    }


def _weekly_focus_result(ok, error=""):
    status = 200 if ok else 400
    return jsonify({"ok": ok, "error": error, "weekly": parse_weekly_focus()}), status


@app.route("/api/add-project", methods=["POST"])
def api_add_project():
    body = request.get_json(silent=True) or {}
    ok, error = add_project(**_project_args(body))
    return _project_result(ok, error)


@app.route("/api/delete-project", methods=["POST"])
def api_delete_project():
    body = request.get_json(silent=True) or {}
    idx = body.get("index", -1)
    ok, error = delete_project(idx)
    return _project_result(ok, error)


@app.route("/api/edit-project", methods=["POST"])
def api_edit_project():
    body = request.get_json(silent=True) or {}
    ok, error = edit_project(project_index=body.get("index", -1), **_project_args(body))
    return _project_result(ok, error)


@app.route("/api/add-weekly-focus", methods=["POST"])
def api_add_weekly_focus():
    body = request.get_json(silent=True) or {}
    ok, error = add_weekly_focus(**_weekly_focus_args(body))
    return _weekly_focus_result(ok, error)


@app.route("/api/edit-weekly-focus", methods=["POST"])
def api_edit_weekly_focus():
    body = request.get_json(silent=True) or {}
    ok, error = edit_weekly_focus(week_index=body.get("index", -1), **_weekly_focus_args(body))
    return _weekly_focus_result(ok, error)


@app.route("/api/delete-weekly-focus", methods=["POST"])
def api_delete_weekly_focus():
    body = request.get_json(silent=True) or {}
    ok, error = delete_weekly_focus(body.get("index", -1))
    return _weekly_focus_result(ok, error)


def _onboarding_provider(body):
    """Return a valid provider key or raise ValueError for an unsupported one."""
    return onboarding.normalize_provider(body.get("provider", onboarding.DEFAULT_PROVIDER))


@app.route("/api/onboarding/questions", methods=["POST"])
def api_onboarding_questions():
    body = request.get_json(silent=True) or {}
    week_of = current_week_of()
    need_goals = bool(body.get("need_goals", False))
    try:
        provider = _onboarding_provider(body)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    try:
        questions = onboarding.generate_questions(week_of, need_goals=need_goals, provider=provider)
    except (FileNotFoundError, TimeoutError, ValueError, RuntimeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "week_of": week_of, "provider": provider, "questions": questions})


@app.route("/api/onboarding/generate", methods=["POST"])
def api_onboarding_generate():
    body = request.get_json(silent=True) or {}
    week_of = current_week_of()
    need_goals = bool(body.get("need_goals", False))
    answers = body.get("answers", [])
    if not isinstance(answers, list) or not answers:
        return jsonify({"ok": False, "error": "Answers are required."}), 400
    try:
        provider = _onboarding_provider(body)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    try:
        result = onboarding.generate_focus(
            week_of, answers, need_goals=need_goals, provider=provider
        )
    except (FileNotFoundError, TimeoutError, ValueError, RuntimeError) as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "week_of": week_of, "provider": provider, **result})


if __name__ == "__main__":
    port = int(os.environ.get("PERSONAL_PM_PORT", "5151"))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
