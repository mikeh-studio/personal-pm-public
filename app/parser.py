import csv
import io
import json
import re
import threading
from datetime import datetime, timedelta

from paths import data_path

_file_lock = threading.Lock()

PROJECT_PRIORITIES = {"Now", "Next", "Later"}
PROJECT_STATUSES = {"Active", "Idea", "Paused", "Closed"}
CANCELED_STATUSES = {"cancel", "canceled", "cancelled"}
DELETED_STATUSES = {"delete", "deleted", "removed"}
PROJECT_ROW_RE = re.compile(
    r"^\|\s*([^|\n]+?)\s*\|\s*(Now|Next|Later)\s*\|\s*(Active|Idea|Paused|Closed)\s*\|\s*([^|\n]*?)\s*\|\s*([^|\n]*?)\s*\|\s*([^|\n]*?)\s*\|\s*$",
    re.MULTILINE,
)
WEEKLY_FOCUS_RE = re.compile(
    r"^## Week of (?P<week_of>\d{4}-\d{2}-\d{2})\s*\n(?P<body>.*?)(?=^## Week of \d{4}-\d{2}-\d{2}\s*$|\Z)",
    re.MULTILINE | re.DOTALL,
)
WEEKLY_PRIORITY_RE = re.compile(r"^\s*(?P<number>\d+)\.\s+\[(?P<checked>[ xX])\]\s*(?P<text>.*)$")


def current_week_of():
    """Monday of the current week as YYYY-MM-DD (mirrors the JS defaultWeekOf)."""
    today = datetime.now()
    monday = today - timedelta(days=today.weekday())
    return monday.strftime("%Y-%m-%d")


def split_metadata(body: str):
    parts = [part.strip() for part in body.split(" | ")]
    main = parts[0]
    meta = {}
    for part in parts[1:]:
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        meta[key.strip()] = value.strip()
    return main, meta


def _normalized_metadata_value(meta, key):
    for meta_key, value in meta.items():
        if str(meta_key).strip().lower() == key:
            return str(value).strip()
    return ""


def _normalize_status(value):
    token = str(value or "").strip().lower()
    token = re.sub(r"[^a-z]+", "_", token).strip("_")
    if token in CANCELED_STATUSES:
        return "canceled"
    if token in DELETED_STATUSES:
        return "deleted"
    return ""


def _archive_task_status(checked, meta, section_status=""):
    metadata_status = _normalize_status(_normalized_metadata_value(meta, "status"))
    if metadata_status:
        return metadata_status
    if section_status:
        return section_status
    return "completed" if checked else "incomplete"


def _archive_section_status(header):
    normalized = str(header or "").strip().lower()
    if "deleted" in normalized or "removed" in normalized:
        return "deleted"
    if "canceled" in normalized or "cancelled" in normalized:
        return "canceled"
    return ""


def parse_today():
    path = data_path("tasks", "today.md")
    if not path.exists():
        return None

    text = path.read_text()
    result = {
        "raw": text,
        "date": None,
        "tasks": [],
        "carry_forward": [],
        "heads_up": [],
        "feedback": {"worked": "", "did_not_work": "", "new_goal": ""},
    }

    date_match = re.search(r"## (\d{4}-\d{2}-\d{2})", text)
    if date_match:
        result["date"] = date_match.group(1)

    task_pattern = re.compile(
        r"- \[([ xX])\] "
        r"\[P(\d)\] "
        r"\[(\d+m)\] "
        r"(.+)"
    )

    for m in task_pattern.finditer(text):
        checked = m.group(1).lower() == "x"
        priority = int(m.group(2))
        duration = m.group(3)
        rest = m.group(4)

        title_part, meta = split_metadata(rest)
        parts = title_part.rsplit(" — ", 1)
        title = parts[0].strip()
        discipline = parts[1].strip() if len(parts) > 1 else ""

        result["tasks"].append(
            {
                "checked": checked,
                "priority": priority,
                "duration": duration,
                "title": title,
                "discipline": discipline,
                "meta": meta,
            }
        )

    sections = re.split(r"^### ", text, flags=re.MULTILINE)
    for section in sections:
        lines = section.strip().split("\n")
        header = lines[0].strip().lower() if lines else ""
        bullets = [
            line.lstrip("- ").strip()
            for line in lines[1:]
            if line.strip().startswith("- ") and line.strip() != "-"
        ]

        if header == "carry-forward":
            result["carry_forward"] = bullets
        elif header.startswith("heads-up"):
            result["heads_up"] = bullets
        elif header.startswith("feedback"):
            for line in lines[1:]:
                line = line.strip()
                if line.startswith("- What worked:"):
                    result["feedback"]["worked"] = line.replace("- What worked:", "").strip()
                elif line.startswith("- What did not work:"):
                    result["feedback"]["did_not_work"] = line.replace(
                        "- What did not work:", ""
                    ).strip()
                elif line.startswith("- New goal or constraint:"):
                    result["feedback"]["new_goal"] = line.replace(
                        "- New goal or constraint:", ""
                    ).strip()

    return result


