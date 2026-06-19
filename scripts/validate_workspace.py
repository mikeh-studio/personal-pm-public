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
VALIDATE_TODAY_PATH = (
    REPO_ROOT / "public" / "skill" / "personal-pm" / "scripts" / "validate_today.py"
)

REQUIRED_FILES = [
    "goals/goal.md",
    "goals/projects.md",
    "context/weekly-focus.md",
    "context/planner-memory.md",
    "context/daily-outcomes.md",
    "context/planning-insights.md",
    "context/weekly-outcomes.md",
    "tasks/today.md",
    "tasks/backlog.md",
    "tasks/archive/log.md",
    "data/task_log.csv",
]

GITHUB_SYNC_ALLOWED_CONFIG_KEYS = {
    "repo",
    "project_owner",
    "project_owner_type",
    "project_number",
    "tasks",
    "projects",
    "map_path",
}

GITHUB_SYNC_BLOCKED_CONFIG_KEYS = {
    "allow_public_project",
    "allow_public_repo",
    "auth",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
}

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

PLACEHOLDER_RE = re.compile(
    r"^(tbd|todo|placeholder|none|n/a|na|\[.*\]|\{\{.*\}\})$", re.IGNORECASE
)


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
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL
    )
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
        for key in (
            "matched_goals",
            "matched_projects",
            "matched_keywords",
            "key_points",
            "action_items",
        ):
            if key in doc and not isinstance(doc[key], list):
                errors.append(
                    f"context/recent-drive-docs.json: doc {index} field '{key}' must be a list"
                )
    return errors


def validate_summary_cache(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"data/google_docs_summary_cache.json: invalid JSON ({exc})"]
    if not isinstance(payload, dict):
        return ["data/google_docs_summary_cache.json: expected a JSON object"]
    if payload.get("contains_raw_bodies") is not False:
        return ["data/google_docs_summary_cache.json: contains_raw_bodies must be false"]
    entries = payload.get("entries", {})
    if not isinstance(entries, dict):
        return ["data/google_docs_summary_cache.json: expected 'entries' to be an object"]
    errors = []
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            errors.append(f"data/google_docs_summary_cache.json: entry {key!r} is not an object")
            continue
        if not str(entry.get("title", "")).strip():
            errors.append(f"data/google_docs_summary_cache.json: entry {key!r} missing title")
        for list_key in (
            "key_points",
            "action_items",
            "matched_goals",
            "matched_projects",
            "matched_keywords",
        ):
            if list_key in entry and not isinstance(entry[list_key], list):
                errors.append(
                    f"data/google_docs_summary_cache.json: entry {key!r} field '{list_key}' must be a list"
                )
    return errors


def validate_ingest_key_index(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"data/google_docs_ingest_keys.json: invalid JSON ({exc})"]
    if not isinstance(payload, dict):
        return ["data/google_docs_ingest_keys.json: expected a JSON object"]
    keys = payload.get("keys", {})
    if not isinstance(keys, dict):
        return ["data/google_docs_ingest_keys.json: expected 'keys' to be an object"]
    errors = []
    for key, entry in keys.items():
        if not isinstance(entry, dict):
            errors.append(f"data/google_docs_ingest_keys.json: entry {key!r} is not an object")
            continue
        if not str(entry.get("activity_date", "")).strip():
            errors.append(f"data/google_docs_ingest_keys.json: entry {key!r} missing activity_date")
        if not (str(entry.get("id", "")).strip() or str(entry.get("url", "")).strip()):
            errors.append(f"data/google_docs_ingest_keys.json: entry {key!r} missing id or url")
    return errors


