"""First-run onboarding: use a local agent CLI to draft weekly-focus questions and
synthesize a weekly focus from the user's answers after goals are managed explicitly.

The same runners as "Run Today's Flow" are supported (Codex, Claude Code, Gemini CLI).
Each CLI is run read-only and asked to return only JSON — it never edits files. The
server validates the JSON and persists it via parser writers.
"""

import json
import os
import shutil
import subprocess

from parser import parse_goals  # noqa: F401 — compatibility for existing callers
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
    if key.startswith("api:"):
        from pm_core.connections import provider

        provider(key[4:])
        return key
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
    if provider_key.startswith("api:"):
        from pm_core.api_provider import generate_json

        return generate_json(provider_key[4:], prompt, "weekly_setup")
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


# Shared weekly policy, context, and writers live with the skill.
from pm_core.weekly import (  # noqa: E402, F401
    _clean_questions,
    build_planner_context,
    focus_prompt,
    questions_prompt,
    save_weekly,
)


def generate_questions(week_of, provider=DEFAULT_PROVIDER):
    payload = _run_provider_json(provider, questions_prompt(week_of))
    questions = _clean_questions(payload.get("questions"))
    if len(questions) < 6:
        raise ValueError("The assistant did not return the required 6 to 8 questions.")
    return questions


def generate_focus(week_of, answers, provider=DEFAULT_PROVIDER):
    payload = _run_provider_json(provider, focus_prompt(week_of, answers))
    return save_weekly(week_of, payload)
