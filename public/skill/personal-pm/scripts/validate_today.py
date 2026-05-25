#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path


TASK_TYPES = {
    "interview_prep",
    "project_work",
    "skill_practice",
    "career",
    "writing",
    "design_exploration",
}

GOALS = {"data_owner", "experience_design"}

SUB_CATEGORIES = {
    "decision_science",
    "data_foundation",
    "evaluation_discipline",
    "service_platform_eng",
    "website",
    "writing",
    "physical_ai",
    "career_assets",
}

BACKLOG_RE = re.compile(r"^[1-9]\d*d$")

PLAN_DATE_RE = re.compile(r"^##\s+(?P<date>\d{4}-\d{2}-\d{2})\s+.+Daily Plan\s*$")
TASK_LINE_RE = re.compile(
    r"^- \[(?P<done>[ xX])\]\s*"
    r"(?:(?:\[(?P<priority_bracket>P[123])\])|(?P<priority_plain>P[123]))?\s*"
    r"(?:(?:\[(?P<duration>\d+)m\])|(?P<duration_plain>\d+)m)?\s*"
    r"(?P<body>.+?)\s*$"
)

PLANNER_MAINTENANCE_TERMS = {
    "personal-pm",
    "planner maintenance",
    "task_log",
    "tasks/archive",
    "planner-memory",
    "weekly-focus",
    "launchd",
    "cron",
}


def normalize_token(value: str) -> str:
    token = value.strip().lower()
    token = token.replace("&", "and")
    token = re.sub(r"[^a-z0-9]+", "_", token)
    return re.sub(r"_+", "_", token).strip("_")


def expected_date() -> str:
    return os.environ.get("PERSONAL_PM_TODAY_DATE", date.today().isoformat())


def resolve_data_dir(value: str | None = None) -> Path:
    raw_value = value if value is not None else os.environ.get("PERSONAL_PM_DATA_DIR", "")
    raw_value = raw_value.strip()
    if not raw_value:
        raw_value = "private"

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def split_metadata(body: str):
    parts = [part.strip() for part in body.split(" | ")]
    main = parts[0]
    metadata = {}
    for part in parts[1:]:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        metadata[key.strip().lower()] = value.strip()
    return main, metadata


def extract_tasks_section(lines):
    in_tasks = False
    tasks = []
    for line in lines:
        if line.startswith("### Tasks"):
            in_tasks = True
            continue
        if in_tasks and line.startswith("### "):
            break
        if in_tasks and line.startswith("- ["):
            tasks.append(line)
    return tasks


def extract_plan_date(lines):
    for line in lines:
        match = PLAN_DATE_RE.match(line.strip())
        if match:
            return match.group("date")
    return ""


def lane_key(main_text: str) -> str:
    if " — " in main_text:
        _, lane = main_text.rsplit(" — ", 1)
        return normalize_token(lane)

    lowered = main_text.lower()
    if "interview" in lowered:
        return "interview"
    if lowered.startswith("side project"):
        return "side_project"
    if "website" in lowered:
        return "website"
    if "writeup" in lowered or "writing" in lowered:
        return "writing"
    return ""


def validate_task_line(line: str, index: int, allow_planner_maintenance: bool):
    errors = []
    match = TASK_LINE_RE.match(line.strip())
    if not match:
        return [f"Task {index}: invalid checkbox task format"]

    priority = match.group("priority_bracket") or match.group("priority_plain") or ""
    if priority not in {"P1", "P2", "P3"}:
        errors.append(f"Task {index}: missing P1/P2/P3 priority")

    body = match.group("body").strip()
    main_text, metadata = split_metadata(body)

    missing = [key for key in ("type", "goal", "sub") if key not in metadata]
    if missing:
        errors.append(f"Task {index}: missing metadata {', '.join(missing)}")

    task_type = metadata.get("type")
    if task_type and task_type not in TASK_TYPES:
        errors.append(f"Task {index}: invalid type '{task_type}'")

    goal = metadata.get("goal")
    if goal and goal not in GOALS:
        errors.append(f"Task {index}: invalid goal '{goal}'")

    sub = metadata.get("sub")
    if sub and sub not in SUB_CATEGORIES:
        errors.append(f"Task {index}: invalid sub '{sub}'")

    backlog = metadata.get("backlog")
    if backlog:
        if not BACKLOG_RE.match(backlog):
            errors.append(f"Task {index}: invalid backlog '{backlog}' (expected Nd, for example 4d)")
        else:
            backlog_days = int(backlog[:-1])
            duration = match.group("duration") or match.group("duration_plain") or ""
            duration_minutes = int(duration) if duration else 0
            if priority in {"P1", "P2"} and backlog_days >= 2 and duration_minutes > 60:
                errors.append(
                    f"Task {index}: repeated high-priority backlog task is still over 60m; split it into a smaller actionable step"
                )

    if not allow_planner_maintenance:
        normalized_main = main_text.lower()
        for term in PLANNER_MAINTENANCE_TERMS:
            if term in normalized_main:
                errors.append(f"Task {index}: planner-maintenance term '{term}' is not allowed")
                break

    return errors


def validate(path: Path, task_count: int, allow_planner_maintenance: bool, check_date: bool = True):
    errors = []

    if not path.exists():
        return [f"Missing today file: {path}"]

    lines = path.read_text(encoding="utf-8").splitlines()
    plan_date = extract_plan_date(lines)
    current_date = expected_date()

    if not plan_date:
        errors.append("Missing '## YYYY-MM-DD — Daily Plan' heading")
    elif check_date and plan_date != current_date:
        errors.append(f"Plan date is {plan_date}, expected {current_date}")

    tasks = extract_tasks_section(lines)
    if len(tasks) != task_count:
        errors.append(f"Expected {task_count} tasks, found {len(tasks)}")

    lanes = {}
    for index, line in enumerate(tasks, start=1):
        errors.extend(validate_task_line(line, index, allow_planner_maintenance))
        match = TASK_LINE_RE.match(line.strip())
        if not match:
            continue
        main_text, _ = split_metadata(match.group("body").strip())
        lane = lane_key(main_text)
        if not lane:
            continue
        if lane in lanes:
            errors.append(f"Task {index}: duplicate lane with task {lanes[lane]} ('{lane}')")
        else:
            lanes[lane] = index

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the canonical personal PM daily plan.")
    parser.add_argument("--data-dir", default=os.environ.get("PERSONAL_PM_DATA_DIR", ""), help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/")
    parser.add_argument("--file", default="", help="Path to the daily plan file. Overrides --data-dir")
    parser.add_argument("--task-count", type=int, default=int(os.environ.get("PERSONAL_PM_TASK_COUNT", "5")))
    parser.add_argument("--allow-planner-maintenance", action="store_true")
    parser.add_argument("--skip-date-check", action="store_true", help="Validate shape without requiring today's date")
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation output")
    args = parser.parse_args()

    path = Path(args.file).expanduser() if args.file else resolve_data_dir(args.data_dir) / "tasks" / "today.md"
    if not path.is_absolute():
        path = Path.cwd() / path

    errors = validate(path, args.task_count, args.allow_planner_maintenance, check_date=not args.skip_date_check)
    result = {"ok": not errors, "errors": errors, "file": str(path)}

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        print(f"{path} validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(f"{path} validation passed")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
