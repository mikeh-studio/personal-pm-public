#!/usr/bin/env python3

import argparse
import csv
import importlib.util
import json
import os
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
VALIDATE_TODAY_PATH = REPO_ROOT / "public" / "skill" / "personal-pm" / "scripts" / "validate_today.py"

REQUIRED_FILES = [
    "goals/goal.md",
    "goals/projects.md",
    "context/weekly-focus.md",
    "context/planner-memory.md",
    "context/daily-outcomes.md",
    "tasks/today.md",
    "tasks/backlog.md",
    "tasks/archive/log.md",
    "data/task_log.csv",
]

REQUIRED_GOAL_SECTIONS = [
    "Overall Goals",
    "Current Near-Term Deadlines",
    "Key Disciplines",
    "Suggested Daily Practice",
]

LEDGER_FIELDS = [
    "date",
    "task_text",
    "completed",
    "priority",
    "task_type",
    "goal",
    "sub_category",
    "project",
    "duration_minutes",
    "source",
    "source_date",
]

PLACEHOLDER_RE = re.compile(r"^(tbd|todo|placeholder|none|n/a|na|\[.*\]|\{\{.*\}\})$", re.IGNORECASE)


def resolve_data_dir(value: str | None = None) -> Path:
    raw_value = value if value is not None else os.environ.get("PERSONAL_PM_DATA_DIR", "")
    raw_value = raw_value.strip()
    if not raw_value:
        raw_value = "private"

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def load_validate_today():
    spec = importlib.util.spec_from_file_location("validate_today", VALIDATE_TODAY_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load validator: {VALIDATE_TODAY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def section_body(text: str, heading: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def has_meaningful_content(body: str) -> bool:
    for line in body.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith("|") and ("---" in cleaned or "Discipline Area" in cleaned):
            continue
        cleaned = cleaned.strip("-*`#>| ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and not PLACEHOLDER_RE.match(cleaned):
            return True
    return False


def validate_goal_file(path: Path) -> list[str]:
    errors = []
    text = path.read_text(encoding="utf-8")
    for heading in REQUIRED_GOAL_SECTIONS:
        body = section_body(text, heading)
        if not body:
            errors.append(f"goals/goal.md: missing section '{heading}'")
        elif not has_meaningful_content(body):
            errors.append(f"goals/goal.md: section '{heading}' is placeholder-only")
    return errors


def validate_ledger(path: Path) -> list[str]:
    if not path.exists():
        return [f"Missing required file: {path}"]

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return ["data/task_log.csv: missing CSV header"]

    if header != LEDGER_FIELDS:
        return [f"data/task_log.csv: expected header {LEDGER_FIELDS}, found {header}"]
    return []


def validate_archive(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return []
    if not re.search(r"^##\s+\d{4}-\d{2}-\d{2}", text, re.MULTILINE):
        return ["tasks/archive/log.md: non-empty archive has no dated '## YYYY-MM-DD' entries"]
    return []


def validate_recent_drive_docs(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"context/recent-drive-docs.json: invalid JSON ({exc})"]
    if not isinstance(payload, dict):
        return ["context/recent-drive-docs.json: expected a JSON object"]
    docs = payload.get("docs", [])
    if not isinstance(docs, list):
        return ["context/recent-drive-docs.json: expected 'docs' to be a list"]
    errors = []
    for index, doc in enumerate(docs, start=1):
        if not isinstance(doc, dict):
            errors.append(f"context/recent-drive-docs.json: doc {index} is not an object")
            continue
        if not str(doc.get("title", "")).strip():
            errors.append(f"context/recent-drive-docs.json: doc {index} missing title")
        for key in ("matched_goals", "matched_projects", "matched_keywords"):
            if key in doc and not isinstance(doc[key], list):
                errors.append(f"context/recent-drive-docs.json: doc {index} field '{key}' must be a list")
    return errors


def validate_workspace(data_dir: Path, task_count: int, strict_today: bool) -> list[str]:
    errors = []

    if not data_dir.exists():
        return [f"Data root does not exist: {data_dir}"]
    if not data_dir.is_dir():
        return [f"Data root is not a directory: {data_dir}"]

    for relative_path in REQUIRED_FILES:
        path = data_dir / relative_path
        if not path.exists():
            errors.append(f"Missing required file: {relative_path}")
        elif not path.is_file():
            errors.append(f"Expected file but found non-file path: {relative_path}")

    goal_path = data_dir / "goals" / "goal.md"
    if goal_path.exists():
        errors.extend(validate_goal_file(goal_path))

    ledger_path = data_dir / "data" / "task_log.csv"
    if ledger_path.exists():
        errors.extend(validate_ledger(ledger_path))

    archive_path = data_dir / "tasks" / "archive" / "log.md"
    if archive_path.exists():
        errors.extend(validate_archive(archive_path))

    recent_docs_path = data_dir / "context" / "recent-drive-docs.json"
    errors.extend(validate_recent_drive_docs(recent_docs_path))

    today_path = data_dir / "tasks" / "today.md"
    if today_path.exists():
        validator = load_validate_today()
        errors.extend(
            f"tasks/today.md: {error}"
            for error in validator.validate(
                today_path,
                task_count,
                allow_planner_maintenance=True,
                check_date=strict_today,
            )
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only compatibility check for a Personal PM data root.")
    parser.add_argument("--data-dir", default=os.environ.get("PERSONAL_PM_DATA_DIR", ""), help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/")
    parser.add_argument("--read-only", action="store_true", help="Accepted for explicitness; this command never writes")
    parser.add_argument("--strict-today", action="store_true", help="Require tasks/today.md to use today's date")
    parser.add_argument("--task-count", type=int, default=int(os.environ.get("PERSONAL_PM_TASK_COUNT", "5")))
    parser.add_argument("--json", action="store_true", help="Print machine-readable validation output")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    errors = validate_workspace(data_dir, args.task_count, args.strict_today)
    result = {"ok": not errors, "data_dir": str(data_dir), "errors": errors, "read_only": True}

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif errors:
        print(f"Workspace validation failed for {data_dir}:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
    else:
        print(f"Workspace validation passed for {data_dir}")

    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
