#!/usr/bin/env python3

import argparse
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

TASK_LINE_RE = re.compile(
    r"^- \[(?P<done>[ xX])\]\s*"
    r"(?:(?:\[(?P<priority_bracket>P[123])\])|(?P<priority_plain>P[123]))?\s*"
    r"(?:(?:\[(?P<duration>\d+)m\])|(?P<duration_plain>\d+)m)?\s*"
    r"(?P<body>.+?)\s*$"
)

CANCELED_STATUSES = {"cancel", "canceled", "cancelled"}
DELETED_STATUSES = {"delete", "deleted", "removed"}


@dataclass
class ArchiveTask:
    line: str
    title: str
    checked: bool
    status: str
    priority: str
    duration_minutes: int
    metadata: dict[str, str]

    @property
    def active(self) -> bool:
        return self.status in {"completed", "incomplete"}


@dataclass
class ArchiveDay:
    day: str
    tasks: list[ArchiveTask]
    notes: list[str]

    @property
    def completed(self) -> list[ArchiveTask]:
        return [task for task in self.tasks if task.status == "completed"]

    @property
    def incomplete(self) -> list[ArchiveTask]:
        return [task for task in self.tasks if task.status == "incomplete"]

    @property
    def deleted_canceled(self) -> list[ArchiveTask]:
        return [task for task in self.tasks if task.status in {"deleted", "canceled"}]

    @property
    def active_planned_count(self) -> int:
        return len(self.completed) + len(self.incomplete)

    @property
    def original_planned_count(self) -> int:
        return self.active_planned_count + len(self.deleted_canceled)

    @property
    def completion_rate(self) -> int:
        if self.active_planned_count == 0:
            return 0
        return round(len(self.completed) / self.active_planned_count * 100)

    @property
    def planned_minutes(self) -> int:
        return sum(task.duration_minutes for task in self.tasks if task.active)

    @property
    def completed_minutes(self) -> int:
        return sum(task.duration_minutes for task in self.completed)


def resolve_data_dir(value: str | None = None) -> Path:
    raw_value = (value or os.environ.get("PERSONAL_PM_DATA_DIR", "")).strip()
    if not raw_value:
        raw_value = "private"

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    return path.resolve()


def split_metadata(body: str) -> tuple[str, dict[str, str]]:
    parts = [part.strip() for part in body.split(" | ")]
    main = parts[0]
    metadata: dict[str, str] = {}
    for part in parts[1:]:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        metadata[key.strip().lower()] = value.strip()
    return main, metadata


def visible_title(main_text: str) -> str:
    title = main_text.split(" \u2014 ", 1)[0].strip()
    return re.sub(r"\s+", " ", title)


def normalize_status(value: str) -> str:
    token = value.strip().lower()
    token = re.sub(r"[^a-z]+", "_", token).strip("_")
    if token in CANCELED_STATUSES:
        return "canceled"
    if token in DELETED_STATUSES:
        return "deleted"
    return ""


def normalize_bucket(value: str) -> str:
    token = value.strip().lower()
    token = token.replace("&", "and")
    token = re.sub(r"[^a-z0-9]+", "_", token)
    return re.sub(r"_+", "_", token).strip("_") or "unknown"


def status_for_task(checked: bool, metadata: dict[str, str], section_status: str = "") -> str:
    metadata_status = normalize_status(metadata.get("status", ""))
    if metadata_status:
        return metadata_status
    if section_status:
        return section_status
    return "completed" if checked else "incomplete"


def parse_task_line(line: str, section_status: str = "") -> ArchiveTask | None:
    match = TASK_LINE_RE.match(line.strip())
    if not match:
        return None

    checked = match.group("done").lower() == "x"
    priority = match.group("priority_bracket") or match.group("priority_plain") or ""
    duration = match.group("duration") or match.group("duration_plain") or "0"
    body = match.group("body").strip()
    main_text, metadata = split_metadata(body)

    return ArchiveTask(
        line=line.strip(),
        title=visible_title(main_text),
        checked=checked,
        status=status_for_task(checked, metadata, section_status),
        priority=priority,
        duration_minutes=int(duration),
        metadata=metadata,
    )


