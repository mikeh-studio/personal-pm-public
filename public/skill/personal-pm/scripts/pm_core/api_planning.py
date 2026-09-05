"""Skill-grounded API drafts; no browser or Flask dependency."""

import hashlib
import json
import secrets
import tempfile
import threading
import time
from pathlib import Path

import validate_today

from pm_core import api_provider, workflow
from pm_core.paths import SKILL_DIR, data_dir, data_path
from pm_core.weekly import build_planner_context

_DRAFTS = {}
_LOCK = threading.RLock()
CONTEXT_FILES = (
    "goals/goal.md",
    "goals/projects.md",
    "context/weekly-focus.md",
    "tasks/today.md",
    "tasks/backlog.md",
    "tasks/archive/log.md",
    "context/planning-insights.md",
    "context/weekly-outcomes.md",
    "context/daily-report.md",
    "config/planner.json",
    "context/daily-outcomes.md",
    "context/planner-memory.md",
    "data/task_log.csv",
)


def fingerprint():
    return hashlib.sha256(
        json.dumps([workflow.read(data_dir() / name) for name in CONTEXT_FILES]).encode()
    ).hexdigest()


def draft_plan(key, mode, focus, user_context):
    if (
        not isinstance(mode, str)
        or mode not in {"normal", "focus"}
        or not isinstance(focus, str)
        or len(focus) > 80
    ):
        raise ValueError("Invalid planning mode or focus.")
    if not isinstance(user_context, str) or len(user_context) > 8000:
        raise ValueError("Keep today's context to 8000 characters or fewer.")
    state = workflow.status()
    if state["goal_errors"]:
        raise ValueError("Review and complete the saved goals before drafting a plan.")
    source_version = fingerprint()
    day = validate_today.expected_date()
    adaptive_rule = workflow.outcomes.adaptive_rule(workflow.planning_days(), day)
    references = "\n\n".join(
        (SKILL_DIR / "references" / name).read_text()
        for name in ("daily-planning.md", "today-template.md", "metadata.md")
    )
    context = {
        "date": day,
        "mode": mode,
        "focus": focus,
        "user_context": user_context,
        "planning_context": state["planning_context"],
        "latest_outcomes": state["latest_outcomes"],
        "taxonomy": state["taxonomy"],
        "adaptive_rule": adaptive_rule,
        "today": (state["today"] or {}).get("raw", ""),
        "backlog": workflow.read(data_path("tasks", "backlog.md"))[:6000],
        "recent_work": workflow.read(data_path("context", "daily-report.md"))[-10000:],
    }
    prompt = (
        f"Planning contract:\n{references}\nSaved context:\n{build_planner_context()}\n"
        f"Current session data:\n{json.dumps(context)}\n"
        "Return ONLY JSON with string summary, list of string questions, and string plan_markdown. "
        "If priority or goal context needs a consequential answer, return up to 3 brief questions and an empty plan_markdown. "
        "Otherwise return no questions and one complete Markdown plan for the given date. Preserve existing checked/canceled tasks and feedback verbatim. "
        "The backend has no tools and will show a draft before applying; do not claim files, goals, or history were changed."
    )
    result = api_provider.generate_json(key, prompt, "daily_draft")
    if not isinstance(result, dict) or set(result) != {"summary", "questions", "plan_markdown"}:
        raise ValueError("Expected a summary, questions, and plan_markdown from the provider.")
    summary, questions, markdown = result["summary"], result["questions"], result["plan_markdown"]
    if (
        not isinstance(summary, str)
        or len(summary) > 2000
        or not isinstance(questions, list)
        or len(questions) > 3
        or any(not isinstance(q, str) or not q.strip() or len(q) > 500 for q in questions)
    ):
        raise ValueError("Provider returned invalid planning questions or summary.")
    if (
        not isinstance(markdown, str)
        or len(markdown) > 30000
        or bool(questions) == bool(markdown.strip())
    ):
        raise ValueError("Provider must return either questions or a plan draft.")
    if source_version != fingerprint() or day != validate_today.expected_date():
        raise ValueError(
            "Planning context changed while drafting. Review the latest state and try again."
        )
    if questions:
        return {"summary": summary, "questions": questions, "plan_markdown": ""}
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "plan.md"
        path.write_text(markdown)
        workflow.save_plan(path, focus=focus, validate_only=True)
    current = state["today"] or {}
    if current.get("date") == day:
        draft_tasks = validate_today.extract_tasks_section(markdown.splitlines())
        for line in validate_today.extract_tasks_section(current.get("raw", "").splitlines()):
            if line.startswith("- [") and (
                line.startswith(("- [x]", "- [X]"))
                or any(f"status:{s}" in line for s in ("canceled", "cancelled", "deleted"))
            ):
                if line not in draft_tasks:
                    raise ValueError(
                        "Draft omitted previously completed or canceled work. Nothing was saved."
                    )
        draft_feedback = workflow.store.parse_today_text(markdown)["feedback"]
        for field, value in current.get("feedback", {}).items():
            if value and draft_feedback.get(field) != value:
                raise ValueError("Draft omitted existing feedback. Nothing was saved.")
    with _LOCK:
        now = time.monotonic()
        for token in list(_DRAFTS):
            if now - _DRAFTS[token]["created"] > 900:
                del _DRAFTS[token]
        if len(_DRAFTS) >= 20:
            _DRAFTS.pop(next(iter(_DRAFTS)))
        token = secrets.token_urlsafe(24)
        _DRAFTS[token] = {
            "root": str(data_dir()),
            "version": source_version,
            "day": day,
            "markdown": markdown,
            "focus": focus,
            "created": now,
        }
    return {"summary": summary, "questions": [], "plan_markdown": markdown, "draft_id": token}


def apply_draft(token):
    with _LOCK, workflow.store._file_lock:
        draft = _DRAFTS.get(token)
        if (
            not draft
            or draft["root"] != str(data_dir())
            or time.monotonic() - draft["created"] > 900
        ):
            raise ValueError("Draft expired or unavailable; generate a new draft.")
        if draft["version"] != fingerprint() or draft["day"] != validate_today.expected_date():
            raise ValueError("The workspace changed. Generate a fresh draft before applying.")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "plan.md"
            path.write_text(draft["markdown"])
            workflow.save_plan(path, focus=draft["focus"], validate_only=True)
            current = workflow.store.parse_today()
            if (
                current
                and current.get("date")
                and current["tasks"]
                and current["date"] != draft["day"]
            ):
                workflow.rollover(draft["day"])
            result = workflow.save_plan(path, replace=True, focus=draft["focus"])
        del _DRAFTS[token]
    return result