def validate_github_sync_config(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"config/github_sync.json: invalid JSON ({exc})"]
    if not isinstance(payload, dict):
        return ["config/github_sync.json: expected a JSON object"]

    errors = []
    data_dir = path.parent.parent.resolve()
    for key in payload:
        normalized = str(key).strip().lower()
        if (
            normalized in GITHUB_SYNC_BLOCKED_CONFIG_KEYS
            or "token" in normalized
            or "secret" in normalized
        ):
            errors.append(
                f"config/github_sync.json: key '{key}' is not allowed; keep auth in gh"
            )
        elif normalized not in GITHUB_SYNC_ALLOWED_CONFIG_KEYS:
            allowed = ", ".join(sorted(GITHUB_SYNC_ALLOWED_CONFIG_KEYS))
            errors.append(
                f"config/github_sync.json: unsupported key '{key}'; allowed keys: {allowed}"
            )

    repo = str(payload.get("repo", "") or "").strip()
    if repo and not re.fullmatch(r"[^/\s]+/[^/\s]+", repo):
        errors.append("config/github_sync.json: repo must use OWNER/REPO form")

    project_owner_type = str(payload.get("project_owner_type", "") or "").strip()
    if project_owner_type and project_owner_type not in {"user", "org"}:
        errors.append("config/github_sync.json: project_owner_type must be user or org")

    tasks = str(payload.get("tasks", "") or "").strip()
    if tasks and tasks not in {"none", "durable", "all"}:
        errors.append("config/github_sync.json: tasks must be none, durable, or all")

    projects = str(payload.get("projects", "") or "").strip()
    if projects and projects not in {"none", "open", "all"}:
        errors.append("config/github_sync.json: projects must be none, open, or all")

    if "project_number" in payload:
        try:
            int(payload["project_number"])
        except (TypeError, ValueError):
            errors.append("config/github_sync.json: project_number must be an integer")

    map_path = str(payload.get("map_path", "") or "").strip()
    if map_path:
        candidate = Path(map_path).expanduser()
        if not candidate.is_absolute():
            candidate = data_dir / candidate
        resolved_candidate = candidate.resolve()
        if not resolved_candidate.is_relative_to(data_dir):
            errors.append("config/github_sync.json: map_path must stay under the data root")

    return errors


def validate_workspace(
    data_dir: Path,
    task_count: int,
    min_task_count: int,
    strict_today: bool,
    template_mode: bool = False,
) -> list[str]:
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
    if goal_path.exists() and not template_mode:
        errors.extend(validate_goal_file(goal_path))

    ledger_path = data_dir / "data" / "task_log.csv"
    if ledger_path.exists():
        errors.extend(validate_ledger(ledger_path))

    archive_path = data_dir / "tasks" / "archive" / "log.md"
    if archive_path.exists():
        errors.extend(validate_archive(archive_path))

    recent_docs_path = data_dir / "context" / "recent-drive-docs.json"
    errors.extend(validate_recent_drive_docs(recent_docs_path))

    summary_cache_path = data_dir / "data" / "google_docs_summary_cache.json"
    errors.extend(validate_summary_cache(summary_cache_path))

    ingest_key_index_path = data_dir / "data" / "google_docs_ingest_keys.json"
    errors.extend(validate_ingest_key_index(ingest_key_index_path))

    github_sync_config_path = data_dir / "config" / "github_sync.json"
    errors.extend(validate_github_sync_config(github_sync_config_path))

    today_path = data_dir / "tasks" / "today.md"
    if today_path.exists() and not template_mode:
        validator = load_validate_today()
        errors.extend(
            f"tasks/today.md: {error}"
            for error in validator.validate(
                today_path,
                task_count,
                min_task_count,
                allow_planner_maintenance=True,
                check_date=strict_today,
            )
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only compatibility check for a Personal PM data root."
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PERSONAL_PM_DATA_DIR", ""),
        help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="Accepted for explicitness; this command never writes",
    )
    parser.add_argument(
        "--strict-today", action="store_true", help="Require tasks/today.md to use today's date"
    )
    parser.add_argument(
        "--template",
        action="store_true",
        help="Validate blank starter layout without requiring live goals or a dated plan",
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
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable validation output"
    )
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    if args.min_task_count > args.task_count:
        parser.error("--min-task-count cannot be greater than --task-count")

    errors = validate_workspace(
        data_dir,
        args.task_count,
        args.min_task_count,
        args.strict_today,
        template_mode=args.template,
    )
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