def section_status_from_heading(heading: str) -> str:
    normalized = heading.strip().lower()
    if "deleted" in normalized or "removed" in normalized:
        return "deleted"
    if "canceled" in normalized or "cancelled" in normalized:
        return "canceled"
    return ""


def section_blocks(body: str):
    matches = list(re.finditer(r"^###\s+(.+?)\s*$", body, re.MULTILINE))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        yield match.group(1).strip(), body[start:end]


def bullet_lines(section_text: str) -> list[str]:
    lines = []
    for line in section_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            lines.append(stripped[2:].strip())
    return lines


def parse_archive(text: str) -> list[ArchiveDay]:
    days = []
    matches = list(re.finditer(r"^##\s+(\d{4}-\d{2}-\d{2})\s*$", text, re.MULTILINE))

    for index, match in enumerate(matches):
        day = match.group(1)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end]
        tasks: list[ArchiveTask] = []
        notes: list[str] = []

        for heading, section_text in section_blocks(body):
            lower_heading = heading.lower()
            if lower_heading.startswith("final tasks"):
                for line in section_text.splitlines():
                    if not line.strip().startswith("- ["):
                        continue
                    task = parse_task_line(line)
                    if task:
                        tasks.append(task)
                continue

            section_status = section_status_from_heading(heading)
            if section_status:
                for line in section_text.splitlines():
                    if not line.strip().startswith("- ["):
                        continue
                    task = parse_task_line(line, section_status)
                    if task:
                        tasks.append(task)
                continue

            if lower_heading.startswith("planning notes"):
                notes.extend(bullet_lines(section_text))

        days.append(ArchiveDay(day=day, tasks=tasks, notes=notes))

    days.sort(key=lambda item: item.day)
    return days


def consecutive_zero_completion_days(days: list[ArchiveDay]) -> int:
    count = 0
    for archived_day in reversed(days):
        if archived_day.active_planned_count == 0:
            continue
        if archived_day.completed:
            break
        count += 1
    return count


def recent_window(days: list[ArchiveDay], count: int) -> list[ArchiveDay]:
    if count <= 0:
        return days
    return days[-count:]


def dimension_stats(days: list[ArchiveDay], key: str):
    planned: Counter[str] = Counter()
    completed: Counter[str] = Counter()
    incomplete: Counter[str] = Counter()

    for archived_day in days:
        for task in archived_day.tasks:
            if not task.active:
                continue
            value = normalize_bucket(task.metadata.get(key, "unknown"))
            planned[value] += 1
            if task.status == "completed":
                completed[value] += 1
            else:
                incomplete[value] += 1

    rows = []
    for value in sorted(planned):
        total = planned[value]
        done = completed[value]
        missed = incomplete[value]
        rows.append(
            {
                "value": value,
                "planned": total,
                "completed": done,
                "incomplete": missed,
                "rate": round(done / total * 100) if total else 0,
            }
        )
    return rows


def best_rows(rows, limit: int = 4):
    useful_rows = [row for row in rows if row["value"] != "unknown"] or rows
    return sorted(
        useful_rows, key=lambda row: (row["completed"], row["rate"], -row["planned"]), reverse=True
    )[:limit]


def friction_rows(rows, limit: int = 4):
    useful_rows = [row for row in rows if row["value"] != "unknown"] or rows
    return sorted(
        useful_rows, key=lambda row: (row["incomplete"], row["planned"], -row["rate"]), reverse=True
    )[:limit]


