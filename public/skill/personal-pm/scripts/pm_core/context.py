"""Read-only freshness signals; the host reconciles them with the conversation."""

import re
from datetime import date, timedelta


def planning_context(plan, weekly, days, as_of):
    today = date.fromisoformat(as_of)

    def age(value):
        try:
            return (today - date.fromisoformat(value)).days
        except (TypeError, ValueError):
            return None

    plan_date = (plan or {}).get("date")
    weekly_date = (weekly or {}).get("week_of")
    recorded_dates = [day.day for day in days] + ([plan_date] if plan_date else [])
    valid_dates = [value for value in recorded_dates if age(value) is not None and age(value) >= 0]
    last_recorded = max(valid_dates, default=None)
    gap = age(last_recorded)
    weekly_age = age(weekly_date)
    reasons = []
    if gap is not None and gap >= 7:
        reasons.append(
            "No plan or archived outcome recorded in at least 7 days; refresh current priorities."
        )
    if weekly_age is not None and weekly_age >= 14:
        reasons.append(
            "Weekly focus is at least 14 days old; confirm relevance without requiring weekly setup."
        )
    if any(age(value) is not None and age(value) < 0 for value in (plan_date, weekly_date)):
        reasons.append("A planning date is in the future; check it before rollover or replacement.")
    candidates = []
    for index, task in enumerate((plan or {}).get("tasks", [])):
        if task["checked"] or task["meta"].get("status", "").lower() in {
            "canceled",
            "cancelled",
            "deleted",
            "cancel",
            "delete",
            "removed",
        }:
            continue
        backlog = re.fullmatch(r"(\d+)d", task["meta"].get("backlog", ""))
        task_age = (int(backlog[1]) if backlog else 0) + max(age(plan_date) or 0, 0)
        if task_age >= 14:
            candidates.append({"task_index": index, "title": task["title"], "age_days": task_age})
    monday = today - timedelta(days=today.weekday())
    return {
        "as_of": as_of,
        "last_recorded_date": last_recorded,
        "recording_gap_days": gap,
        "weekly_stale": weekly_age is None or weekly_age > (today - monday).days,
        "refresh_needed": bool(reasons),
        "reasons": reasons,
        "carry_forward_to_review": candidates,
        "note": "Dates describe planner records, not work performed. Current conversation and explicit corrections take precedence; goal and project relevance still need judgment.",
    }
