#!/usr/bin/env python3

import argparse
import csv
import os
import re
from pathlib import Path


CSV_FIELDS = [
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

TASK_TYPES = {
    "interview_prep",
    "project_work",
    "skill_practice",
    "research",
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

TASK_LINE_RE = re.compile(
    r"^- \[(?P<done>[ xX])\]\s*"
    r"(?:(?:\[(?P<priority_bracket>P[123])\])|(?P<priority_plain>P[123]))?\s*"
    r"(?:(?:\[(?P<duration>\d+)m\])|(?P<duration_plain>\d+)m)?\s*"
    r"(?P<body>.+?)\s*$"
)


def resolve_data_dir(value: str | None = None) -> Path:
    raw_value = (value or "").strip()
    if not raw_value:
        raw_value = "private"

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def normalize_token(value: str) -> str:
    token = value.strip().lower()
    token = token.replace("&", "and")
    token = re.sub(r"[^a-z0-9]+", "_", token)
    token = re.sub(r"_+", "_", token).strip("_")
    return token


def normalize_task_type(value: str) -> str:
    aliases = {
        "interview": "interview_prep",
        "interview_prep": "interview_prep",
        "project_work": "project_work",
        "project": "project_work",
        "skill_practice": "skill_practice",
        "skill": "skill_practice",
        "research": "research",
        "career": "career",
        "writing": "writing",
        "design": "design_exploration",
        "design_exploration": "design_exploration",
    }
    token = aliases.get(normalize_token(value), normalize_token(value))
    if token not in TASK_TYPES:
        raise ValueError(f"Unsupported task_type: {value}")
    return token


def normalize_goal(value: str) -> str:
    aliases = {
        "data_owner": "data_owner",
        "data": "data_owner",
        "experience_design": "experience_design",
        "design": "experience_design",
    }
    token = aliases.get(normalize_token(value), normalize_token(value))
    if token not in GOALS:
        raise ValueError(f"Unsupported goal: {value}")
    return token


def normalize_sub_category(value: str) -> str:
    aliases = {
        "decision_science": "decision_science",
        "data_foundation": "data_foundation",
        "evaluation": "evaluation_discipline",
        "evaluation_discipline": "evaluation_discipline",
        "service_platform_eng": "service_platform_eng",
        "service_platform_engineering": "service_platform_eng",
        "service_platform": "service_platform_eng",
        "website": "website",
        "writing": "writing",
        "physical_ai": "physical_ai",
        "career": "career_assets",
        "career_assets": "career_assets",
    }
    token = aliases.get(normalize_token(value), normalize_token(value))
    if token not in SUB_CATEGORIES:
        raise ValueError(f"Unsupported sub_category: {value}")
    return token


def parse_archive_sections(text: str):
    current_date = None
    in_final_tasks = False
    section_lines = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_date and section_lines:
                yield current_date, section_lines
            current_date = line.replace("## ", "", 1).strip()
            in_final_tasks = False
            section_lines = []
            continue
        if current_date is None:
            continue
        if line.startswith("### Final Tasks"):
            in_final_tasks = True
            continue
        if line.startswith("### ") and in_final_tasks:
            in_final_tasks = False
            continue
        if in_final_tasks and line.startswith("- ["):
            section_lines.append(line)

    if current_date and section_lines:
        yield current_date, section_lines


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


def split_task_and_project(main_text: str):
    if " — " in main_text:
        task_text, project = main_text.split(" — ", 1)
        return task_text.strip(), project.strip()
    if ":" in main_text and main_text.lower().startswith("side project"):
        return main_text.strip(), "Side project"
    return main_text.strip(), ""


def infer_task_type(task_text: str, project: str) -> str:
    combined = f"{task_text} {project}".lower()

    if any(term in combined for term in ["apply to", "application", "role", "completed coding interview", "coding interview"]):
        return "career"
    if any(term in combined for term in ["interview prep", "mock case", "timed case", "behavioral", "star story", "assessment test", "case study"]):
        return "interview_prep"
    if any(term in combined for term in ["writeup", "blog topic", "weekly writeup"]):
        return "writing"
    if any(term in combined for term in ["read one current piece", "research-report", "guide", "suggested reads"]):
        return "research"
    if any(term in combined for term in ["collect 2 reference artifacts", "experience design exploration"]):
        return "design_exploration"
    if any(term in combined for term in ["python", "sql", "drill", "exercise", "practice", "learn figma basics"]):
        return "skill_practice"
    return "project_work"


def infer_sub_category(task_text: str, project: str, task_type: str) -> str:
    combined = f"{task_text} {project}".lower()

    if task_type == "career":
        return "career_assets"
    if any(term in combined for term in ["physical ai", "ai + experience design exploration"]):
        return "physical_ai"
    if any(term in combined for term in ["website", "figma", "project stories", "launch checklist", "content scope", "homepage", "case-study section"]):
        return "website"
    if task_type == "writing" or "writeup" in combined or "blog topic" in combined:
        return "writing"
    if any(term in combined for term in ["labeling", "eval", "evaluation discipline", "grading", "trace grading"]):
        return "evaluation_discipline"
    if any(term in combined for term in ["python", "sql", "data foundation", "analytics exercise", "skill practice"]):
        return "data_foundation"
    if any(term in combined for term in ["service-platform eng", "service / platform", "parser", "api", "queue", "retries"]):
        return "service_platform_eng"
    return "decision_science"


def infer_goal(project: str, sub_category: str) -> str:
    project_lower = project.lower()
    if sub_category in {"website", "physical_ai"}:
        return "experience_design"
    if "experience design" in project_lower or "personal website" in project_lower or "figma" in project_lower:
        return "experience_design"
    return "data_owner"


def parse_task_line(line: str, date: str, source: str):
    match = TASK_LINE_RE.match(line.strip())
    if not match:
        return None

    done = match.group("done").lower() == "x"
    priority = match.group("priority_bracket") or match.group("priority_plain") or ""
    duration = match.group("duration") or match.group("duration_plain") or ""
    body = match.group("body").strip()

    main_text, metadata = split_metadata(body)
    task_text, project = split_task_and_project(main_text)

    if not done:
        return None

    task_type = normalize_task_type(metadata["type"]) if "type" in metadata else infer_task_type(task_text, project)
    sub_category = normalize_sub_category(metadata["sub"]) if "sub" in metadata else infer_sub_category(task_text, project, task_type)
    goal = normalize_goal(metadata["goal"]) if "goal" in metadata else infer_goal(project, sub_category)

    return {
        "date": date,
        "task_text": task_text,
        "completed": "true",
        "priority": priority,
        "task_type": task_type,
        "goal": goal,
        "sub_category": sub_category,
        "project": project,
        "duration_minutes": duration,
        "source": source,
        "source_date": date,
    }


def ensure_ledger(ledger_path: Path):
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    if ledger_path.exists():
        return
    with ledger_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()


def load_existing_keys(ledger_path: Path):
    if not ledger_path.exists():
        return set()
    with ledger_path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        return {(row["source_date"], row["task_text"]) for row in reader}


def append_rows(ledger_path: Path, rows):
    ensure_ledger(ledger_path)
    existing = load_existing_keys(ledger_path)
    new_rows = [row for row in rows if (row["source_date"], row["task_text"]) not in existing]
    if not new_rows:
        return 0
    with ledger_path.open("a", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writerows(new_rows)
    return len(new_rows)


def rows_from_archive(archive_path: Path, source: str, only_date: str = ""):
    text = archive_path.read_text()
    rows = []
    for section_date, lines in parse_archive_sections(text):
        if only_date and section_date != only_date:
            continue
        for line in lines:
            row = parse_task_line(line, section_date, source)
            if row:
                rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description="Build and maintain the structured personal PM task ledger.")
    parser.add_argument("--data-dir", default="", help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/")
    parser.add_argument("--archive", default="", help="Archive log path. Defaults to DATA_DIR/tasks/archive/log.md")
    parser.add_argument("--ledger", default="", help="Task ledger path. Defaults to DATA_DIR/data/task_log.csv")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("ensure-ledger")
    backfill = subparsers.add_parser("backfill-archive")
    backfill.add_argument("--source", default="archive_backfill")
    append_date = subparsers.add_parser("append-date")
    append_date.add_argument("--date", required=True)
    append_date.add_argument("--source", default="archive_rollover")

    args = parser.parse_args()
    data_dir = resolve_data_dir(args.data_dir or os.environ.get("PERSONAL_PM_DATA_DIR", ""))
    archive_path = Path(args.archive).expanduser() if args.archive else data_dir / "tasks" / "archive" / "log.md"
    ledger_path = Path(args.ledger).expanduser() if args.ledger else data_dir / "data" / "task_log.csv"
    if not archive_path.is_absolute():
        archive_path = Path.cwd() / archive_path
    if not ledger_path.is_absolute():
        ledger_path = Path.cwd() / ledger_path

    if args.command == "ensure-ledger":
        ensure_ledger(ledger_path)
        print(f"Ensured ledger at {ledger_path}")
        return

    if not archive_path.exists():
        raise SystemExit(f"Archive file not found: {archive_path}")

    if args.command == "backfill-archive":
        rows = rows_from_archive(archive_path, args.source)
        added = append_rows(ledger_path, rows)
        print(f"Backfilled {added} completed tasks into {ledger_path}")
        return

    if args.command == "append-date":
        rows = rows_from_archive(archive_path, args.source, only_date=args.date)
        added = append_rows(ledger_path, rows)
        print(f"Appended {added} completed tasks for {args.date} into {ledger_path}")
        return


if __name__ == "__main__":
    main()