def adaptive_rule(days: list[ArchiveDay]) -> tuple[str, int, int]:
    if not days:
        return (
            "No archived outcomes yet; use the normal 5-task plan until real completion data exists.",
            5,
            180,
        )

    latest = days[-1]
    recent = recent_window(days, 7)
    recent_active = sum(day.active_planned_count for day in recent)
    recent_completed = sum(len(day.completed) for day in recent)
    recent_rate = round(recent_completed / recent_active * 100) if recent_active else 0
    zero_streak = consecutive_zero_completion_days(days)

    if latest.active_planned_count and not latest.completed:
        if zero_streak >= 2:
            return (
                "Latest archived day completed 0 active tasks and the zero-completion streak is "
                f"{zero_streak} days. Document this as difficulty completing large task sets; "
                "make the next plan at most 3 active tasks, at most 75 planned minutes, and keep P1 at 35 minutes or less.",
                3,
                75,
            )
        return (
            "Latest archived day completed 0 active tasks. Document this as difficulty completing large tasks; "
            "reduce the next plan to at most 4 active tasks or 90 planned minutes, with a smaller first artifact.",
            4,
            90,
        )

    if recent_rate < 40 and recent_active:
        return (
            f"Recent 7-archive completion rate is {recent_rate}%. Keep the next plan at most 4 active tasks "
            "or reduce planned minutes by about 25%.",
            4,
            120,
        )

    return (
        f"Recent 7-archive completion rate is {recent_rate}%. A normal 5-task plan is acceptable if P3 tasks remain optional.",
        5,
        180,
    )


def format_task_titles(tasks: list[ArchiveTask], limit: int = 8) -> list[str]:
    if not tasks:
        return ["None."]

    rendered = []
    for task in tasks[:limit]:
        pieces = []
        if task.priority:
            pieces.append(task.priority)
        if task.duration_minutes:
            pieces.append(f"{task.duration_minutes}m")
        type_value = normalize_bucket(task.metadata.get("type", ""))
        sub_value = normalize_bucket(task.metadata.get("sub", ""))
        if type_value != "unknown":
            pieces.append(f"type:{type_value}")
        if sub_value != "unknown":
            pieces.append(f"sub:{sub_value}")
        suffix = f" ({', '.join(pieces)})" if pieces else ""
        rendered.append(f"{task.title}{suffix}")
    if len(tasks) > limit:
        rendered.append(f"... plus {len(tasks) - limit} more.")
    return rendered


def format_dimension_rows(rows) -> list[str]:
    if not rows:
        return ["No typed task history yet."]
    return [
        f"{row['value']}: {row['completed']}/{row['planned']} completed ({row['rate']}%)"
        for row in rows
        if row["planned"]
    ] or ["No typed task history yet."]


