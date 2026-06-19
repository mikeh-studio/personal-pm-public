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


def truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def infer_data_dir(path: Path) -> Path:
    if path.name == "today.md" and path.parent.name == "tasks":
        return path.parent.parent.resolve()
    return resolve_data_dir()


def string_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def load_goal_tied_recent_docs(data_dir: Path):
    path = data_dir / "context" / "recent-drive-docs.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if isinstance(payload, list):
        docs = payload
    elif isinstance(payload, dict):
        cache_dates = {
            str(payload.get("run_date", ""))[:10],
            str(payload.get("generated_at", ""))[:10],
        }
        if expected_date() not in cache_dates:
            return []
        docs = payload.get("docs", [])
    else:
        docs = []
    if not isinstance(docs, list):
        return []

    candidates = []
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        matched_goals = [goal for goal in string_list(doc.get("matched_goals")) if goal in GOALS]
        if not matched_goals:
            continue
        candidates.append(
            {
                "id": str(doc.get("id", "") or "").strip(),
                "title": str(doc.get("title", "") or "").strip(),
                "url": str(doc.get("url", "") or "").strip(),
                "matched_goals": matched_goals,
            }
        )
    return candidates


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
            errors.append(
                f"Task {index}: invalid backlog '{backlog}' (expected Nd, for example 4d)"
            )
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


def task_references_doc(main_text: str, metadata: dict, doc: dict) -> bool:
    title = str(doc.get("title") or "").strip().lower()
    if not title or title not in main_text.lower():
        return False

    doc_metadata = metadata.get("doc", "").lower()
    for value in (doc.get("id"), doc.get("url")):
        value = str(value or "").strip().lower()
        if value and value in doc_metadata:
            return True
    return False


def validate_recent_doc_task(task_records, data_dir: Path):
    docs = load_goal_tied_recent_docs(data_dir)
    if not docs:
        return []

    matching_task_indexes = set()
    for index, main_text, metadata in task_records:
        task_goal = metadata.get("goal", "")
        for doc in docs:
            if task_goal not in doc["matched_goals"]:
                continue
            if task_references_doc(main_text, metadata, doc):
                matching_task_indexes.add(index)

    if not matching_task_indexes:
        return [
            "Expected one task to reference a fresh goal-tied recent doc using the doc title and doc:<id-or-url> metadata"
        ]
    if len(matching_task_indexes) > 1:
        return [f"Expected exactly one recent-doc task, found {len(matching_task_indexes)}"]
    return []


def validate(
    path: Path,
    task_count: int,
    min_task_count: int,
    allow_planner_maintenance: bool,
    check_date: bool = True,
    require_doc_task: bool = False,
):
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
    if len(tasks) < min_task_count or len(tasks) > task_count:
        if min_task_count == task_count:
            errors.append(f"Expected {task_count} tasks, found {len(tasks)}")
        else:
            errors.append(
                f"Expected between {min_task_count} and {task_count} tasks, found {len(tasks)}"
            )

    lanes = {}
    task_records = []
    for index, line in enumerate(tasks, start=1):
        errors.extend(validate_task_line(line, index, allow_planner_maintenance))
        match = TASK_LINE_RE.match(line.strip())
        if not match:
            continue
        main_text, metadata = split_metadata(match.group("body").strip())
        task_records.append((index, main_text, metadata))
        lane = lane_key(main_text)
        if not lane:
            continue
        if lane in lanes:
            errors.append(f"Task {index}: duplicate lane with task {lanes[lane]} ('{lane}')")
        else:
            lanes[lane] = index

    if require_doc_task:
        errors.extend(validate_recent_doc_task(task_records, infer_data_dir(path)))

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the canonical personal PM daily plan.")
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PERSONAL_PM_DATA_DIR", ""),
        help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/",
    )
    parser.add_argument(
        "--file", default="", help="Path to the daily plan file. Overrides --data-dir"
    )
    parser.add_argument(
        "--task-count",
        type=int,
        default=int(os.environ.get("PERSONAL_PM_TASK_COUNT", "5")),
        help="Maximum valid task count",
    )
    parser.add_argument(
        "--min-task-count",
        type=int,
        default=int(os.environ.get("PERSONAL_PM_MIN_TASK_COUNT", "1")),
        help="Minimum valid task count",
    )
    parser.add_argument("--allow-planner-maintenance", action="store_true")
    parser.add_argument(
        "--skip-date-check",
        action="store_true",
        help="Validate shape without requiring today's date",
    )
    parser.add_argument(
        "--require-doc-task",
        action="store_true",
        help="Require one task to reference a fresh goal-tied recent doc when available",
    )
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable validation output"
    )
    args = parser.parse_args()

    if args.min_task_count > args.task_count:
        parser.error("--min-task-count cannot be greater than --task-count")

    path = (
        Path(args.file).expanduser()
        if args.file
        else resolve_data_dir(args.data_dir) / "tasks" / "today.md"
    )
    if not path.is_absolute():
        path = Path.cwd() / path

    require_doc_task = args.require_doc_task or truthy(
        os.environ.get("PERSONAL_PM_REQUIRE_DOC_TASK", "")
    )
    errors = validate(
        path,
        args.task_count,
        args.min_task_count,
        args.allow_planner_maintenance,
        check_date=not args.skip_date_check,
        require_doc_task=require_doc_task,
    )
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
