"""Deterministic file operations for the conversational planner. No agent or UI runtime."""

import os
import re
import tempfile
from datetime import date
from pathlib import Path

import outcome_memory as outcomes
import task_ledger as ledger
import validate_today as validator

from . import store
from .context import planning_context
from .goals import validate_goal_file
from .paths import data_dir, data_path
from .taxonomy import load as load_taxonomy


def read(path):
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write(path, text):
    if read(path) == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return True


def status():
    path = data_path("goals", "goal.md")
    errors = validate_goal_file(path) if path.exists() else ["Missing goals/goal.md"]
    plan = store.parse_today()
    weekly = store.parse_weekly_focus()
    days = outcomes.parse_archive(read(data_path("tasks", "archive", "log.md")))
    return {
        "data_root": str(data_dir()),
        "goal_errors": errors,
        "today": plan,
        "weekly": weekly,
        "planning_context": planning_context(plan, weekly, days, validator.expected_date()),
        "latest_outcomes": {
            "date": days[-1].day,
            "completed": len(days[-1].completed),
            "confirmed_incomplete_or_blocked": len(days[-1].confirmed_incomplete),
            "unknown": len(days[-1].unknown),
            "canceled_or_deleted": len(days[-1].deleted_canceled),
            "reporting_coverage_percent": days[-1].reporting_coverage,
        }
        if days
        else None,
        "projects": store.project_daily_flow_partition(),
        "taxonomy": {key: sorted(values) for key, values in load_taxonomy().items()},
        "adaptive_rule": outcomes.adaptive_rule(days, validator.expected_date()),
    }


def require_plan_day(expected):
    date.fromisoformat(expected)
    plan = store.parse_today()
    if not plan or plan["date"] != expected:
        raise ValueError(
            "The plan date changed or is missing. Read today's plan and supply its date."
        )
    return plan


def complete(index, expected):
    plan = require_plan_day(expected)
    if not 0 <= index < len(plan["tasks"]):
        raise ValueError("Task index is out of range (zero based).")
    task = plan["tasks"][index]
    if store._normalize_status(store._normalized_metadata_value(task["meta"], "status")):
        raise ValueError("A canceled task cannot be marked complete.")
    if task["checked"]:
        return {"changed": False}
    return {"changed": store.toggle_task(index)}


def feedback(field, text, expected):
    require_plan_day(expected)
    if field not in {"worked", "did_not_work", "new_goal"}:
        raise ValueError("Unsupported feedback field.")
    if not isinstance(text, str) or len(text) > 4000 or "\x00" in text:
        raise ValueError("Feedback must be text of at most 4000 characters.")
    return {"changed": store.update_feedback(field, " ".join(text.split()))}


def report(index, outcome, expected):
    """Record an explicit closeout without inferring completion from an empty checkbox."""
    if outcome not in {"completed", "incomplete", "blocked", "dropped", "unknown"}:
        raise ValueError("Unsupported task outcome.")
    if outcome == "completed":
        return complete(index, expected)
    with store._file_lock:
        plan = require_plan_day(expected)
        if not 0 <= index < len(plan["tasks"]):
            raise ValueError("Task index is out of range (zero based).")
        task = plan["tasks"][index]
        canceled = store._normalize_status(store._normalized_metadata_value(task["meta"], "status"))
        if canceled:
            if outcome == "dropped":
                return {"changed": False}
            raise ValueError("A canceled task cannot be reopened by closeout.")
        if task["checked"]:
            raise ValueError(
                "Closeout cannot erase a recorded completion; explicitly revise the plan to correct it."
            )
        matches = list(re.finditer(r"^- \[[ xX]\] \[P\d\] \[\d+m\] .+$", plan["raw"], re.MULTILINE))
        match = matches[index]
        parts = match[0].split(" | ")
        parts = [parts[0]] + [
            part for part in parts[1:] if part.split(":", 1)[0].strip().lower() != "outcome"
        ]
        if outcome == "dropped":
            parts = [parts[0]] + [
                part for part in parts[1:] if part.split(":", 1)[0].strip().lower() != "status"
            ]
            parts.append("status:canceled")
        else:
            parts.append(f"outcome:{outcome}")
        updated = plan["raw"][: match.start()] + " | ".join(parts) + plan["raw"][match.end() :]
        return {"changed": write(data_path("tasks", "today.md"), updated)}


