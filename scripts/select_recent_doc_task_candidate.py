#!/usr/bin/env python3

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GOALS = {"data_owner", "experience_design"}


def resolve_data_dir(value: str | None = None) -> Path:
    raw_value = value if value is not None else os.environ.get("PERSONAL_PM_DATA_DIR", "")
    raw_value = raw_value.strip() or "private"
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def parse_time(value):
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def string_list(value):
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def load_project_statuses(data_dir: Path) -> dict[str, str]:
    path = data_dir / "goals" / "projects.md"
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    statuses = {}
    row_re = re.compile(
        r"^\|\s*([^|\n]+?)\s*\|\s*(?:Now|Next|Later)\s*\|\s*(Active|Idea|Paused|Closed)\s*\|",
        re.MULTILINE,
    )
    for row in row_re.finditer(text):
        name = row.group(1).strip()
        if name and name != "---":
            statuses[name] = row.group(2).strip()
    return statuses


def active_matched_projects(doc: dict, project_statuses: dict[str, str]) -> list[str]:
    projects = string_list(doc.get("matched_projects"))
    if not project_statuses:
        return projects
    return [
        project
        for project in projects
        if project_statuses.get(project, "Active") not in {"Paused", "Closed"}
    ]


def tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z][a-zA-Z0-9_]{2,}", text.lower()))


def choose_sub(doc: dict) -> str:
    haystack = " ".join(
        [
            str(doc.get("title", "")),
            str(doc.get("summary", "")),
            " ".join(string_list(doc.get("matched_keywords"))),
            " ".join(string_list(doc.get("key_points"))),
        ]
    ).lower()
    tokens = tokenize(haystack)

    if tokens & {
        "metric",
        "metrics",
        "kpi",
        "dashboard",
        "lineage",
        "contract",
        "grain",
        "data_center",
    }:
        return "data_foundation"
    if tokens & {"evaluation", "validation", "quality", "synthetic", "reasoning", "scorecard"}:
        return "evaluation_discipline"
    if tokens & {"robot", "robotics", "nvidia", "nvlink", "gpu", "hardware", "jetson", "physical"}:
        return "physical_ai"
    if tokens & {"agent", "api", "service", "platform", "schema", "template"}:
        return "service_platform_eng"
    if tokens & {"website", "design", "experience", "hri"}:
        return "website"
    return "decision_science"


def choose_task_type(doc: dict, sub: str, project_statuses: dict[str, str] | None = None) -> str:
    projects = active_matched_projects(doc, project_statuses or {})
    if projects:
        return "project_work"
    if sub in {"data_foundation", "evaluation_discipline", "physical_ai", "service_platform_eng"}:
        return "skill_practice"
    return "interview_prep"


def goal_matches(doc: dict) -> list[str]:
    return [goal for goal in string_list(doc.get("matched_goals")) if goal in GOALS]