def build_planning_insights(days: list[ArchiveDay], recent_days_count: int) -> str:
    recent = recent_window(days, recent_days_count)
    rule_text, max_tasks, max_minutes = adaptive_rule(days)
    zero_streak = consecutive_zero_completion_days(days)
    type_rows = dimension_stats(days, "type")
    sub_rows = dimension_stats(days, "sub")
    recent_active = sum(day.active_planned_count for day in recent)
    recent_completed = sum(len(day.completed) for day in recent)
    recent_deleted_canceled = sum(len(day.deleted_canceled) for day in recent)
    recent_rate = round(recent_completed / recent_active * 100) if recent_active else 0

    lines = [
        "# Planning Insights",
        "",
        "<!--",
        "Generated from tasks/archive/log.md by outcome_memory.py.",
        "The archive remains the source of truth; regenerate this file after rollover.",
        "Treat unchecked tasks as incomplete unless they have status:canceled, status:cancelled, status:deleted,",
        "or appear in a Deleted / Canceled Tasks archive section.",
        "-->",
        "",
    ]

    if days:
        latest = days[-1]
        lines.extend(
            [
                "## Latest Archived Day",
                f"- Date: {latest.day}",
                f"- Active planned tasks: {latest.active_planned_count}",
                f"- Completed tasks: {len(latest.completed)}",
                f"- Incomplete tasks: {len(latest.incomplete)}",
                f"- Deleted / canceled tasks: {len(latest.deleted_canceled)}",
                f"- Completion rate: {latest.completion_rate}%",
                f"- Planned minutes: {latest.planned_minutes}",
                f"- Completed minutes: {latest.completed_minutes}",
                "",
                "Completed:",
            ]
        )
        lines.extend(f"- {task}" for task in format_task_titles(latest.completed))
        lines.extend(["", "Deleted / canceled:"])
        lines.extend(f"- {task}" for task in format_task_titles(latest.deleted_canceled))
        lines.extend(["", "Incomplete:"])
        lines.extend(f"- {task}" for task in format_task_titles(latest.incomplete))
        lines.append("")
    else:
        lines.extend(["## Latest Archived Day", "- No archived outcomes yet.", ""])

    lines.extend(
        [
            "## Adaptive Planning Rule",
            f"- Recommendation: {rule_text}",
            f"- Next-plan active task cap: {max_tasks}",
            f"- Next-plan planned-minute cap: {max_minutes}",
            f"- Current zero-completion streak: {zero_streak}",
            f"- Recent window: last {len(recent)} archived days",
            f"- Recent active planned tasks: {recent_active}",
            f"- Recent completed tasks: {recent_completed}",
            f"- Recent deleted / canceled tasks: {recent_deleted_canceled}",
            f"- Recent completion rate: {recent_rate}%",
            "",
            "## Learned Completion Patterns",
            "Completed more reliably by task type:",
        ]
    )
    lines.extend(f"- {row}" for row in format_dimension_rows(best_rows(type_rows)))
    lines.extend(["", "Higher-friction task types:"])
    lines.extend(f"- {row}" for row in format_dimension_rows(friction_rows(type_rows)))
    lines.extend(["", "Completed more reliably by sub-category:"])
    lines.extend(f"- {row}" for row in format_dimension_rows(best_rows(sub_rows)))
    lines.extend(["", "Higher-friction sub-categories:"])
    lines.extend(f"- {row}" for row in format_dimension_rows(friction_rows(sub_rows)))
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def week_start(day_value: str) -> date:
    parsed = date.fromisoformat(day_value)
    return parsed - timedelta(days=parsed.weekday())


def group_by_week(days: list[ArchiveDay]):
    groups: dict[date, list[ArchiveDay]] = defaultdict(list)
    for archived_day in days:
        groups[week_start(archived_day.day)].append(archived_day)
    return dict(sorted(groups.items(), key=lambda item: item[0]))


def build_week_signal(week_days: list[ArchiveDay]) -> str:
    active_planned = sum(day.active_planned_count for day in week_days)
    completed = sum(len(day.completed) for day in week_days)
    zero_days = sum(1 for day in week_days if day.active_planned_count and not day.completed)
    rate = round(completed / active_planned * 100) if active_planned else 0

    if active_planned and completed == 0:
        return "No active tasks completed this week; next week should reduce task count or total time and make P1 a smaller first artifact."
    if zero_days >= 2:
        return f"{zero_days} zero-completion days this week; use fewer active tasks and treat P3 work as optional."
    if rate < 40 and active_planned:
        return f"Completion rate was {rate}%; reduce scope before adding new lanes."
    return "Completion was enough to keep normal planning, as long as lower-priority tasks stay skippable."