def parse_goals():
    path = data_path("goals", "goal.md")
    if not path.exists():
        return None
    text = path.read_text()

    result = {"overall_goals": [], "deadlines": [], "disciplines": []}

    goal_section = re.search(r"## Overall Goals\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if goal_section:
        result["overall_goals"] = [
            line.lstrip("* ").strip()
            for line in goal_section.group(1).strip().split("\n")
            if line.strip().startswith("*")
        ]

    deadline_section = re.search(
        r"## Current Near-Term Deadlines\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL
    )
    if deadline_section:
        result["deadlines"] = [
            line.lstrip("* ").strip()
            for line in deadline_section.group(1).strip().split("\n")
            if line.strip().startswith("*")
        ]

    disc_section = re.search(r"## Key Disciplines\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if disc_section:
        for row in re.finditer(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", disc_section.group(1)):
            name = row.group(1).strip()
            details = row.group(2).strip()
            if name.lower() not in ("discipline area", "---", "") and not name.startswith("-"):
                result["disciplines"].append({"name": name, "details": details})

    return result


def _sanitize_goal_items(goals):
    items = []
    for goal in goals or []:
        text = re.sub(r"\s+", " ", str(goal or "").replace("\n", " ")).strip()
        text = text.lstrip("*-• ").strip()
        if text:
            items.append(text[:300])
        if len(items) >= 12:
            break
    return items


def set_overall_goals(goals):
    """Create or replace the ## Overall Goals section in goals/goal.md, preserving the rest."""
    items = _sanitize_goal_items(goals)
    if not items:
        return False, "Add at least one goal."

    body = "## Overall Goals\n" + "\n".join(f"* {goal}" for goal in items) + "\n"

    with _file_lock:
        path = data_path("goals", "goal.md")
        if path.exists():
            text = path.read_text()
            pattern = re.compile(r"## Overall Goals[^\n]*\n.*?(?=\n## |\Z)", re.DOTALL)
            if pattern.search(text):
                new_text = pattern.sub(lambda _m: body.rstrip("\n") + "\n", text, count=1)
            else:
                new_text = body + "\n" + text.lstrip("\n")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            new_text = body

        path.write_text(new_text.rstrip("\n") + "\n")
        return True, ""


def parse_projects():
    path = data_path("goals", "projects.md")
    if not path.exists():
        return None

    text = path.read_text()
    projects = []

    for index, row in enumerate(PROJECT_ROW_RE.finditer(text)):
        projects.append(
            {
                "index": index,
                "name": row.group(1).strip(),
                "priority": row.group(2).strip(),
                "status": row.group(3).strip(),
                "discipline": row.group(4).strip(),
                "next_action": row.group(5).strip(),
                "notes": row.group(6).strip(),
            }
        )

    return projects


def _clean_project_cell(value):
    value = str(value or "")
    value = value.replace("|", "/").replace("\n", " ").replace("\r", " ")
    return re.sub(r"\s+", " ", value).strip()


def _normalize_project(name, priority, status, discipline="", next_action="", notes=""):
    project = {
        "name": _clean_project_cell(name),
        "priority": _clean_project_cell(priority),
        "status": _clean_project_cell(status),
        "discipline": _clean_project_cell(discipline),
        "next_action": _clean_project_cell(next_action),
        "notes": _clean_project_cell(notes),
    }

    if not project["name"]:
        return None, "Project name is required."
    if project["priority"] not in PROJECT_PRIORITIES:
        return None, "Priority must be Now, Next, or Later."
    if project["status"] not in PROJECT_STATUSES:
        return None, "Status must be Active, Idea, Paused, or Closed."
    return project, ""


def _build_project_line(project):
    return (
        f"| {project['name']} | {project['priority']} | {project['status']} | "
        f"{project['discipline']} | {project['next_action']} | {project['notes']} |"
    )


def _project_matches(text):
    return list(PROJECT_ROW_RE.finditer(text))


def project_daily_flow_partition(projects=None):
    items = projects if projects is not None else parse_projects()
    active = [p for p in items if p.get("status") not in {"Paused", "Closed"}]
    paused = [p for p in items if p.get("status") == "Paused"]
    closed = [p for p in items if p.get("status") == "Closed"]
    return {"eligible": active, "paused": paused, "closed": closed}


def _find_project_insert_pos(text):
    matches = _project_matches(text)
    if matches:
        return matches[-1].end()

    offset = 0
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines[:-1]):
        header = line.lower()
        separator = lines[i + 1]
        if (
            "priority" in header
            and "status" in header
            and "next action" in header
            and "notes" in header
            and "---" in separator
        ):
            return offset + len(line) + len(separator)
        offset += len(line)
    return None


def add_project(name, priority, status, discipline="", next_action="", notes=""):
    project, error = _normalize_project(name, priority, status, discipline, next_action, notes)
    if error:
        return False, error

    with _file_lock:
        path = data_path("goals", "projects.md")
        if not path.exists():
            return False, "goals/projects.md not found."

        text = path.read_text()
        insert_pos = _find_project_insert_pos(text)
        if insert_pos is None:
            return False, "Project table not found in goals/projects.md."

        new_line = _build_project_line(project)
        prefix = "" if insert_pos > 0 and text[insert_pos - 1] == "\n" else "\n"
        suffix = (
            "" if insert_pos < len(text) and text[insert_pos : insert_pos + 1] == "\n" else "\n"
        )
        text = text[:insert_pos] + prefix + new_line + suffix + text[insert_pos:]
        path.write_text(text)
        return True, ""


def edit_project(
    project_index: int, name, priority, status, discipline="", next_action="", notes=""
):
    project, error = _normalize_project(name, priority, status, discipline, next_action, notes)
    if error:
        return False, error
    try:
        project_index = int(project_index)
    except (TypeError, ValueError):
        return False, "Project index is out of range."

    with _file_lock:
        path = data_path("goals", "projects.md")
        if not path.exists():
            return False, "goals/projects.md not found."

        text = path.read_text()
        matches = _project_matches(text)
        if not 0 <= project_index < len(matches):
            return False, "Project index is out of range."

        match = matches[project_index]
        text = text[: match.start()] + _build_project_line(project) + text[match.end() :]
        path.write_text(text)
        return True, ""


def delete_project(project_index: int):
    try:
        project_index = int(project_index)
    except (TypeError, ValueError):
        return False, "Project index is out of range."

    with _file_lock:
        path = data_path("goals", "projects.md")
        if not path.exists():
            return False, "goals/projects.md not found."

        text = path.read_text()
        matches = _project_matches(text)
        if not 0 <= project_index < len(matches):
            return False, "Project index is out of range."

        match = matches[project_index]
        start = match.start()
        end = match.end()
        if end < len(text) and text[end] == "\n":
            end += 1
        elif start > 0 and text[start - 1] == "\n":
            start -= 1
        text = text[:start] + text[end:]
        path.write_text(text)
        return True, ""


def _weekly_focus_matches(text):
    return list(WEEKLY_FOCUS_RE.finditer(text))


def _parse_weekly_focus_match(match, index):
    body = match.group("body").strip("\n")
    why = ""
    priorities = []
    notes = []
    in_notes = False

    for line in body.splitlines():
        stripped = line.strip()
        why_match = re.match(r"^\*\*Why this week:\*\*\s*(.*)$", stripped)
        if why_match:
            why = why_match.group(1).strip()
            continue

        priority_match = WEEKLY_PRIORITY_RE.match(line)
        if priority_match:
            text = priority_match.group("text").strip()
            if not text:
                continue
            priorities.append(
                {
                    "number": int(priority_match.group("number")),
                    "checked": priority_match.group("checked").lower() == "x",
                    "text": text,
                }
            )
            continue

        if stripped.lower().startswith("### notes"):
            in_notes = True
            continue
        if stripped.startswith("**Carry-over"):
            in_notes = True

        if in_notes:
            notes.append(line.rstrip())

    while notes and not notes[0].strip():
        notes.pop(0)
    while notes and not notes[-1].strip():
        notes.pop()

    priority_items = sorted(priorities, key=lambda item: item["number"])
    return {
        "index": index,
        "week_of": match.group("week_of"),
        "why": why,
        "priorities": [item["text"] for item in priority_items],
        "priority_items": priority_items,
        "notes": "\n".join(notes).strip(),
        "raw": match.group(0).strip(),
    }


def parse_weekly_focus():
    path = data_path("context", "weekly-focus.md")
    if not path.exists():
        return None

    text = path.read_text()
    weeks = [
        _parse_weekly_focus_match(match, index)
        for index, match in enumerate(_weekly_focus_matches(text))
    ]

    if not weeks:
        return None
    weeks.sort(key=lambda w: w["week_of"], reverse=True)
    latest = dict(weeks[0])
    latest["weeks"] = weeks
    return latest


def _clean_weekly_text(value, multiline=False):
    value = str(value or "").replace("\r", "")
    if multiline:
        return "\n".join(line.rstrip() for line in value.splitlines()).strip()
    value = value.replace("\n", " ")
    return re.sub(r"\s+", " ", value).strip()


def _normalize_weekly_focus(week_of, why="", priorities=None, notes=""):
    week_of = _clean_weekly_text(week_of)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", week_of):
        return None, "Week date must use YYYY-MM-DD."

    priority_items = []
    for item in priorities or []:
        if isinstance(item, dict):
            text = item.get("text", "")
            checked = bool(item.get("checked", False))
        else:
            text = item
            checked = False
        text = _clean_weekly_text(text)
        if not text:
            continue
        priority_items.append({"number": len(priority_items) + 1, "checked": checked, "text": text})

    if not priority_items:
        return None, "Add at least one priority."

    return {
        "week_of": week_of,
        "why": _clean_weekly_text(why),
        "priority_items": priority_items,
        "notes": _clean_weekly_text(notes, multiline=True),
    }, ""


def _build_weekly_focus_section(week):
    lines = [f"## Week of {week['week_of']}"]
    if week.get("why"):
        lines.extend(["", f"**Why this week:** {week['why']}"])
    lines.append("")
    for index, item in enumerate(week.get("priority_items", []), start=1):
        checked = "x" if item.get("checked") else " "
        lines.append(f"{index}. [{checked}] {item['text']}")
    if week.get("notes"):
        lines.extend(["", "### Notes", ""])
        lines.extend(week["notes"].splitlines())
    return "\n".join(lines).rstrip() + "\n"


def _weekly_focus_prefix(text, matches):
    if matches:
        return text[: matches[0].start()].rstrip() + "\n\n"
    return (text.rstrip() + "\n\n") if text.strip() else "# Weekly Focus\n\n"


def _write_weekly_focus_sections(path, prefix, weeks):
    body = "\n".join(_build_weekly_focus_section(week).rstrip() for week in weeks).rstrip()
    text = prefix.rstrip() + ("\n\n" + body if body else "") + "\n"
    path.write_text(text)


def ensure_weekly_focus_file():
    """Create context/weekly-focus.md with a heading if it does not exist yet."""
    path = data_path("context", "weekly-focus.md")
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Weekly Focus\n")
    return path


def add_weekly_focus(week_of, why="", priorities=None, notes=""):
    week, error = _normalize_weekly_focus(week_of, why, priorities, notes)
    if error:
        return False, error

    with _file_lock:
        path = data_path("context", "weekly-focus.md")
        if not path.exists():
            return False, "context/weekly-focus.md not found."

        text = path.read_text()
        matches = _weekly_focus_matches(text)
        weeks = [_parse_weekly_focus_match(match, index) for index, match in enumerate(matches)]
        if any(existing["week_of"] == week["week_of"] for existing in weeks):
            return False, "A weekly focus for that date already exists."
        weeks.append(week)
        weeks.sort(key=lambda item: item["week_of"], reverse=True)
        _write_weekly_focus_sections(path, _weekly_focus_prefix(text, matches), weeks)
        return True, ""


def edit_weekly_focus(week_index, week_of, why="", priorities=None, notes=""):
    week, error = _normalize_weekly_focus(week_of, why, priorities, notes)
    if error:
        return False, error
    try:
        week_index = int(week_index)
    except (TypeError, ValueError):
        return False, "Weekly focus index is out of range."

    with _file_lock:
        path = data_path("context", "weekly-focus.md")
        if not path.exists():
            return False, "context/weekly-focus.md not found."

        text = path.read_text()
        matches = _weekly_focus_matches(text)
        weeks = [_parse_weekly_focus_match(match, index) for index, match in enumerate(matches)]
        if not 0 <= week_index < len(weeks):
            return False, "Weekly focus index is out of range."
        if any(
            existing["week_of"] == week["week_of"] and existing["index"] != week_index
            for existing in weeks
        ):
            return False, "A weekly focus for that date already exists."
        weeks = [week if existing["index"] == week_index else existing for existing in weeks]
        weeks.sort(key=lambda item: item["week_of"], reverse=True)
        _write_weekly_focus_sections(path, _weekly_focus_prefix(text, matches), weeks)
        return True, ""


def delete_weekly_focus(week_index):
    try:
        week_index = int(week_index)
    except (TypeError, ValueError):
        return False, "Weekly focus index is out of range."

    with _file_lock:
        path = data_path("context", "weekly-focus.md")
        if not path.exists():
            return False, "context/weekly-focus.md not found."

        text = path.read_text()
        matches = _weekly_focus_matches(text)
        weeks = [_parse_weekly_focus_match(match, index) for index, match in enumerate(matches)]
        if not 0 <= week_index < len(weeks):
            return False, "Weekly focus index is out of range."
        weeks = [week for week in weeks if week["index"] != week_index]
        weeks.sort(key=lambda item: item["week_of"], reverse=True)
        _write_weekly_focus_sections(path, _weekly_focus_prefix(text, matches), weeks)
        return True, ""


def parse_daily_outcomes():
    path = data_path("context", "daily-outcomes.md")
    if not path.exists():
        return []

    text = path.read_text()
    entries = []

    for m in re.finditer(r"## (\d{4}-\d{2}-\d{2})\n(.*?)(?=\n## |\Z)", text, re.DOTALL):
        date = m.group(1)
        body = m.group(2)
        completed = re.findall(r"^\s+- (.+)$", body, re.MULTILINE)
        takeaway_match = re.search(r"Planning takeaway:\s*(.+)", body)
        entries.append(
            {
                "date": date,
                "completed": completed[:5],
                "takeaway": takeaway_match.group(1).strip() if takeaway_match else "",
            }
        )

    return entries[-7:]


def parse_recent_drive_docs():
    path = data_path("context", "recent-drive-docs.json")

    def string_list(value):
        if isinstance(value, list):
            return [str(v) for v in value if v]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    if not path.exists():
        return {
            "generated_at": None,
            "lookback_days": None,
            "source": "not_configured",
            "missing": True,
            "summary": {
                "total": 0,
                "high_confidence": 0,
                "actionable": 0,
                "goals": {},
                "projects": {},
            },
            "docs": [],
        }

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "generated_at": None,
            "lookback_days": None,
            "source": "invalid_cache",
            "missing": False,
            "error": f"Invalid recent-drive-docs.json: {exc}",
            "summary": {
                "total": 0,
                "high_confidence": 0,
                "actionable": 0,
                "goals": {},
                "projects": {},
            },
            "docs": [],
        }

    if isinstance(raw, list):
        raw = {"docs": raw}
    if not isinstance(raw, dict):
        raw = {"docs": []}

    docs = []
    for item in raw.get("docs", []):
        if not isinstance(item, dict):
            continue
        confidence = item.get("confidence", 0)
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0

        docs.append(
            {
                "id": str(item.get("id", "") or ""),
                "title": str(item.get("title", "") or "Untitled document"),
                "url": str(item.get("url", "") or ""),
                "created_at": str(item.get("created_at", "") or item.get("createdTime", "") or ""),
                "modified_at": str(
                    item.get("modified_at", "") or item.get("modifiedTime", "") or ""
                ),
                "activity_at": str(item.get("activity_at", "") or ""),
                "activity_date": str(item.get("activity_date", "") or ""),
                "owner": str(item.get("owner", "") or ""),
                "summary": str(item.get("summary", "") or ""),
                "key_points": string_list(item.get("key_points", [])),
                "action_items": string_list(item.get("action_items", [])),
                "reason": str(item.get("reason", "") or ""),
                "priority_hint": str(item.get("priority_hint", "") or ""),
                "confidence": confidence,
                "matched_goals": string_list(item.get("matched_goals", [])),
                "matched_projects": string_list(item.get("matched_projects", [])),
                "matched_keywords": string_list(item.get("matched_keywords", [])),
            }
        )

    docs.sort(
        key=lambda d: d.get("activity_at") or d.get("created_at") or d.get("modified_at") or "",
        reverse=True,
    )

    goals = {}
    projects = {}
    actionable = 0
    high_confidence = 0
    for doc in docs:
        if doc["priority_hint"]:
            actionable += 1
        if doc["confidence"] >= 0.75:
            high_confidence += 1
        for goal in doc["matched_goals"]:
            goals[goal] = goals.get(goal, 0) + 1
        for project in doc["matched_projects"]:
            projects[project] = projects.get(project, 0) + 1

    return {
        "generated_at": raw.get("generated_at"),
        "run_date": raw.get("run_date"),
        "lookback_days": raw.get("lookback_days"),
        "source": raw.get("source", "cache"),
        "missing": False,
        "summary": {
            "total": len(docs),
            "high_confidence": high_confidence,
            "actionable": actionable,
            "goals": goals,
            "projects": projects,
        },
        "docs": docs,
    }


def toggle_task(task_index: int):
    with _file_lock:
        path = data_path("tasks", "today.md")
        text = path.read_text()

        task_pattern = re.compile(r"- \[([ xX])\] \[P\d\] \[\d+m\]")
        matches = list(task_pattern.finditer(text))

        if 0 <= task_index < len(matches):
            m = matches[task_index]
            current = m.group(1)
            new_state = " " if current.lower() == "x" else "x"
            text = text[: m.start(1)] + new_state + text[m.end(1) :]
            path.write_text(text)
            return True
        return False


def update_feedback(field: str, value: str):
    with _file_lock:
        path = data_path("tasks", "today.md")
        text = path.read_text()

        field_map = {
            "worked": "What worked:",
            "did_not_work": "What did not work:",
            "new_goal": "New goal or constraint:",
        }

        label = field_map.get(field)
        if not label:
            return False

        pattern = re.compile(rf"(- {re.escape(label)})\s*.*$", re.MULTILINE)
        replacement = rf"\1 {value}"
        new_text = pattern.sub(replacement, text)
        if new_text != text:
            path.write_text(new_text)
            return True
        return False


def _build_task_line(priority, duration, title, discipline, meta):
    meta_parts = [f"{k}:{v}" for k, v in (meta or {}).items() if v]
    meta_str = " | " + " | ".join(meta_parts) if meta_parts else ""
    disc_str = f" — {discipline}" if discipline else ""
    return f"- [ ] [P{priority}] [{duration}m] {title}{disc_str}{meta_str}"


def _task_line_with_status(line: str, status: str):
    match = re.match(
        r"^- \[[ xX]\] \[P(?P<priority>\d)\] \[(?P<duration>\d+)m\] (?P<rest>.+)$",
        line.strip(),
    )
    if not match:
        return None

    title_part, meta = split_metadata(match.group("rest"))
    meta = {k: v for k, v in meta.items() if k.strip().lower() != "status"}
    meta["status"] = status
    meta_str = " | " + " | ".join(f"{k}:{v}" for k, v in meta.items() if v)
    return f"- [ ] [P{match.group('priority')}] [{match.group('duration')}m] {title_part}{meta_str}"


def _find_tasks_range(text):
    """Return (start, end) character offsets of the task lines block in today.md."""
    task_pattern = re.compile(r"^- \[[ xX]\] \[P\d\] \[\d+m\] .+$", re.MULTILINE)
    matches = list(task_pattern.finditer(text))
    if not matches:
        return None, None
    return matches[0].start(), matches[-1].end()


def add_task(priority, duration, title, discipline="", meta=None):
    with _file_lock:
        path = data_path("tasks", "today.md")
        text = path.read_text()

        new_line = _build_task_line(priority, duration, title, discipline, meta or {})

        task_pattern = re.compile(r"^- \[[ xX]\] \[P\d\] \[\d+m\] .+$", re.MULTILINE)
        matches = list(task_pattern.finditer(text))

        if matches:
            insert_pos = matches[-1].end()
            text = text[:insert_pos] + "\n" + new_line + text[insert_pos:]
        else:
            tasks_header = re.search(r"^### Tasks\s*$", text, re.MULTILINE)
            if tasks_header:
                insert_pos = tasks_header.end()
                text = text[:insert_pos] + "\n" + new_line + text[insert_pos:]
            else:
                return False

        path.write_text(text)
        return True


def delete_task(task_index: int):
    with _file_lock:
        path = data_path("tasks", "today.md")
        text = path.read_text()

        task_pattern = re.compile(r"^- \[[ xX]\] \[P\d\] \[\d+m\] .+$", re.MULTILINE)
        matches = list(task_pattern.finditer(text))

        if 0 <= task_index < len(matches):
            m = matches[task_index]
            new_line = _task_line_with_status(m.group(0), "canceled")
            if not new_line:
                return False
            text = text[: m.start()] + new_line + text[m.end() :]
            path.write_text(text)
            return True
        return False


def edit_task(task_index: int, priority, duration, title, discipline="", meta=None):
    with _file_lock:
        path = data_path("tasks", "today.md")
        text = path.read_text()

        task_pattern = re.compile(r"^- \[([ xX])\] \[P\d\] \[\d+m\] .+$", re.MULTILINE)
        matches = list(task_pattern.finditer(text))

        if 0 <= task_index < len(matches):
            m = matches[task_index]
            checked = m.group(1)
            meta_str = ""
            if meta:
                meta_str = " | " + " | ".join(f"{k}:{v}" for k, v in meta.items() if v)
            disc_str = f" — {discipline}" if discipline else ""
            new_line = f"- [{checked}] [P{priority}] [{duration}m] {title}{disc_str}{meta_str}"
            text = text[: m.start()] + new_line + text[m.end() :]
            path.write_text(text)
            return True
        return False


def get_completion_streak():
    days = parse_archive_daily_stats()
    if not days:
        return {"streak": 0, "total_days": 0, "completion_days": 0, "last_completed": None}

    completion_days = [day for day in days if day.get("completed", 0) > 0]
    streak = 0
    for day in reversed(days):
        if day.get("completed", 0) <= 0:
            break
        streak += 1

    return {
        "streak": streak,
        "total_days": len(days),
        "completion_days": len(completion_days),
        "last_completed": completion_days[-1]["date"] if completion_days else None,
    }


def get_available_dates():
    """Return dates (last 30 days) that have data in archive or today.md."""
    cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    dates = set()

    archive_path = data_path("tasks", "archive", "log.md")
    if archive_path.exists():
        for m in re.finditer(r"^## (\d{4}-\d{2}-\d{2})", archive_path.read_text(), re.MULTILINE):
            if m.group(1) >= cutoff:
                dates.add(m.group(1))

    today_path = data_path("tasks", "today.md")
    if today_path.exists():
        m = re.search(r"## (\d{4}-\d{2}-\d{2})", today_path.read_text())
        if m and m.group(1) >= cutoff:
            dates.add(m.group(1))

    return sorted(dates, reverse=True)


def parse_archive_day(date_str):
    """Parse a single archived day into the same shape as parse_today()."""
    archive_path = data_path("tasks", "archive", "log.md")
    if not archive_path.exists():
        return None

    text = archive_path.read_text()
    pattern = re.compile(
        rf"## {re.escape(date_str)}\n(.*?)(?=\n## \d{{4}}-\d{{2}}-\d{{2}}|\Z)",
        re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return None

    body = m.group(1)
    result = {
        "date": date_str,
        "tasks": [],
        "deleted_canceled": [],
        "carry_forward": [],
        "heads_up": [],
        "feedback": {"worked": "", "did_not_work": "", "new_goal": ""},
        "archived": True,
    }

    task_pattern = re.compile(
        r"- \[([ xX])\] "
        r"(?:\[?P(\d)\]?\s*)"
        r"(?:\[(\d+)m\]\s*)?"
        r"(.+)"
    )
    tasks_section = ""
    for section in re.split(r"^### ", body, flags=re.MULTILINE):
        if section.strip().lower().startswith("final tasks"):
            tasks_section = section
            break

    for t in task_pattern.finditer(tasks_section):
        checked = t.group(1).lower() == "x"
        priority = int(t.group(2)) if t.group(2) else 0
        duration = f"{t.group(3)}m" if t.group(3) else ""
        rest = t.group(4)

        title_part, meta = split_metadata(rest)
        parts = title_part.rsplit(" — ", 1)
        title = parts[0].strip()
        discipline = parts[1].strip() if len(parts) > 1 else ""
        status = _archive_task_status(checked, meta)

        task_payload = {
            "checked": checked,
            "priority": priority,
            "duration": duration,
            "title": title,
            "discipline": discipline,
            "meta": meta,
            "status": status,
        }
        if status in {"deleted", "canceled"}:
            result["deleted_canceled"].append(task_payload)
        else:
            result["tasks"].append(task_payload)

    for section in re.split(r"^### ", body, flags=re.MULTILINE):
        lines = section.strip().split("\n")
        header = lines[0].strip().lower() if lines else ""
        section_status = _archive_section_status(header)
        if header.startswith("planning notes"):
            result["carry_forward"] = [
                line.lstrip("- ").strip()
                for line in lines[1:]
                if line.strip().startswith("- ") and line.strip() != "-"
            ]
        elif section_status:
            for t in task_pattern.finditer(section):
                checked = t.group(1).lower() == "x"
                priority = int(t.group(2)) if t.group(2) else 0
                duration = f"{t.group(3)}m" if t.group(3) else ""
                rest = t.group(4)

                title_part, meta = split_metadata(rest)
                parts = title_part.rsplit(" — ", 1)
                title = parts[0].strip()
                discipline = parts[1].strip() if len(parts) > 1 else ""
                status = _archive_task_status(checked, meta, section_status)

                result["deleted_canceled"].append(
                    {
                        "checked": checked,
                        "priority": priority,
                        "duration": duration,
                        "title": title,
                        "discipline": discipline,
                        "meta": meta,
                        "status": status,
                    }
                )

    return result


def parse_archive_daily_stats():
    """Parse the archive log to get per-day planned/completed counts with priority and sub breakdowns."""
    path = data_path("tasks", "archive", "log.md")
    if not path.exists():
        return []

    text = path.read_text()
    days = []

    task_re = re.compile(
        r"- \[([ xX])\] "
        r"(?:\[?P(\d)\]?\s*)"
        r"(?:\[(\d+)m\]\s*)?"
        r"(.+)"
    )
    for m in re.finditer(r"## (\d{4}-\d{2}-\d{2})\n(.*?)(?=\n## |\Z)", text, re.DOTALL):
        date = m.group(1)
        body = m.group(2)

        tasks_section = ""
        for section in re.split(r"^### ", body, flags=re.MULTILINE):
            if section.strip().lower().startswith("final tasks"):
                tasks_section = section
                break

        planned = 0
        original_planned = 0
        completed = 0
        deleted_canceled = 0
        by_priority = {
            "P1": {"planned": 0, "completed": 0},
            "P2": {"planned": 0, "completed": 0},
            "P3": {"planned": 0, "completed": 0},
        }
        by_sub = {}
        by_type = {}
        total_planned_minutes = 0
        total_completed_minutes = 0

        for t in task_re.finditer(tasks_section):
            checked = t.group(1).lower() == "x"
            priority = t.group(2) or "0"
            duration = int(t.group(3)) if t.group(3) else 0
            rest = t.group(4)

            _, meta = split_metadata(rest)
            status = _archive_task_status(checked, meta)
            original_planned += 1
            if status in {"deleted", "canceled"}:
                deleted_canceled += 1
                continue

            pkey = f"P{priority}"
            if pkey not in by_priority:
                by_priority[pkey] = {"planned": 0, "completed": 0}

            planned += 1
            by_priority[pkey]["planned"] += 1
            total_planned_minutes += duration

            if status == "completed":
                completed += 1
                by_priority[pkey]["completed"] += 1
                total_completed_minutes += duration

                sub = meta.get("sub", "other")
                by_sub[sub] = by_sub.get(sub, 0) + 1

                ttype = meta.get("type", "other")
                by_type[ttype] = by_type.get(ttype, 0) + 1

        for section in re.split(r"^### ", body, flags=re.MULTILINE):
            lines = section.strip().split("\n")
            header = lines[0].strip().lower() if lines else ""
            section_status = _archive_section_status(header)
            if not section_status:
                continue
            for _task in task_re.finditer(section):
                original_planned += 1
                deleted_canceled += 1

        days.append(
            {
                "date": date,
                "original_planned": original_planned,
                "planned": planned,
                "completed": completed,
                "deleted_canceled": deleted_canceled,
                "completion_rate": round(completed / planned * 100) if planned > 0 else 0,
                "by_priority": by_priority,
                "by_sub": by_sub,
                "by_type": by_type,
                "planned_minutes": total_planned_minutes,
                "completed_minutes": total_completed_minutes,
            }
        )

    days.sort(key=lambda d: d["date"])
    return days


def parse_task_log_stats():
    """Parse task_log.csv to get completed task breakdowns."""
    path = data_path("data", "task_log.csv")
    if not path.exists():
        return {
            "by_sub": {},
            "by_type": {},
            "by_goal": {},
            "by_priority": {},
            "total": 0,
            "tasks": [],
        }

    text = path.read_text()
    reader = csv.DictReader(io.StringIO(text))

    by_sub = {}
    by_type = {}
    by_goal = {}
    by_priority = {}
    tasks = []

    for row in reader:
        sub = row.get("sub_category", "other")
        ttype = row.get("task_type", "other")
        goal = row.get("goal", "other")
        priority = row.get("priority", "P0")
        date = row.get("date", "")
        duration = int(row.get("duration_minutes", "0") or "0")

        by_sub[sub] = by_sub.get(sub, 0) + 1
        by_type[ttype] = by_type.get(ttype, 0) + 1
        by_goal[goal] = by_goal.get(goal, 0) + 1
        by_priority[priority] = by_priority.get(priority, 0) + 1

        tasks.append(
            {
                "date": date,
                "sub": sub,
                "type": ttype,
                "goal": goal,
                "priority": priority,
                "duration": duration,
            }
        )

    return {
        "by_sub": by_sub,
        "by_type": by_type,
        "by_goal": by_goal,
        "by_priority": by_priority,
        "total": len(tasks),
        "tasks": tasks,
    }


def _duration_minutes(value):
    match = re.search(r"\d+", str(value or ""))
    return int(match.group(0)) if match else 0


def current_plan_analytics_preview(archived_dates=None):
    today = parse_today()
    if not today or not today.get("date"):
        return None

    archived_dates = set(archived_dates or [])
    tasks = today.get("tasks") or []
    planned = len(tasks)
    completed_tasks = [task for task in tasks if task.get("checked")]
    completed = len(completed_tasks)
    planned_minutes = sum(_duration_minutes(task.get("duration")) for task in tasks)
    completed_minutes = sum(_duration_minutes(task.get("duration")) for task in completed_tasks)
    by_priority = {
        "P1": {"planned": 0, "completed": 0},
        "P2": {"planned": 0, "completed": 0},
        "P3": {"planned": 0, "completed": 0},
    }
    planned_by_type = {}
    planned_by_sub = {}
    completed_by_type = {}
    completed_by_sub = {}

    for task in tasks:
        pkey = f"P{task.get('priority', 0)}"
        by_priority.setdefault(pkey, {"planned": 0, "completed": 0})
        by_priority[pkey]["planned"] += 1
        meta = task.get("meta") or {}
        sub = meta.get("sub") or "other"
        ttype = meta.get("type") or "other"
        planned_by_sub[sub] = planned_by_sub.get(sub, 0) + 1
        planned_by_type[ttype] = planned_by_type.get(ttype, 0) + 1
        if task.get("checked"):
            by_priority[pkey]["completed"] += 1
            completed_by_sub[sub] = completed_by_sub.get(sub, 0) + 1
            completed_by_type[ttype] = completed_by_type.get(ttype, 0) + 1

    return {
        "date": today["date"],
        "archived": today["date"] in archived_dates,
        "included_in_history": today["date"] in archived_dates,
        "planned": planned,
        "completed": completed,
        "completion_rate": round(completed / planned * 100) if planned else 0,
        "planned_minutes": planned_minutes,
        "completed_minutes": completed_minutes,
        "by_priority": by_priority,
        "planned_by_sub": planned_by_sub,
        "planned_by_type": planned_by_type,
        "completed_by_sub": completed_by_sub,
        "completed_by_type": completed_by_type,
    }


def _parse_run_timestamp(value):
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_agent_run_stats():
    """Parse durable planner run records for Analytics."""
    path = data_path("data", "agent_runs.jsonl")
    runs = []
    by_status = {}
    by_mode = {}

    if not path.exists():
        return {
            "runs": [],
            "summary": {
                "total": 0,
                "successful": 0,
                "failed": 0,
                "skipped": 0,
                "latest": None,
                "by_status": {},
                "by_mode": {},
            },
        }

    cutoff = datetime.now() - timedelta(days=90)

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []

    for line in lines:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue

        started = _parse_run_timestamp(record.get("started_at"))
        if not started or started.replace(tzinfo=None) < cutoff:
            continue

        status = str(record.get("status") or "unknown")
        mode = str(record.get("mode") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        by_mode[mode] = by_mode.get(mode, 0) + 1

        token_usage = (
            record.get("token_usage") if isinstance(record.get("token_usage"), dict) else {}
        )
        runs.append(
            {
                "started_at": record.get("started_at"),
                "ended_at": record.get("ended_at"),
                "date": str(record.get("started_at") or "")[:10],
                "run_id": record.get("run_id"),
                "mode": mode,
                "status": status,
                "exit_code": record.get("exit_code"),
                "focus": record.get("focus"),
                "provider": record.get("provider"),
                "provider_label": record.get("provider_label"),
                "run_type": record.get("run_type"),
                "actions": record.get("actions") if isinstance(record.get("actions"), list) else [],
                "errors": record.get("errors") if isinstance(record.get("errors"), list) else [],
                "total_tokens": token_usage.get("total_tokens", 0),
                "model_calls": token_usage.get("model_calls", 0),
            }
        )

    runs.sort(key=lambda item: str(item.get("started_at") or ""))
    latest = runs[-1] if runs else None

    return {
        "runs": runs,
        "summary": {
            "total": len(runs),
            "successful": by_status.get("success", 0),
            "failed": by_status.get("failed", 0),
            "skipped": by_status.get("skipped", 0),
            "latest": latest,
            "by_status": by_status,
            "by_mode": by_mode,
        },
    }


def get_analytics_90d():
    """Combine archive and task log data for the last 90 days."""
    archive_days = parse_archive_daily_stats()
    task_log = parse_task_log_stats()
    run_history = parse_agent_run_stats()

    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    recent_days = [d for d in archive_days if d["date"] >= cutoff]
    current_plan = current_plan_analytics_preview({day["date"] for day in archive_days})

    # Build per-date breakdowns from task_log.csv (cleaner metadata than archive)
    log_by_date_sub = {}
    log_by_date_type = {}
    for t in task_log["tasks"]:
        d = t["date"]
        sub = t["sub"]
        ttype = t["type"]
        log_by_date_sub.setdefault(d, {})
        log_by_date_sub[d][sub] = log_by_date_sub[d].get(sub, 0) + 1
        log_by_date_type.setdefault(d, {})
        log_by_date_type[d][ttype] = log_by_date_type[d].get(ttype, 0) + 1

    # Overlay task_log data onto archive days where available
    for day in recent_days:
        csv_sub = log_by_date_sub.get(day["date"])
        csv_type = log_by_date_type.get(day["date"])
        if csv_sub:
            day["by_sub"] = csv_sub
        if csv_type:
            day["by_type"] = csv_type

    total_planned = sum(d["planned"] for d in recent_days)
    total_original_planned = sum(d.get("original_planned", d["planned"]) for d in recent_days)
    total_completed = sum(d["completed"] for d in recent_days)
    total_deleted_canceled = sum(d.get("deleted_canceled", 0) for d in recent_days)
    days_with_completions = sum(1 for d in recent_days if d["completed"] > 0)
    days_with_zero = sum(1 for d in recent_days if d["completed"] == 0)

    agg_sub = {}
    agg_type = {}
    for d in recent_days:
        for k, v in d["by_sub"].items():
            agg_sub[k] = agg_sub.get(k, 0) + v
        for k, v in d["by_type"].items():
            agg_type[k] = agg_type.get(k, 0) + v

    total_planned_min = sum(d["planned_minutes"] for d in recent_days)
    total_completed_min = sum(d["completed_minutes"] for d in recent_days)

    return {
        "days": recent_days,
        "summary": {
            "total_days": len(recent_days),
            "total_original_planned": total_original_planned,
            "total_planned": total_planned,
            "total_completed": total_completed,
            "total_deleted_canceled": total_deleted_canceled,
            "overall_completion_rate": round(total_completed / total_planned * 100)
            if total_planned > 0
            else 0,
            "days_with_completions": days_with_completions,
            "days_with_zero": days_with_zero,
            "avg_planned_per_day": round(total_planned / len(recent_days), 1) if recent_days else 0,
            "avg_completed_per_day": round(total_completed / len(recent_days), 1)
            if recent_days
            else 0,
            "total_planned_hours": round(total_planned_min / 60, 1),
            "total_completed_hours": round(total_completed_min / 60, 1),
            "by_sub": agg_sub,
            "by_type": agg_type,
        },
        "task_log": task_log,
        "current_plan": current_plan,
        "run_history": run_history,
    }