def score_doc(doc: dict, index: int, project_statuses: dict[str, str] | None = None) -> tuple:
    priority = str(doc.get("priority_hint") or "")
    priority_score = {"P1": 3, "P2": 2, "P3": 1}.get(priority, 0)
    try:
        confidence = float(doc.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0
    has_action = 1 if string_list(doc.get("action_items")) else 0
    has_project = 1 if active_matched_projects(doc, project_statuses or {}) else 0
    activity = (
        parse_time(doc.get("activity_at"))
        or parse_time(doc.get("modified_at"))
        or parse_time(doc.get("created_at"))
    )
    activity_score = activity.timestamp() if activity else 0
    return (priority_score, confidence, has_action, has_project, activity_score, -index)


def load_docs(data_dir: Path) -> tuple[dict, list[dict]]:
    path = data_dir / "context" / "recent-drive-docs.json"
    if not path.exists():
        return {}, []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, []
    if isinstance(payload, list):
        payload = {"docs": payload}
    if not isinstance(payload, dict):
        return {}, []
    docs = [doc for doc in payload.get("docs", []) if isinstance(doc, dict)]
    return payload, docs


def build_candidate(doc: dict, project_statuses: dict[str, str] | None = None) -> dict:
    goals = goal_matches(doc)
    goal = goals[0] if goals else ""
    sub = choose_sub(doc)
    active_projects = active_matched_projects(doc, project_statuses or {})
    task_type = choose_task_type(doc, sub, project_statuses)
    doc_id = str(doc.get("id") or doc.get("url") or "").strip()
    title = str(doc.get("title") or "Untitled document").strip()
    action_items = string_list(doc.get("action_items"))
    key_points = string_list(doc.get("key_points"))

    if action_items:
        action = action_items[0]
    elif sub == "data_foundation":
        action = "turn it into a one-page metric tree or data contract"
    elif sub == "evaluation_discipline":
        action = "turn it into a compact evaluation checklist or validation mini-rep"
    elif sub == "physical_ai":
        action = "extract one interview-ready systems map with 3 operating tradeoffs"
    elif sub == "service_platform_eng":
        action = "turn it into a small reusable implementation or review checklist"
    else:
        action = "extract one reusable PM artifact tied to the active goal"

    return {
        "id": doc_id,
        "title": title,
        "url": str(doc.get("url") or ""),
        "activity_date": str(doc.get("activity_date") or ""),
        "summary": str(doc.get("summary") or ""),
        "key_points": key_points[:3],
        "action_items": action_items[:3],
        "matched_goals": goals,
        "matched_projects": active_projects,
        "priority_hint": str(doc.get("priority_hint") or ""),
        "confidence": doc.get("confidence", 0),
        "suggested_goal": goal,
        "suggested_sub": sub,
        "suggested_type": task_type,
        "suggested_action": action,
    }


def select_candidate(data_dir: Path) -> tuple[dict, dict | None]:
    payload, docs = load_docs(data_dir)
    project_statuses = load_project_statuses(data_dir)
    eligible = [(index, doc) for index, doc in enumerate(docs) if goal_matches(doc)]
    if not eligible:
        return payload, None
    _, doc = max(eligible, key=lambda item: score_doc(item[1], item[0], project_statuses))
    return payload, build_candidate(doc, project_statuses)


def prompt_text(payload: dict, candidate: dict | None) -> str:
    run_date = str(payload.get("run_date") or "")
    generated_at = str(payload.get("generated_at") or "")
    if not candidate:
        return "No goal-tied recent-doc task candidate found in context/recent-drive-docs.json."

    lines = [
        f"Recent-doc task candidate from local cache (run_date: {run_date or 'unknown'}, generated_at: {generated_at or 'unknown'}):",
        f"- Title: {candidate['title']}",
        f"- Activity date: {candidate['activity_date'] or 'unknown'}",
        f"- Link: {candidate['url'] or 'missing'}",
        f"- Suggested metadata: type:{candidate['suggested_type']} | goal:{candidate['suggested_goal']} | sub:{candidate['suggested_sub']} | doc:{candidate['id']}",
        f"- Suggested action: {candidate['suggested_action']}",
    ]
    if candidate["summary"]:
        lines.append(f"- Summary: {candidate['summary']}")
    if candidate["key_points"]:
        lines.append("- Key points: " + "; ".join(candidate["key_points"][:3]))
    if candidate["matched_projects"]:
        lines.append("- Matched projects: " + ", ".join(candidate["matched_projects"]))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Select one goal-tied recent-doc task candidate for the daily planner."
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PERSONAL_PM_DATA_DIR", ""),
        help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/",
    )
    parser.add_argument("--format", choices=("json", "prompt"), default="prompt")
    args = parser.parse_args()

    payload, candidate = select_candidate(resolve_data_dir(args.data_dir))
    if args.format == "json":
        print(
            json.dumps(
                {"run_date": payload.get("run_date"), "candidate": candidate},
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(prompt_text(payload, candidate))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
