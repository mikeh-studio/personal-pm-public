"""First-run onboarding: use a local agent CLI to draft weekly-focus questions and
synthesize a weekly focus (and overall goals when missing) from the user's answers.

The same runners as "Run Today's Flow" are supported (Codex, Claude Code, Gemini CLI).
Each CLI is run read-only and asked to return only JSON — it never edits files. The
server validates the JSON and persists it via parser writers.
"""

import json
import os
import shutil
import subprocess

from parser import (
    add_weekly_focus,
    ensure_weekly_focus_file,
    parse_goals,
    parse_projects,
    parse_weekly_focus,
    set_overall_goals,
)
from paths import REPO_ROOT

# Mirror server.RUN_PROVIDERS so onboarding offers the same runners as the daily flow.
PROVIDERS = {
    "codex": {"label": "Codex", "env": "PERSONAL_PM_CODEX_BIN", "command": "codex"},
    "claude": {"label": "Claude Code", "env": "PERSONAL_PM_CLAUDE_BIN", "command": "claude"},
    "gemini": {"label": "Gemini CLI", "env": "PERSONAL_PM_GEMINI_BIN", "command": "gemini"},
}
DEFAULT_PROVIDER = "codex"
CLI_TIMEOUT = 120


# ── Agent CLI as a JSON function ──


def normalize_provider(provider_key):
    key = str(provider_key or "").strip().lower() or DEFAULT_PROVIDER
    if key not in PROVIDERS:
        raise ValueError(f"Unsupported runner: {provider_key}")
    return key


def _resolve_bin(provider_key):
    provider = PROVIDERS[provider_key]
    override = os.environ.get(provider["env"], "").strip()
    if override:
        return override
    found = shutil.which(provider["command"])
    if found:
        return found
    raise FileNotFoundError(
        f"{provider['label']} CLI not found. Install it or set {provider['env']} to its path."
    )


def _build_command(provider_key, executable, prompt, model):
    if provider_key == "codex":
        command = [
            executable,
            "exec",
            "--json",
            "-s",
            "read-only",
            "--skip-git-repo-check",
            "-C",
            str(REPO_ROOT),
        ]
        if model:
            command += ["-m", model]
        command.append(prompt)
        return command
    if provider_key == "claude":
        command = [
            executable,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--disallowedTools",
            "Write",
            "Edit",
            "Bash",
        ]
        if model:
            command += ["--model", model]
        return command
    if provider_key == "gemini":
        command = [executable, "-p", prompt, "-o", "json", "--approval-mode", "plan"]
        if model:
            command += ["-m", model]
        return command
    raise ValueError(f"Unsupported runner: {provider_key}")