def dated_section(text, day):
    match = re.search(rf"^## {re.escape(day)}\s*\n.*?(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(0).strip() if match else None


def archive_entry(plan):
    tasks = validator.extract_tasks_section(plan["raw"].splitlines())
    parsed = [outcomes.parse_task_line(line) for line in tasks]
    if not tasks or any(task is None for task in parsed):
        raise ValueError("Cannot archive an empty or malformed task list.")
    canceled = [task for task in parsed if not task.active]
    active = [task for task in parsed if task.active]
    completed = [task for task in active if task.checked]
    notes = [
        f"Completed: {len(completed)}",
        f"Deleted / canceled: {len(canceled)}",
        f"Incomplete / carry-forward: {len(active) - len(completed)}",
    ]
    notes += [f"Carry-forward: {item}" for item in plan["carry_forward"]]
    notes += [f"Heads-up: {item}" for item in plan["heads_up"]]
    notes += [f"Feedback {key}: {value}" for key, value in plan["feedback"].items() if value]
    lines = [f"## {plan['date']}", "", "### Final Tasks", *[t.line for t in active]]
    if canceled:
        lines += ["", "### Deleted / Canceled Tasks", *[t.line for t in canceled]]
    lines += ["", "### Planning Notes", *[f"- {note}" for note in notes]]
    return "\n".join(lines).strip()


def append_section(path, day, section):
    text = read(path)
    existing = dated_section(text, day)
    if existing:
        return False
    return write(path, text.rstrip() + "\n\n" + section.rstrip() + "\n")


def _rollover_archive(plan):
    """Prepare and validate the next archive state without writing it."""
    entry = archive_entry(plan)
    archive = data_path("tasks", "archive", "log.md")
    archive_text = read(archive)
    existing = dated_section(archive_text, plan["date"])
    if existing and existing != entry:
        raise ValueError(
            "Archive already contains a different final state for this date; resolve it before rollover."
        )
    combined = archive_text if existing else archive_text.rstrip() + "\n\n" + entry + "\n"
    days = outcomes.parse_archive(combined)
    # Validate ledger conversion before making any changes. Replays recover derived files.
    rows = [
        ledger.parse_task_line(task.line, plan["date"], "archive_rollover")
        for task in next(day for day in days if day.day == plan["date"]).completed
    ]
    rows = [row for row in rows if row]
    return combined, days, rows


def planning_days():
    """Include the day about to roll over when validating the next plan's scope."""
    plan = store.parse_today()
    if plan and plan["date"] and plan["tasks"]:
        previous = date.fromisoformat(plan["date"])
        target = date.fromisoformat(validator.expected_date())
        if previous > target:
            raise ValueError("Cannot overwrite a future plan.")
        if previous < target:
            return _rollover_archive(plan)[1]
    return outcomes.parse_archive(read(data_path("tasks", "archive", "log.md")))


def rollover(target_date):
    target = date.fromisoformat(target_date)
    plan = store.parse_today()
    if not plan or not plan["date"]:
        raise ValueError("No dated plan to roll over.")
    previous = date.fromisoformat(plan["date"])
    if previous == target:
        return {"changed": False, "reason": "Plan is already current."}
    if previous > target:
        raise ValueError("Cannot roll a future plan backward.")
    combined, days, rows = _rollover_archive(plan)
    archive = data_path("tasks", "archive", "log.md")
    changed = write(archive, combined)
    added = ledger.append_rows(data_path("data", "task_log.csv"), rows)
    write(data_path("context", "planning-insights.md"), outcomes.build_planning_insights(days, 14))
    write(data_path("context", "weekly-outcomes.md"), outcomes.build_weekly_outcomes(days, 8))
    archived = next(day for day in days if day.day == plan["date"])
    signal, _, _ = outcomes.adaptive_rule([day for day in days if day.day <= plan["date"]])
    append_section(
        data_path("context", "daily-outcomes.md"),
        plan["date"],
        f"## {plan['date']}\n\nCompleted tasks:\n"
        + "\n".join(f"- {task.title}" for task in archived.completed)
        + "\n\nSpecific feedback:\n"
        + "\n".join(f"- {k}: {v}" for k, v in plan["feedback"].items() if v)
        + f"\n\nPlanning takeaway: {signal}\n",
    )
    append_section(
        data_path("context", "planner-memory.md"),
        plan["date"],
        f"## {plan['date']}\n\n- {signal}\n",
    )
    return {
        "changed": changed,
        "archived_date": plan["date"],
        "ledger_rows_added": added,
        "adaptive_rule": signal,
    }


def save_plan(source: Path, replace=False, focus="", validate_only=False):
    path = data_path("goals", "goal.md")
    errors = validate_goal_file(path) if path.exists() else ["Missing goals/goal.md"]
    if errors:
        raise ValueError("; ".join(errors))
    candidate = source.read_text(encoding="utf-8")
    task_lines = validator.extract_tasks_section(candidate.splitlines())
    if any(
        not re.fullmatch(r"- \[[ xX]\] \[P[123]\] \[[1-9]\d*m\] .+", line) for line in task_lines
    ):
        raise ValueError(
            "Use canonical task lines: - [ ] [P1] [20m] Task | type:... | goal:... | sub:..."
        )
    for heading in ("### Carry-forward", "### Heads-up", "### Feedback For Tomorrow"):
        if heading not in candidate.splitlines():
            raise ValueError(f"Missing {heading} section.")
    # Validate in the active data root so workspace vocabulary applies to draft files too.
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        draft = root / "tasks/today.md"
        draft.parent.mkdir()
        draft.write_text(candidate, encoding="utf-8")
        config = data_path("config", "planner.json")
        if config.exists():
            (root / "config").mkdir()
            (root / "config/planner.json").write_text(read(config), encoding="utf-8")
        errors = validator.validate(draft, 5, 1, False)
    tasks = [
        outcomes.parse_task_line(line)
        for line in validator.extract_tasks_section(candidate.splitlines())
    ]
    if errors or any(task is None for task in tasks):
        raise ValueError("; ".join(errors) or "Malformed tasks.")
    active = [task for task in tasks if task.active]
    if sum(task.priority == "P1" for task in active) != 1:
        raise ValueError("A plan must have exactly one active P1 success condition.")
    projects = store.parse_projects() or []
    project_names = {project["name"] for project in projects}
    seen_projects = set()
    seen_titles = set()
    for task in active:
        project_name = task.metadata.get("project", "")
        if project_name and project_name not in project_names:
            raise ValueError(f"Unknown project: {project_name}. Use an exact saved project name.")
        title = task.title.casefold()
        if title in seen_titles:
            raise ValueError("Keep one task per concrete outcome; duplicate task title found.")
        seen_titles.add(title)
        for project in projects:
            # Explicit metadata is preferred; retain legacy exact lane names.
            lane = task.line.split(" — ", 1)[-1].split(" | ", 1)[0]
            matches = (
                project_name == project["name"]
                if project_name
                else project["name"] in [v.strip() for v in lane.split(" / ")]
            )
            if matches:
                if project["name"] in seen_projects:
                    raise ValueError(f"Keep one task per project: {project['name']}.")
                seen_projects.add(project["name"])
            if matches and (
                project["status"] == "Closed"
                or (project["status"] == "Paused" and focus != project["name"])
            ):
                raise ValueError(
                    f"Project {project['name']} is {project['status']} and ineligible for this plan."
                )
    days = planning_days()
    rule, cap, minutes = outcomes.adaptive_rule(days, validator.expected_date())
    total = sum(task.duration_minutes for task in active)
    if outcomes.recent_reported_zero(days, validator.expected_date()):
        repeated = outcomes.consecutive_zero_completion_days(days) >= 2
        exceeds = (
            (len(active) > cap or total > minutes)
            if repeated
            else (len(active) > cap and total > minutes)
        )
        if exceeds or (
            repeated and any(t.priority == "P1" and t.duration_minutes > 35 for t in active)
        ):
            raise ValueError(rule)
    if validate_only:
        return {"changed": False, "valid": True}
    current = store.parse_today()
    if (
        current
        and current["date"]
        and current["tasks"]
        and current["date"] != validator.expected_date()
    ):
        if date.fromisoformat(current["date"]) > date.fromisoformat(validator.expected_date()):
            raise ValueError("Cannot overwrite a future plan.")
        if dated_section(
            read(data_path("tasks", "archive", "log.md")), current["date"]
        ) != archive_entry(current):
            raise ValueError("Roll over the prior plan before saving a new day.")
    if current and current["date"] == validator.expected_date() and current["tasks"]:
        if candidate == current["raw"]:
            return {"changed": False}
        if not replace:
            raise ValueError(
                "A plan already exists for today; verify it or explicitly request --replace."
            )
    return {"changed": write(data_path("tasks", "today.md"), candidate)}
