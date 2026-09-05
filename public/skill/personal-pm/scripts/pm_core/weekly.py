"""Weekly coaching contract and validated persistence shared by chat and UI."""

from datetime import date

from .paths import SKILL_DIR, data_path
from .store import (
    add_weekly_focus,
    edit_weekly_focus,
    ensure_weekly_focus_file,
    parse_goals,
    parse_projects,
    parse_weekly_focus,
    project_daily_flow_partition,
)


def build_planner_context():
    goals = parse_goals() or {}
    overall = goals.get("overall_goals") or []
    disciplines = [d.get("name", "") for d in goals.get("disciplines", []) if d.get("name")]

    projects = parse_projects() or []
    active = project_daily_flow_partition(projects)["eligible"]
    project_lines = []
    for p in active[:8]:
        line = f"- {p.get('name', '')} ({p.get('priority', '')}/{p.get('status', '')})"
        if p.get("next_action"):
            line += f" next: {p['next_action']}"
        project_lines.append(line)

    weekly = parse_weekly_focus() or {}
    last_priorities = [
        item.get("text", "") for item in (weekly.get("priority_items") or []) if item.get("text")
    ]

    parts = ["Overall goals:\n" + ("\n".join(f"- {g}" for g in overall) or "- (none set yet)")]
    if goals.get("deadlines"):
        parts.append("Deadlines:\n" + "\n".join(goals["deadlines"]))
    if disciplines:
        parts.append("Key disciplines: " + ", ".join(disciplines))
    parts.append("Active projects:\n" + ("\n".join(project_lines) or "- (none)"))
    if last_priorities:
        parts.append(
            f"Most recent weekly priorities (week of {weekly.get('week_of', '?')}):\n"
            + "\n".join(f"- {t}" for t in last_priorities)
        )
    for name in ("planning-insights.md", "weekly-outcomes.md"):
        path = data_path("context", name)
        if path.exists():
            parts.append(f"{name}:\n{path.read_text(encoding='utf-8')[:6000]}")
    return "\n\n".join(parts)


def _clean_questions(raw):
    cleaned = []
    if not isinstance(raw, list):
        raise ValueError("Questions must be a list.")
    for idx, q in enumerate(raw):
        if not isinstance(q, dict):
            continue
        label = str(q.get("label", "")).strip()
        if not label:
            continue
        help_text = str(q.get("help", "")).strip()[:300]
        placeholder = str(q.get("placeholder", "")).strip()[:200]
        cleaned.append(
            {
                "id": (str(q.get("id") or "").strip() or f"q{idx + 1}"),
                "label": label[:300],
                "help": help_text or "Answer with a concrete outcome, constraint, or decision.",
                "placeholder": placeholder or "What will be true by the end of the week?",
            }
        )
        if len(cleaned) >= 8:
            break
    return cleaned


def _format_answers(answers):
    lines = []
    for item in answers or []:
        if isinstance(item, dict):
            label = str(item.get("label") or item.get("question") or item.get("id") or "").strip()
            answer = str(item.get("answer", "")).strip()
        else:
            label, answer = "", str(item).strip()
        if not answer:
            continue
        lines.append(f"Q: {label}\nA: {answer}" if label else f"A: {answer}")
    return "\n\n".join(lines)


def contract():
    return (SKILL_DIR / "references/weekly-planning.md").read_text(encoding="utf-8")


def questions_prompt(week_of):
    return (
        f"Follow this weekly planning contract:\n{contract()}\n"
        f"Week of {week_of}. Saved user context:\n{build_planner_context()}\n"
        "Generate the UI's 6 to 8 questions. Return ONLY JSON with a questions list; "
        "each question has string id (snake_case), label, help, and placeholder fields."
    )


def focus_prompt(week_of, answers):
    qa = _format_answers(answers)
    if not qa:
        raise ValueError("No answers were provided.")
    return (
        f"Follow this weekly planning contract:\n{contract()}\n"
        f"Week of {week_of}. Saved user context:\n{build_planner_context()}\n"
        f"User answers:\n{qa}\nReturn ONLY the weekly JSON object from the contract."
    )


def save_weekly(week_of, payload, replace=False):
    goals = parse_goals() or {}
    if not goals.get("overall_goals") or any("{{" in g for g in goals["overall_goals"]):
        raise ValueError("Review and save at least one goal first.")
    day = date.fromisoformat(week_of)
    if day.weekday() != 0 or day.isoformat() != week_of:
        raise ValueError("Week date must be a Monday in YYYY-MM-DD format.")
    weekly = payload.get("weekly") if isinstance(payload, dict) else None
    if not isinstance(weekly, dict):
        raise ValueError("Expected a weekly JSON object.")
    priorities = weekly.get("priorities")
    if not isinstance(priorities, list) or not 1 <= len(priorities) <= 4:
        raise ValueError("Weekly focus needs 1 to 4 priorities.")
    fields = [weekly.get("why", ""), weekly.get("notes", ""), *priorities]
    if any(not isinstance(v, str) or len(v) > 4000 or "\x00" in v for v in fields):
        raise ValueError("Weekly fields must be text of at most 4000 characters.")
    if any(not p.strip() for p in priorities):
        raise ValueError("Weekly priorities cannot be empty.")
    # Single lines cannot inject new dated sections or Markdown task structures.
    why, notes = (" ".join(v.split()) for v in fields[:2])
    priorities = [" ".join(p.split()) for p in priorities]
    current = parse_weekly_focus() or {}
    existing = next((w for w in current.get("weeks", []) if w["week_of"] == week_of), None)
    if existing:
        if (existing["why"], existing["priorities"], existing["notes"]) == (why, priorities, notes):
            return {"weekly": current, "goals": parse_goals(), "changed": False}
        if not replace:
            raise ValueError(
                "A weekly focus already exists. Use --replace only for an explicit revision."
            )
        # Preserve checked priorities when the same outcome survives a revision.
        checked = {p["text"]: p["checked"] for p in existing["priority_items"]}
        items = [{"text": p, "checked": checked.get(p, False)} for p in priorities]
        ok, error = edit_weekly_focus(existing["index"], week_of, why, items, notes)
    else:
        ensure_weekly_focus_file()
        ok, error = add_weekly_focus(week_of, why, priorities, notes)
    if not ok:
        raise ValueError(error)
    return {"weekly": parse_weekly_focus(), "goals": parse_goals(), "changed": True}
