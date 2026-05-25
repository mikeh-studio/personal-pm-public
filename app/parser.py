import csv
import io
import json
import re
import threading
from datetime import datetime, timedelta

from paths import data_dir, data_path

_file_lock = threading.Lock()


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

        result["tasks"].append({
            "checked": checked,
            "priority": priority,
            "duration": duration,
            "title": title,
            "discipline": discipline,
            "meta": meta,
        })

    sections = re.split(r"^### ", text, flags=re.MULTILINE)
    for section in sections:
        lines = section.strip().split("\n")
        header = lines[0].strip().lower() if lines else ""
        bullets = [
            l.lstrip("- ").strip()
            for l in lines[1:]
            if l.strip().startswith("- ") and l.strip() != "-"
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
                    result["feedback"]["did_not_work"] = line.replace("- What did not work:", "").strip()
                elif line.startswith("- New goal or constraint:"):
                    result["feedback"]["new_goal"] = line.replace("- New goal or constraint:", "").strip()

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
            l.lstrip("* ").strip()
            for l in goal_section.group(1).strip().split("\n")
            if l.strip().startswith("*")
        ]

    deadline_section = re.search(r"## Current Near-Term Deadlines\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if deadline_section:
        result["deadlines"] = [
            l.lstrip("* ").strip()
            for l in deadline_section.group(1).strip().split("\n")
            if l.strip().startswith("*")
        ]

    disc_section = re.search(r"## Key Disciplines\s*\n(.*?)(?=\n##|\Z)", text, re.DOTALL)
    if disc_section:
        for row in re.finditer(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", disc_section.group(1)):
            name = row.group(1).strip()
            details = row.group(2).strip()
            if name.lower() not in ("discipline area", "---", "") and not name.startswith("-"):
                result["disciplines"].append({"name": name, "details": details})

    return result


def parse_projects():
    path = data_path("goals", "projects.md")
    if not path.exists():
        return None

    text = path.read_text()
    projects = []

    for row in re.finditer(
        r"\|\s*([^|]+?)\s*\|\s*(Now|Next|Later)\s*\|\s*(Active|Idea|Paused)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|",
        text,
    ):
        projects.append({
            "name": row.group(1).strip(),
            "priority": row.group(2).strip(),
            "status": row.group(3).strip(),
            "discipline": row.group(4).strip(),
            "next_action": row.group(5).strip(),
            "notes": row.group(6).strip(),
        })

    return projects


def parse_weekly_focus():
    path = data_path("context", "weekly-focus.md")
    if not path.exists():
        return None

    text = path.read_text()
    weeks = []

    for m in re.finditer(r"## Week of (\d{4}-\d{2}-\d{2})\n(.*?)(?=\n## |\Z)", text, re.DOTALL):
        date = m.group(1)
        body = m.group(2)
        priorities = re.findall(r"\d+\. \[.\] (.+)", body)
        weeks.append({"week_of": date, "priorities": priorities})

    if not weeks:
        return None
    weeks.sort(key=lambda w: w["week_of"], reverse=True)
    return weeks[0]


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
        entries.append({
            "date": date,
            "completed": completed[:5],
            "takeaway": takeaway_match.group(1).strip() if takeaway_match else "",
        })

    return entries[-7:]


def parse_recent_drive_docs():
    path = data_path("context", "recent-drive-docs.json")
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

        docs.append({
            "id": str(item.get("id", "") or ""),
            "title": str(item.get("title", "") or "Untitled document"),
            "url": str(item.get("url", "") or ""),
            "created_at": str(item.get("created_at", "") or item.get("createdTime", "") or ""),
            "modified_at": str(item.get("modified_at", "") or item.get("modifiedTime", "") or ""),
            "owner": str(item.get("owner", "") or ""),
            "summary": str(item.get("summary", "") or ""),
            "reason": str(item.get("reason", "") or ""),
            "priority_hint": str(item.get("priority_hint", "") or ""),
            "confidence": confidence,
            "matched_goals": [str(v) for v in item.get("matched_goals", []) if v],
            "matched_projects": [str(v) for v in item.get("matched_projects", []) if v],
            "matched_keywords": [str(v) for v in item.get("matched_keywords", []) if v],
        })

    docs.sort(key=lambda d: d.get("created_at") or d.get("modified_at") or "", reverse=True)

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
            start = m.start()
            end = m.end()
            if end < len(text) and text[end] == "\n":
                end += 1
            elif start > 0 and text[start - 1] == "\n":
                start -= 1
            text = text[:start] + text[end:]
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
            text = text[:m.start()] + new_line + text[m.end():]
            path.write_text(text)
            return True
        return False


def get_completion_streak():
    path = data_path("context", "daily-outcomes.md")
    if not path.exists():
        return {"streak": 0, "last_completed": None}

    text = path.read_text()
    dates_with_completions = []

    for m in re.finditer(r"## (\d{4}-\d{2}-\d{2})\n(.*?)(?=\n## |\Z)", text, re.DOTALL):
        date = m.group(1)
        body = m.group(2)
        if "- None." not in body.split("Specific feedback")[0]:
            dates_with_completions.append(date)

    streak = 0
    for d in reversed(dates_with_completions):
        streak += 1

    return {
        "streak": streak,
        "total_days": len(re.findall(r"## \d{4}-\d{2}-\d{2}", text)),
        "completion_days": len(dates_with_completions),
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

        result["tasks"].append({
            "checked": checked,
            "priority": priority,
            "duration": duration,
            "title": title,
            "discipline": discipline,
            "meta": meta,
        })

    for section in re.split(r"^### ", body, flags=re.MULTILINE):
        lines = section.strip().split("\n")
        header = lines[0].strip().lower() if lines else ""
        if header.startswith("planning notes"):
            result["carry_forward"] = [
                l.lstrip("- ").strip()
                for l in lines[1:]
                if l.strip().startswith("- ") and l.strip() != "-"
            ]

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
        completed = 0
        by_priority = {"P1": {"planned": 0, "completed": 0}, "P2": {"planned": 0, "completed": 0}, "P3": {"planned": 0, "completed": 0}}
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

            pkey = f"P{priority}"
            if pkey not in by_priority:
                by_priority[pkey] = {"planned": 0, "completed": 0}

            planned += 1
            by_priority[pkey]["planned"] += 1
            total_planned_minutes += duration

            if checked:
                completed += 1
                by_priority[pkey]["completed"] += 1
                total_completed_minutes += duration

                sub = meta.get("sub", "other")
                by_sub[sub] = by_sub.get(sub, 0) + 1

                ttype = meta.get("type", "other")
                by_type[ttype] = by_type.get(ttype, 0) + 1

        days.append({
            "date": date,
            "planned": planned,
            "completed": completed,
            "completion_rate": round(completed / planned * 100) if planned > 0 else 0,
            "by_priority": by_priority,
            "by_sub": by_sub,
            "by_type": by_type,
            "planned_minutes": total_planned_minutes,
            "completed_minutes": total_completed_minutes,
        })

    days.sort(key=lambda d: d["date"])
    return days


def parse_task_log_stats():
    """Parse task_log.csv to get completed task breakdowns."""
    path = data_path("data", "task_log.csv")
    if not path.exists():
        return {"by_sub": {}, "by_type": {}, "by_goal": {}, "by_priority": {}, "total": 0, "tasks": []}

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

        tasks.append({
            "date": date,
            "sub": sub,
            "type": ttype,
            "goal": goal,
            "priority": priority,
            "duration": duration,
        })

    return {
        "by_sub": by_sub,
        "by_type": by_type,
        "by_goal": by_goal,
        "by_priority": by_priority,
        "total": len(tasks),
        "tasks": tasks,
    }


def get_analytics_90d():
    """Combine archive and task log data for the last 90 days."""
    archive_days = parse_archive_daily_stats()
    task_log = parse_task_log_stats()

    cutoff = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    recent_days = [d for d in archive_days if d["date"] >= cutoff]

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
    total_completed = sum(d["completed"] for d in recent_days)
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
            "total_planned": total_planned,
            "total_completed": total_completed,
            "overall_completion_rate": round(total_completed / total_planned * 100) if total_planned > 0 else 0,
            "days_with_completions": days_with_completions,
            "days_with_zero": days_with_zero,
            "avg_planned_per_day": round(total_planned / len(recent_days), 1) if recent_days else 0,
            "avg_completed_per_day": round(total_completed / len(recent_days), 1) if recent_days else 0,
            "total_planned_hours": round(total_planned_min / 60, 1),
            "total_completed_hours": round(total_completed_min / 60, 1),
            "by_sub": agg_sub,
            "by_type": agg_type,
        },
        "task_log": task_log,
    }