def build_weekly_outcomes(days: list[ArchiveDay], recent_weeks: int) -> str:
    groups = group_by_week(days)
    selected = list(groups.items())[-recent_weeks:] if recent_weeks > 0 else list(groups.items())

    lines = [
        "# Weekly Outcomes",
        "",
        "<!--",
        "Generated from tasks/archive/log.md by outcome_memory.py.",
        "Use this compact rollup before reading long daily outcome history.",
        "Completed tasks are separated from deleted / canceled tasks.",
        "-->",
        "",
    ]

    if not selected:
        lines.extend(["## No Weekly Outcomes Yet", "- No archived outcomes yet.", ""])
        return "\n".join(lines).rstrip() + "\n"

    for monday, week_days in selected:
        week_end = monday + timedelta(days=6)
        active_planned = sum(day.active_planned_count for day in week_days)
        original_planned = sum(day.original_planned_count for day in week_days)
        completed = [task for day in week_days for task in day.completed]
        incomplete = [task for day in week_days for task in day.incomplete]
        deleted_canceled = [task for day in week_days for task in day.deleted_canceled]
        planned_minutes = sum(day.planned_minutes for day in week_days)
        completed_minutes = sum(day.completed_minutes for day in week_days)
        rate = round(len(completed) / active_planned * 100) if active_planned else 0

        lines.extend(
            [
                f"## Week of {monday.isoformat()}",
                f"- Range: {monday.isoformat()} through {week_end.isoformat()}",
                f"- Archived days summarized: {', '.join(day.day for day in week_days)}",
                f"- Original planned tasks: {original_planned}",
                f"- Active planned tasks: {active_planned}",
                f"- Completed tasks: {len(completed)}",
                f"- Incomplete tasks: {len(incomplete)}",
                f"- Deleted / canceled tasks: {len(deleted_canceled)}",
                f"- Completion rate: {rate}%",
                f"- Planned minutes: {planned_minutes}",
                f"- Completed minutes: {completed_minutes}",
                f"- Planning signal: {build_week_signal(week_days)}",
                "",
                "Completed:",
            ]
        )
        lines.extend(f"- {task}" for task in format_task_titles(completed))
        lines.extend(["", "Deleted / canceled:"])
        lines.extend(f"- {task}" for task in format_task_titles(deleted_canceled))
        lines.extend(["", "Incomplete / carried:"])
        lines.extend(f"- {task}" for task in format_task_titles(incomplete))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate adaptive planning memory from the Personal PM archive."
    )
    parser.add_argument(
        "--data-dir",
        default="",
        help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/",
    )
    parser.add_argument(
        "--archive", default="", help="Archive log path. Defaults to DATA_DIR/tasks/archive/log.md"
    )
    parser.add_argument(
        "--planning-insights",
        default="",
        help="Output path. Defaults to DATA_DIR/context/planning-insights.md",
    )
    parser.add_argument(
        "--weekly-outcomes",
        default="",
        help="Output path. Defaults to DATA_DIR/context/weekly-outcomes.md",
    )
    parser.add_argument(
        "--recent-days",
        type=int,
        default=14,
        help="Archived days to summarize in planning insights",
    )
    parser.add_argument(
        "--recent-weeks",
        type=int,
        default=8,
        help="Weeks to include in weekly outcomes; use 0 for all",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print generated files instead of writing them"
    )
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    archive_path = (
        Path(args.archive).expanduser()
        if args.archive
        else data_dir / "tasks" / "archive" / "log.md"
    )
    insights_path = (
        Path(args.planning_insights).expanduser()
        if args.planning_insights
        else data_dir / "context" / "planning-insights.md"
    )
    weekly_path = (
        Path(args.weekly_outcomes).expanduser()
        if args.weekly_outcomes
        else data_dir / "context" / "weekly-outcomes.md"
    )

    for path_name, path in {
        "archive": archive_path,
        "planning-insights": insights_path,
        "weekly-outcomes": weekly_path,
    }.items():
        if not path.is_absolute():
            resolved = Path.cwd() / path
            if path_name == "archive":
                archive_path = resolved
            elif path_name == "planning-insights":
                insights_path = resolved
            else:
                weekly_path = resolved

    archive_text = archive_path.read_text(encoding="utf-8") if archive_path.exists() else ""
    days = parse_archive(archive_text)
    insights_text = build_planning_insights(days, args.recent_days)
    weekly_text = build_weekly_outcomes(days, args.recent_weeks)

    if args.dry_run:
        print(f"--- {insights_path} ---")
        print(insights_text.rstrip())
        print(f"--- {weekly_path} ---")
        print(weekly_text.rstrip())
        return 0

    insights_changed = write_if_changed(insights_path, insights_text)
    weekly_changed = write_if_changed(weekly_path, weekly_text)

    print(
        "Updated outcome memory: "
        f"{len(days)} archived days, "
        f"planning-insights changed={str(insights_changed).lower()}, "
        f"weekly-outcomes changed={str(weekly_changed).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
