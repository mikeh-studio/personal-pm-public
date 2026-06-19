#!/usr/bin/env python3

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_data_dir(value: str | None = None) -> Path:
    raw_value = value if value is not None else os.environ.get("PERSONAL_PM_DATA_DIR", "")
    raw_value = raw_value.strip() or "private"
    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def resolve_data_path(data_dir: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = data_dir / path
    return path.resolve()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def string_list(value, limit=5):
    if not isinstance(value, list):
        return []
    items = []
    for item in value:
        text = str(item).strip()
        if text:
            items.append(text[:240])
        if len(items) >= limit:
            break
    return items


def doc_identity(doc: dict) -> str:
    return str(doc.get("id") or doc.get("url") or "").strip()


def doc_activity_date(doc: dict) -> str:
    return str(doc.get("activity_date") or "").strip()


def doc_modified_at(doc: dict) -> str:
    return str(
        doc.get("modified_at") or doc.get("activity_at") or doc.get("created_at") or ""
    ).strip()


def ingest_key(doc: dict) -> str:
    identity = doc_identity(doc)
    activity_date = doc_activity_date(doc)
    if not identity or not activity_date:
        return ""
    return f"{identity}|{activity_date}"


def summary_key(doc: dict) -> str:
    base = ingest_key(doc)
    modified_at = doc_modified_at(doc)
    if not base or not modified_at:
        return ""
    return f"{base}|{modified_at}"


def compact_summary_entry(doc: dict, now: str) -> dict:
    return {
        "id": str(doc.get("id") or ""),
        "title": str(doc.get("title") or "Untitled document"),
        "url": str(doc.get("url") or ""),
        "activity_date": doc_activity_date(doc),
        "activity_at": str(doc.get("activity_at") or ""),
        "created_at": str(doc.get("created_at") or ""),
        "modified_at": str(doc.get("modified_at") or ""),
        "summary": str(doc.get("summary") or ""),
        "key_points": string_list(doc.get("key_points"), limit=3),
        "action_items": string_list(doc.get("action_items"), limit=3),
        "matched_goals": string_list(doc.get("matched_goals")),
        "matched_projects": string_list(doc.get("matched_projects")),
        "matched_keywords": string_list(doc.get("matched_keywords"), limit=12),
        "priority_hint": str(doc.get("priority_hint") or ""),
        "reason": str(doc.get("reason") or ""),
        "summary_source": str(doc.get("summary_source") or "recent-drive-docs"),
        "updated_at": now,
    }


def compact_ingest_key_entry(doc: dict, run_date: str, existing: dict | None = None) -> dict:
    existing = existing if isinstance(existing, dict) else {}
    return {
        "id": str(doc.get("id") or ""),
        "title": str(doc.get("title") or "Untitled document"),
        "url": str(doc.get("url") or ""),
        "activity_date": doc_activity_date(doc),
        "activity_at": str(doc.get("activity_at") or ""),
        "created_at": str(doc.get("created_at") or ""),
        "modified_at": str(doc.get("modified_at") or ""),
        "first_seen_run_date": str(existing.get("first_seen_run_date") or run_date),
        "last_seen_run_date": run_date,
    }


def refresh_state(args) -> int:
    data_dir = resolve_data_dir(args.data_dir)
    recent_docs_path = resolve_data_path(data_dir, args.recent_docs_path)
    summary_cache_path = resolve_data_path(data_dir, args.summary_cache_path)
    ingest_key_index_path = resolve_data_path(data_dir, args.ingest_key_index_path)

    recent_payload = load_json(recent_docs_path, {})
    docs = recent_payload.get("docs", []) if isinstance(recent_payload, dict) else []
    if not isinstance(docs, list):
        docs = []

    now = datetime.now(timezone.utc).isoformat()
    run_date = args.run_date.strip() or str(recent_payload.get("run_date") or "")

    summary_payload = load_json(summary_cache_path, {})
    existing_summary_entries = (
        summary_payload.get("entries", {}) if isinstance(summary_payload, dict) else {}
    )
    if not isinstance(existing_summary_entries, dict):
        existing_summary_entries = {}

    key_payload = load_json(ingest_key_index_path, {})
    existing_keys = key_payload.get("keys", {}) if isinstance(key_payload, dict) else {}
    if not isinstance(existing_keys, dict):
        existing_keys = {}

    summary_entries = dict(existing_summary_entries)
    key_entries = dict(existing_keys)
    refreshed = 0
    skipped = 0

    for doc in docs:
        if not isinstance(doc, dict):
            skipped += 1
            continue
        doc_key = ingest_key(doc)
        doc_summary_key = summary_key(doc)
        if not doc_key:
            skipped += 1
            continue
        key_entries[doc_key] = compact_ingest_key_entry(doc, run_date, key_entries.get(doc_key))
        if doc_summary_key:
            summary_entries[doc_summary_key] = compact_summary_entry(doc, now)
            refreshed += 1

    summary_output = {
        "generated_at": now,
        "source": "recent-drive-docs",
        "entry_key": "doc_id_or_url|activity_date|modified_at",
        "contains_raw_bodies": False,
        "entries": dict(sorted(summary_entries.items())),
    }
    keys_output = {
        "generated_at": now,
        "source": "recent-drive-docs",
        "entry_key": "doc_id_or_url|activity_date",
        "keys": dict(sorted(key_entries.items())),
    }

    write_json(summary_cache_path, summary_output)
    write_json(ingest_key_index_path, keys_output)
    print(f"Refreshed {refreshed} summary cache entries at {summary_cache_path}")
    print(f"Indexed {len(key_entries)} ingest keys at {ingest_key_index_path}")
    if skipped:
        print(f"Skipped {skipped} docs without usable identity/activity date")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Maintain local state for low-cost Google Docs ingest runs."
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PERSONAL_PM_DATA_DIR", ""),
        help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/",
    )
    parser.add_argument("--recent-docs-path", default="context/recent-drive-docs.json")
    parser.add_argument("--summary-cache-path", default="data/google_docs_summary_cache.json")
    parser.add_argument("--ingest-key-index-path", default="data/google_docs_ingest_keys.json")
    parser.add_argument("--run-date", default="", help="Run date to record as last_seen_run_date.")
    args = parser.parse_args()
    return refresh_state(args)


if __name__ == "__main__":
    raise SystemExit(main())
