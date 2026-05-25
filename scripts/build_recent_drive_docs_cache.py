#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

GOAL_TERMS = {
    "data_owner": {
        "activation",
        "analytics",
        "contract",
        "data",
        "denominator",
        "evaluation",
        "experiment",
        "lineage",
        "metric",
        "numerator",
        "quality",
        "scorecard",
        "source",
    },
    "experience_design": {
        "design",
        "experience",
        "japanese",
        "physical",
        "robot",
        "robotics",
        "sensor",
        "website",
    },
}


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
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
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


def iso_or_empty(value):
    dt = parse_time(value)
    return dt.isoformat() if dt else ""


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9_]{3,}", text.lower())
        if token not in {"with", "from", "that", "this", "into", "your", "have", "will", "docs"}
    }


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_projects(data_dir: Path):
    text = read_text(data_dir / "goals" / "projects.md")
    projects = []
    for row in re.finditer(
        r"\|\s*([^|]+?)\s*\|\s*(Now|Next|Later)\s*\|\s*(Active|Idea|Paused)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|",
        text,
    ):
        name = row.group(1).strip()
        if name == "---":
            continue
        body = " ".join(part.strip() for part in row.groups())
        projects.append({
            "name": name,
            "priority": row.group(2).strip(),
            "terms": tokenize(body),
        })
    return projects


def load_goal_terms(data_dir: Path):
    text = read_text(data_dir / "goals" / "goal.md")
    terms = {key: set(values) for key, values in GOAL_TERMS.items()}
    all_goal_tokens = tokenize(text)
    for key in terms:
        terms[key].update(token for token in all_goal_tokens if token in GOAL_TERMS[key])
    return terms


def extract_docs(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("docs", "documents", "files", "items", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            docs = extract_docs(value)
            if docs:
                return docs
    return []


def first_value(item, *keys):
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return ""


def owner_name(value):
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return first.get("displayName") or first.get("emailAddress") or ""
        return str(first)
    if isinstance(value, dict):
        return value.get("displayName") or value.get("emailAddress") or ""
    return str(value or "")


def doc_url(item):
    url = first_value(item, "url", "webViewLink", "alternateLink", "htmlLink")
    if url:
        return str(url)
    doc_id = first_value(item, "id", "fileId", "documentId")
    if doc_id:
        return f"https://docs.google.com/document/d/{doc_id}/edit"
    return ""


def is_google_doc(item):
    mime = str(first_value(item, "mimeType", "mime_type", "type")).lower()
    url = doc_url(item)
    if "google-apps.document" in mime or "document" == mime:
        return True
    return "docs.google.com/document" in url


def summarize(item):
    summary = first_value(item, "summary", "description", "snippet", "textSnippet")
    if summary:
        return re.sub(r"\s+", " ", str(summary)).strip()[:240]
    return "Metadata-only match from title and Drive timestamps."


def score_doc(item, goal_terms, projects):
    title = str(first_value(item, "title", "name")).strip()
    summary = summarize(item)
    text = " ".join(
        str(first_value(item, key))
        for key in ("title", "name", "description", "summary", "snippet", "textSnippet")
    )
    text = f"{text} {summary}"
    tokens = tokenize(text)

    matched_goals = []
    matched_keywords = set()
    for goal, terms in goal_terms.items():
        hits = tokens & terms
        if hits:
            matched_goals.append(goal)
            matched_keywords.update(hits)

    matched_projects = []
    project_boost = 0
    for project in projects:
        hits = tokens & project["terms"]
        if len(hits) >= 2 or project["name"].lower() in text.lower():
            matched_projects.append(project["name"])
            matched_keywords.update(list(hits)[:4])
            project_boost += 0.16 if project["priority"] == "Now" else 0.08

    confidence = 0.2 + min(0.36, len(matched_keywords) * 0.06) + len(matched_goals) * 0.12 + project_boost
    confidence = min(0.98, round(confidence, 2))
    if confidence >= 0.78:
        priority_hint = "P1"
    elif confidence >= 0.55:
        priority_hint = "P2"
    elif confidence >= 0.4:
        priority_hint = "P3"
    else:
        priority_hint = ""

    if matched_projects:
        reason = f"Matches {matched_projects[0]} and {', '.join(sorted(matched_keywords)[:3])}."
    elif matched_goals:
        reason = f"Matches {matched_goals[0]} goal terms: {', '.join(sorted(matched_keywords)[:3])}."
    else:
        reason = ""

    return {
        "matched_goals": matched_goals,
        "matched_projects": matched_projects,
        "matched_keywords": sorted(matched_keywords),
        "priority_hint": priority_hint,
        "confidence": confidence,
        "reason": reason,
        "summary": summary,
        "title": title or "Untitled document",
    }


def normalize_doc(item, goal_terms, projects):
    scored = score_doc(item, goal_terms, projects)
    return {
        "id": str(first_value(item, "id", "fileId", "documentId")),
        "title": scored["title"],
        "url": doc_url(item),
        "created_at": iso_or_empty(first_value(item, "created_at", "createdTime", "created")),
        "modified_at": iso_or_empty(first_value(item, "modified_at", "modifiedTime", "modified")),
        "owner": owner_name(first_value(item, "owners", "owner")),
        "summary": scored["summary"],
        "reason": scored["reason"],
        "priority_hint": scored["priority_hint"],
        "confidence": scored["confidence"],
        "matched_goals": scored["matched_goals"],
        "matched_projects": scored["matched_projects"],
        "matched_keywords": scored["matched_keywords"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize recent Google Drive document metadata into the Personal PM docs cache.")
    parser.add_argument("--input", required=True, help="JSON file from a Google Drive connector/API search. Use '-' for stdin.")
    parser.add_argument("--data-dir", default=os.environ.get("PERSONAL_PM_DATA_DIR", ""), help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/")
    parser.add_argument("--output", default="", help="Output JSON path. Defaults to DATA_DIR/context/recent-drive-docs.json")
    parser.add_argument("--lookback-days", type=int, default=3)
    parser.add_argument("--source", default="google_drive_connector")
    parser.add_argument("--include-unmatched", action="store_true")
    args = parser.parse_args()

    data_dir = resolve_data_dir(args.data_dir)
    raw_text = sys.stdin.read() if args.input == "-" else Path(args.input).read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    docs = extract_docs(payload)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.lookback_days)
    goal_terms = load_goal_terms(data_dir)
    projects = load_projects(data_dir)
    normalized = []

    for item in docs:
        if not isinstance(item, dict) or not is_google_doc(item):
            continue
        created = parse_time(first_value(item, "created_at", "createdTime", "created"))
        modified = parse_time(first_value(item, "modified_at", "modifiedTime", "modified"))
        compare_dt = created or modified
        if compare_dt and compare_dt < cutoff:
            continue
        doc = normalize_doc(item, goal_terms, projects)
        if args.include_unmatched or doc["matched_goals"] or doc["matched_projects"]:
            normalized.append(doc)

    normalized.sort(key=lambda d: d.get("created_at") or d.get("modified_at") or "", reverse=True)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": args.source,
        "lookback_days": args.lookback_days,
        "docs": normalized,
    }

    output_path = Path(args.output).expanduser() if args.output else data_dir / "context" / "recent-drive-docs.json"
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(normalized)} docs to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