def _first_json_object(text):
    """Return the first balanced {...} substring, respecting quoted strings."""
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _coerce_obj(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            snippet = _first_json_object(value)
            if snippet:
                try:
                    return json.loads(snippet)
                except json.JSONDecodeError:
                    return None
    return None


def _obj_from(value):
    obj = _coerce_obj(value)
    if isinstance(obj, dict):
        return obj
    if isinstance(value, str):
        snippet = _first_json_object(value)
        if snippet:
            obj = _coerce_obj(snippet)
            if isinstance(obj, dict):
                return obj
    return None


def _codex_answer(stdout):
    """Pull the final agent_message text (and any error) from codex --json stream."""
    text = None
    error = ""
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message" and item.get("text"):
            text = item["text"]
        if event.get("type") in ("error", "turn.failed"):
            err = event.get("message") or (event.get("error") or {}).get("message") or ""
            if err:
                error = str(err)
    return text, error


def _extract_json(provider_key, stdout):
    """Return (obj, error_detail) for the provider's stdout."""
    raw = (stdout or "").strip()

    if provider_key == "codex":
        text, error = _codex_answer(raw)
        obj = _obj_from(text) if text else None
        if obj is None and not error:
            obj = _obj_from(raw)
        return obj, error

    if provider_key == "claude":
        envelope = _coerce_obj(raw)
        if isinstance(envelope, dict):
            for key in ("structured_output", "result"):
                if key in envelope:
                    obj = _obj_from(envelope[key])
                    if obj:
                        return obj, ""
            if "questions" in envelope or "weekly" in envelope:
                return envelope, ""
        return _obj_from(raw), ""

    if provider_key == "gemini":
        envelope = _coerce_obj(raw)
        if isinstance(envelope, dict):
            for key in ("response", "result", "text", "output"):
                if isinstance(envelope.get(key), str):
                    obj = _obj_from(envelope[key])
                    if obj:
                        return obj, ""
            if "questions" in envelope or "weekly" in envelope:
                return envelope, ""
        return _obj_from(raw), ""

    return _obj_from(raw), ""


def _run_provider_json(provider_key, prompt):
    provider_key = normalize_provider(provider_key)
    executable = _resolve_bin(provider_key)
    model = os.environ.get("PERSONAL_PM_ONBOARDING_MODEL", "").strip()
    command = _build_command(provider_key, executable, prompt, model)
    label = PROVIDERS[provider_key]["label"]

    try:
        proc = subprocess.run(  # noqa: S603
            command,
            capture_output=True,
            text=True,
            timeout=CLI_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("The assistant took too long to respond. Please try again.") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()[:400]
        raise RuntimeError(f"{label} failed (exit {proc.returncode}). {detail}".strip())

    obj, error = _extract_json(provider_key, proc.stdout)
    if obj is None:
        detail = error or (proc.stderr or "").strip()[:300]
        raise ValueError(
            f"{label} did not return usable JSON. {detail}".strip()
            if detail
            else f"{label} did not return usable JSON."
        )
    return obj


# ── Context + prompts ──


def build_planner_context():
    goals = parse_goals() or {}
    overall = goals.get("overall_goals") or []
    disciplines = [d.get("name", "") for d in goals.get("disciplines", []) if d.get("name")]

    projects = parse_projects() or []
    active = [p for p in projects if p.get("priority") == "Now" or p.get("status") == "Active"]
    project_lines = []
    for p in active[:8]:
        line = f"- {p.get('name', '')} ({p.get('priority', '')}/{p.get('status', '')})"
        if p.get("next_action"):
            line += f" next: {p['next_action']}"
        project_lines.append(line)

    weekly = parse_weekly_focus() or {}
    last_priorities = [
        item.get("text", "") for item in (weekly.get("priority_items") or []) if item.get("text")
    ]

    parts = ["Overall goals:\n" + ("\n".join(f"- {g}" for g in overall) or "- (none set yet)")]
    if disciplines:
        parts.append("Key disciplines: " + ", ".join(disciplines))
    parts.append("Active projects:\n" + ("\n".join(project_lines) or "- (none)"))
    if last_priorities:
        parts.append(
            f"Most recent weekly priorities (week of {weekly.get('week_of', '?')}):\n"
            + "\n".join(f"- {t}" for t in last_priorities)
        )
    return "\n\n".join(parts)


def _clean_questions(raw):
    cleaned = []
    for idx, q in enumerate(raw or []):
        if not isinstance(q, dict):
            continue
        label = str(q.get("label", "")).strip()
        if not label:
            continue
        cleaned.append(
            {
                "id": (str(q.get("id") or "").strip() or f"q{idx + 1}"),
                "label": label[:300],
                "help": str(q.get("help", "")).strip()[:300],
                "placeholder": str(q.get("placeholder", "")).strip()[:200],
            }
        )
        if len(cleaned) >= 5:
            break
    return cleaned


_QUESTIONS_SHAPE = (
    '{"questions":[{"id":"snake_case","label":"the question",'
    '"help":"optional one line","placeholder":"optional example answer"}]}'
)


def generate_questions(week_of, need_goals=False, provider=DEFAULT_PROVIDER):
    context = build_planner_context()
    goal_clause = (
        "The user has not set overall goals yet, so include 1-2 questions about their "
        "longer-term direction in addition to this week.\n"
        if need_goals
        else "Overall goals are already set; focus the questions on THIS week only.\n"
    )
    prompt = (
        "You are a focused personal planning coach helping the user set their weekly "
        f"focus for the week of {week_of}.\n\n"
        f"Context about the user:\n{context}\n\n"
        f"{goal_clause}"
        "Write 3 to 5 short, specific questions whose answers let you draft a strong, "
        "concrete weekly focus of 2-4 priorities. Prefer questions about fixed "
        "commitments and deadlines, the single most important outcome this week, time "
        "and energy available, and likely blockers. Avoid generic or yes/no questions.\n\n"
        "Return ONLY a JSON object (no prose, no markdown fences) of exactly this shape:\n"
        f"{_QUESTIONS_SHAPE}\n"
        "Use a snake_case id per question; help and placeholder may be empty strings."
    )
    payload = _run_provider_json(provider, prompt)
    questions = _clean_questions(payload.get("questions"))
    if not questions:
        raise ValueError("The assistant did not return any questions.")
    return questions


def _format_answers(answers):
    lines = []
    for item in answers or []:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("question") or item.get("id") or "").strip()
            answer = str(item.get("answer", "")).strip()
        else:
            label, answer = "", str(item).strip()
        if not answer:
            continue
        lines.append(f"Q: {label}\nA: {answer}" if label else f"A: {answer}")
    return "\n\n".join(lines)


_FOCUS_SHAPE = (
    '{"overall_goals":["..."],'
    '"weekly":{"why":"one sentence","priorities":["...","..."],"notes":"optional"}}'
)


def generate_focus(week_of, answers, need_goals=False, provider=DEFAULT_PROVIDER):
    context = build_planner_context()
    qa = _format_answers(answers)
    if not qa:
        raise ValueError("No answers were provided.")

    goal_clause = (
        "Propose 2-3 concise overall goals (longer-term direction) grounded in the answers "
        "in 'overall_goals'.\n"
        if need_goals
        else "Leave 'overall_goals' as an empty array; only produce the weekly focus.\n"
    )
    prompt = (
        "You are a personal planning coach. Using the user's context and answers, draft a "
        f"concrete weekly focus for the week of {week_of}.\n\n"
        f"User context:\n{context}\n\n"
        f"User answers:\n{qa}\n\n"
        f"{goal_clause}"
        "Weekly focus rules: 'why' is one sentence on the theme; 'priorities' is 2 to 4 "
        "specific, outcome-oriented items naming the concrete result and, where natural, the "
        "discipline or project, e.g. 'Ship X - Discipline / Project'; 'notes' is an optional "
        "short carry-over or constraint (may be empty). Stay grounded in the answers; do not "
        "invent commitments.\n\n"
        "Return ONLY a JSON object (no prose, no markdown fences) of exactly this shape:\n"
        f"{_FOCUS_SHAPE}"
    )
    payload = _run_provider_json(provider, prompt)

    weekly = payload.get("weekly") or {}
    why = str(weekly.get("why", "")).strip()
    priorities = [str(p).strip() for p in (weekly.get("priorities") or []) if str(p).strip()]
    notes = str(weekly.get("notes", "")).strip()
    if not priorities:
        raise ValueError("The assistant did not return any weekly priorities.")

    if need_goals:
        overall = payload.get("overall_goals") or []
        ok, _ = set_overall_goals(overall)
        # If goals could not be set we still proceed; the weekly focus is the priority.

    ensure_weekly_focus_file()
    ok, error = add_weekly_focus(week_of, why=why, priorities=priorities, notes=notes)
    if not ok and "already exists" not in (error or "").lower():
        raise ValueError(error or "Could not save the weekly focus.")

    return {"weekly": parse_weekly_focus(), "goals": parse_goals()}
