#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "private"
SYNC_MAP_RELATIVE_PATH = Path("data/github_sync_map.json")
CONFIG_RELATIVE_PATH = Path("config/github_sync.json")
MARKER_PREFIX = "personal-pm-sync-id:"
SYNC_MAP_VERSION = 1

PROJECT_ROW_RE = re.compile(
    r"^\|\s*([^|\n]+?)\s*\|\s*(Now|Next|Later)\s*\|\s*(Active|Idea|Paused|Closed)\s*\|\s*([^|\n]*?)\s*\|\s*([^|\n]*?)\s*\|\s*([^|\n]*?)\s*\|\s*$",
    re.MULTILINE,
)
TASK_RE = re.compile(
    r"^- \[(?P<checked>[ xX])\]\s+\[P(?P<priority>[123])\]\s+\[(?P<duration>[^\]]+)\]\s+(?P<body>.+)$",
    re.MULTILINE,
)
DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\b", re.MULTILINE)

BASE_LABEL_SPECS = {
    "personal-pm": ("0e8a16", "Managed by the Personal PM GitHub sync."),
    "sync:managed": ("5319e7", "Issue is managed from local Personal PM data."),
    "pm:project": ("1d76db", "Personal PM project record."),
    "pm:task": ("fbca04", "Personal PM task record."),
}

PREFIX_LABEL_COLORS = {
    "goal": "2da44e",
    "sub": "0969da",
    "type": "8250df",
    "day-priority": "bf3989",
    "project-priority": "fbca04",
    "project-status": "6e7781",
    "task-status": "6e7781",
    "discipline": "54aeff",
}

PROJECT_FIELD_NAMES = {
    "pm_status": "PM Status",
    "project_priority": "Project Priority",
    "day_priority": "Day Priority",
    "goal": "Goal",
    "sub": "Sub",
    "type": "Type",
    "planned_date": "Planned Date",
    "timebox": "Timebox",
    "local_source": "Local Source",
    "sync_id": "Sync ID",
}

RECOMMENDED_PROJECT_FIELDS = tuple(PROJECT_FIELD_NAMES.values())
ALLOWED_CONFIG_KEYS = {
    "repo",
    "project_owner",
    "project_owner_type",
    "project_number",
    "tasks",
    "projects",
    "map_path",
}
BLOCKED_CONFIG_KEYS = {
    "allow_public_project",
    "allow_public_repo",
    "auth",
    "authorization",
    "bearer",
    "password",
    "secret",
    "token",
}


class SyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class SyncSettings:
    repo: str | None
    project_owner: str | None
    project_owner_type: str
    project_number: int | None
    tasks: str
    projects: str
    map_path: str | None


@dataclass
class SyncRecord:
    sync_id: str
    kind: str
    title: str
    body: str
    labels: list[str]
    state: str
    fields: dict[str, str]
    source: str
    content_hash: str = ""

    def finalize(self) -> SyncRecord:
        payload = {
            "body": self.body,
            "fields": self.fields,
            "kind": self.kind,
            "labels": sorted(self.labels),
            "state": self.state,
            "title": self.title,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        self.content_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return self


@dataclass
class PlannedAction:
    action: str
    record: SyncRecord
    issue_number: int | None = None
    issue_url: str = ""
    project_item_id: str = ""
    warnings: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "kind": self.record.kind,
            "sync_id": self.record.sync_id,
            "title": self.record.title,
            "source": self.record.source,
            "state": self.record.state,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "project_item_id": self.project_item_id,
            "warnings": self.warnings,
        }


def resolve_data_dir(value: str | None = None) -> Path:
    raw_value = value if value is not None else os.environ.get("PERSONAL_PM_DATA_DIR", "")
    raw_value = raw_value.strip()
    if not raw_value:
        return DEFAULT_DATA_DIR

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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


def slugify(value: str, max_length: int = 72) -> str:
    slug = value.strip().lower()
    slug = re.sub(r"[`\"']", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        slug = "item"
    return slug[:max_length].strip("-") or "item"


def label_token(value: str) -> str:
    label_slug = value.strip().lower()
    label_slug = label_slug.replace("/", "-")
    label_slug = re.sub(r"[^a-z0-9_.-]+", "-", label_slug)
    label_slug = re.sub(r"-+", "-", label_slug).strip("-")
    return label_slug or "unknown"


def prefixed_label(prefix: str, value: str, max_length: int = 50) -> str:
    prefix = label_token(prefix)
    token_budget = max_length - len(prefix) - 1
    if token_budget < 1:
        return prefix[:max_length].rstrip(":-") or "unknown"
    value_slug = label_token(value)[:token_budget].rstrip(":-") or "unknown"
    return f"{prefix}:{value_slug}"


def truncate(value: str, max_length: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return value[: max_length - 3].rstrip() + "..."


def marker(sync_id: str) -> str:
    return f"<!-- {MARKER_PREFIX} {sync_id} -->"


def managed_footer() -> str:
    return (
        "\n\n---\n"
        "Managed by Personal PM GitHub sync. Edit the local Personal PM data source, "
        "then rerun the sync."
    )


def normalize_task_status(checked: bool, metadata: dict[str, str]) -> str:
    status = re.sub(r"[^a-z]+", "_", metadata.get("status", "").lower()).strip("_")
    if status in {"cancel", "canceled", "cancelled"}:
        return "canceled"
    if status in {"delete", "deleted", "removed"}:
        return "deleted"
    return "completed" if checked else "open"


def project_labels(project: dict[str, str]) -> list[str]:
    labels = [
        "personal-pm",
        "sync:managed",
        "pm:project",
        prefixed_label("project-priority", project["priority"]),
        prefixed_label("project-status", project["status"]),
    ]
    if project.get("discipline"):
        labels.append(prefixed_label("discipline", project["discipline"]))
    return unique(labels)


def task_labels(task: dict[str, Any]) -> list[str]:
    metadata = task["metadata"]
    labels = [
        "personal-pm",
        "sync:managed",
        "pm:task",
        prefixed_label("day-priority", f"p{task['priority']}"),
        prefixed_label("task-status", task["status"]),
    ]
    for key in ("type", "goal", "sub"):
        if metadata.get(key):
            labels.append(prefixed_label(key, metadata[key]))
    return unique(labels)


def unique(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def parse_projects(data_dir: Path, project_mode: str) -> list[dict[str, str]]:
    if project_mode == "none":
        return []
    text = read_text(data_dir / "goals" / "projects.md")
    projects = []
    for index, row in enumerate(PROJECT_ROW_RE.finditer(text)):
        project = {
            "index": str(index),
            "name": row.group(1).strip(),
            "priority": row.group(2).strip(),
            "status": row.group(3).strip(),
            "discipline": row.group(4).strip(),
            "next_action": row.group(5).strip(),
            "notes": row.group(6).strip(),
        }
        if project_mode == "open" and project["status"] == "Closed":
            continue
        projects.append(project)
    return projects


def parse_today_tasks(data_dir: Path, task_mode: str) -> tuple[str, list[dict[str, Any]]]:
    if task_mode == "none":
        return "", []
    text = read_text(data_dir / "tasks" / "today.md")
    date_match = DATE_RE.search(text)
    plan_date = date_match.group(1) if date_match else ""

    tasks = []
    for index, row in enumerate(TASK_RE.finditer(text), start=1):
        checked = row.group("checked").lower() == "x"
        priority = int(row.group("priority"))
        duration = row.group("duration").strip()
        main, metadata = split_metadata(row.group("body").strip())
        title_parts = main.rsplit(" — ", 1)
        title = title_parts[0].strip()
        context = title_parts[1].strip() if len(title_parts) == 2 else ""
        status = normalize_task_status(checked, metadata)
        task = {
            "index": index,
            "checked": checked,
            "priority": priority,
            "duration": duration,
            "title": title,
            "context": context,
            "metadata": metadata,
            "status": status,
            "plan_date": plan_date,
        }
        if should_sync_task(task, task_mode):
            tasks.append(task)
    return plan_date, tasks


def should_sync_task(task: dict[str, Any], task_mode: str) -> bool:
    metadata = task["metadata"]
    sync_value = metadata.get("sync", "").strip().lower()
    if sync_value in {"false", "no", "none", "skip"}:
        return False
    if sync_value in {"github", "gh", "true", "yes"}:
        return True
    if task_mode == "all":
        return True
    if task_mode != "durable":
        return False
    return (
        task["priority"] == 1
        or metadata.get("type") == "project_work"
        or bool(metadata.get("backlog"))
    )


def project_record(project: dict[str, str]) -> SyncRecord:
    sync_id = f"project:{slugify(project['name'])}"
    title = truncate(f"Project: {project['name']}", 120)
    state = "closed" if project["status"] == "Closed" else "open"
    body = "\n".join(
        [
            marker(sync_id),
            "",
            "# Personal PM Project",
            "",
            "- Source: `goals/projects.md`",
            f"- Project priority: `{project['priority']}`",
            f"- PM status: `{project['status']}`",
            f"- Discipline: `{project['discipline'] or 'none'}`",
            "",
            "## Next Action",
            project["next_action"] or "No next action set.",
            "",
            "## Notes",
            project["notes"] or "No notes set.",
        ]
    )
    fields = {
        PROJECT_FIELD_NAMES["pm_status"]: project["status"],
        PROJECT_FIELD_NAMES["project_priority"]: project["priority"],
        PROJECT_FIELD_NAMES["local_source"]: "goals/projects.md",
        PROJECT_FIELD_NAMES["sync_id"]: sync_id,
    }
    if project.get("discipline"):
        fields[PROJECT_FIELD_NAMES["sub"]] = project["discipline"]
    return SyncRecord(
        sync_id=sync_id,
        kind="project",
        title=title,
        body=body + managed_footer(),
        labels=project_labels(project),
        state=state,
        fields=fields,
        source="goals/projects.md",
    ).finalize()


def task_sync_id(task: dict[str, Any]) -> str:
    metadata = task["metadata"]
    explicit = metadata.get("github") or metadata.get("github_id") or metadata.get("sync_id")
    if explicit:
        return f"task:{slugify(explicit, max_length=96)}"

    title_slug = slugify(task["title"], max_length=64)
    if metadata.get("backlog"):
        return f"task:backlog:{title_slug}"
    date = task["plan_date"] or "undated"
    return f"task:{date}:p{task['priority']}:{title_slug}"


def task_record(task: dict[str, Any]) -> SyncRecord:
    sync_id = task_sync_id(task)
    title = truncate(f"[P{task['priority']}] {task['title']}", 120)
    state = "closed" if task["status"] in {"completed", "canceled", "deleted"} else "open"
    metadata = task["metadata"]
    metadata_lines = [
        f"- `{key}`: `{value}`"
        for key, value in sorted(metadata.items())
        if key not in {"github", "github_id", "sync", "sync_id"}
    ]
    if not metadata_lines:
        metadata_lines = ["- none"]

    body = "\n".join(
        [
            marker(sync_id),
            "",
            "# Personal PM Task",
            "",
            "- Source: `tasks/today.md`",
            f"- Planned date: `{task['plan_date'] or 'unknown'}`",
            f"- Day priority: `P{task['priority']}`",
            f"- Timebox: `{task['duration']}`",
            f"- Status: `{task['status']}`",
            f"- Project / discipline: `{task['context'] or 'none'}`",
            "",
            "## Task",
            task["title"],
            "",
            "## Metadata",
            *metadata_lines,
        ]
    )
    fields = {
        PROJECT_FIELD_NAMES["pm_status"]: "Done" if state == "closed" else "Today",
        PROJECT_FIELD_NAMES["day_priority"]: f"P{task['priority']}",
        PROJECT_FIELD_NAMES["planned_date"]: task["plan_date"],
        PROJECT_FIELD_NAMES["timebox"]: task["duration"],
        PROJECT_FIELD_NAMES["local_source"]: "tasks/today.md",
        PROJECT_FIELD_NAMES["sync_id"]: sync_id,
    }
    for metadata_key, field_key in (("type", "type"), ("goal", "goal"), ("sub", "sub")):
        if metadata.get(metadata_key):
            fields[PROJECT_FIELD_NAMES[field_key]] = metadata[metadata_key]
    return SyncRecord(
        sync_id=sync_id,
        kind="task",
        title=title,
        body=body + managed_footer(),
        labels=task_labels(task),
        state=state,
        fields=fields,
        source="tasks/today.md",
    ).finalize()


def build_records(data_dir: Path, project_mode: str, task_mode: str) -> list[SyncRecord]:
    projects = [project_record(project) for project in parse_projects(data_dir, project_mode)]
    _, tasks = parse_today_tasks(data_dir, task_mode)
    task_records = [task_record(task) for task in tasks]
    return projects + task_records


def load_sync_map(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": SYNC_MAP_VERSION, "records": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(f"Invalid sync map JSON: {path} ({exc})") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), dict):
        raise SyncError(f"Invalid sync map shape: {path}")
    payload.setdefault("version", SYNC_MAP_VERSION)
    return payload


def save_sync_map(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def load_config(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SyncError(f"Invalid GitHub sync config JSON: {path} ({exc})") from exc
    if not isinstance(payload, dict):
        raise SyncError(f"Invalid GitHub sync config shape: {path}; expected a JSON object.")
    validate_config_keys(payload, path)
    return payload


def validate_config_keys(payload: dict[str, Any], path: Path) -> None:
    for key in payload:
        normalized = str(key).strip().lower()
        if (
            normalized in BLOCKED_CONFIG_KEYS
            or "token" in normalized
            or "secret" in normalized
        ):
            raise SyncError(
                f"GitHub sync config key {key!r} is not allowed in {path}; "
                "keep auth in gh."
            )
        if normalized not in ALLOWED_CONFIG_KEYS:
            allowed = ", ".join(sorted(ALLOWED_CONFIG_KEYS))
            raise SyncError(
                f"Unsupported GitHub sync config key {key!r} in {path}. "
                f"Allowed keys: {allowed}."
            )


def optional_string(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def optional_int(value: Any, name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise SyncError(f"{name} must be an integer.") from exc


def validate_choice(value: str, allowed: set[str], name: str) -> str:
    if value not in allowed:
        choices = ", ".join(sorted(allowed))
        raise SyncError(f"{name} must be one of: {choices}.")
    return value


def settings_from_args(args: argparse.Namespace, config: dict[str, Any]) -> SyncSettings:
    project_owner_type = optional_string(args.project_owner_type) or optional_string(
        config.get("project_owner_type")
    )
    project_owner_type = project_owner_type or "user"
    tasks = optional_string(args.tasks) or optional_string(config.get("tasks")) or "durable"
    projects = optional_string(args.projects) or optional_string(config.get("projects")) or "all"
    return SyncSettings(
        repo=optional_string(args.repo) or optional_string(config.get("repo")),
        project_owner=optional_string(args.project_owner)
        or optional_string(config.get("project_owner")),
        project_owner_type=validate_choice(project_owner_type, {"user", "org"}, "project_owner_type"),
        project_number=(
            args.project_number
            if args.project_number is not None
            else optional_int(config.get("project_number"), "project_number")
        ),
        tasks=validate_choice(tasks, {"none", "durable", "all"}, "tasks"),
        projects=validate_choice(projects, {"none", "open", "all"}, "projects"),
        map_path=optional_string(args.map_path) or optional_string(config.get("map_path")),
    )


def config_from_settings(settings: SyncSettings) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "repo": settings.repo,
        "tasks": settings.tasks,
        "projects": settings.projects,
    }
    if settings.project_owner:
        payload["project_owner"] = settings.project_owner
        payload["project_owner_type"] = settings.project_owner_type
    if settings.project_number is not None:
        payload["project_number"] = settings.project_number
    if settings.map_path:
        payload["map_path"] = settings.map_path
    return {key: value for key, value in payload.items() if value not in {None, ""}}


def write_private_config(path: Path, settings: SyncSettings, overwrite: bool) -> dict[str, Any]:
    if not settings.repo:
        raise SyncError("--repo is required with --init-config.")
    if path.exists() and not overwrite:
        raise SyncError(f"GitHub sync config already exists: {path}. Use --overwrite-config.")
    payload = config_from_settings(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def resolve_sync_map_path(data_dir: Path, value: str | None) -> Path:
    path = Path(value).expanduser() if value else data_dir / SYNC_MAP_RELATIVE_PATH
    if not path.is_absolute():
        path = data_dir / path
    resolved_path = path.resolve()
    resolved_data_dir = data_dir.resolve()
    if not resolved_path.is_relative_to(resolved_data_dir):
        raise SyncError(
            "Sync map path must stay under the active data root; "
            f"got {resolved_path}, data root is {resolved_data_dir}."
        )
    return resolved_path


class GhClient:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def run(self, args: list[str]) -> str:
        try:
            result = subprocess.run(
                ["gh", *args],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise SyncError("GitHub CLI `gh` is not installed or is not on PATH.") from exc
        if result.returncode != 0:
            stderr = result.stderr.strip() or result.stdout.strip()
            raise SyncError(f"`gh {' '.join(args[:3])}` failed: {stderr}")
        return result.stdout

    def api_json(self, args: list[str]) -> dict[str, Any]:
        output = self.run(["api", *args])
        if not output.strip():
            return {}
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise SyncError(f"GitHub API returned invalid JSON for {' '.join(args[:3])}") from exc

    def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        args = ["graphql", "-f", f"query={query}"]
        for key, value in (variables or {}).items():
            flag = "-F" if isinstance(value, (int, bool)) else "-f"
            args.extend([flag, f"{key}={value}"])
        return self.api_json(args)

    def repo_info(self, repo: str) -> dict[str, Any]:
        return self.api_json([f"repos/{repo}"])

    def auth_status(self) -> str:
        return self.run(["auth", "status"])

    def get_issue(self, repo: str, number: int) -> dict[str, Any] | None:
        try:
            return self.api_json([f"repos/{repo}/issues/{number}"])
        except SyncError:
            return None

    def search_issue_by_marker(self, repo: str, sync_id: str) -> dict[str, Any] | None:
        query = f'repo:{repo} is:issue in:body "{MARKER_PREFIX} {sync_id}"'
        payload = self.api_json(
            ["--method", "GET", "search/issues", "-f", f"q={query}", "-F", "per_page=5"]
        )
        for item in payload.get("items", []):
            issue = self.get_issue(repo, int(item["number"]))
            if issue and marker(sync_id) in str(issue.get("body") or ""):
                return issue
        return None

    def create_issue(self, repo: str, record: SyncRecord) -> dict[str, Any]:
        args = [
            "--method",
            "POST",
            f"repos/{repo}/issues",
            "--raw-field",
            f"title={record.title}",
            "--raw-field",
            f"body={record.body}",
        ]
        for label in record.labels:
            args.extend(["-f", f"labels[]={label}"])
        return self.api_json(args)

    def update_issue(self, repo: str, issue_number: int, record: SyncRecord) -> dict[str, Any]:
        args = [
            "--method",
            "PATCH",
            f"repos/{repo}/issues/{issue_number}",
            "--raw-field",
            f"title={record.title}",
            "--raw-field",
            f"body={record.body}",
            "-f",
            f"state={record.state}",
        ]
        for label in record.labels:
            args.extend(["-f", f"labels[]={label}"])
        return self.api_json(args)

    def list_labels(self, repo: str) -> set[str]:
        payload = self.run(
            [
                "api",
                "--method",
                "GET",
                f"repos/{repo}/labels",
                "--paginate",
                "-F",
                "per_page=100",
            ]
        )
        labels: set[str] = set()
        decoder = json.JSONDecoder()
        text = payload.strip()
        while text:
            chunk, index = decoder.raw_decode(text)
            if isinstance(chunk, list):
                labels.update(str(item.get("name", "")) for item in chunk if isinstance(item, dict))
            text = text[index:].lstrip()
        return labels

    def create_label(self, repo: str, name: str, color: str, description: str) -> None:
        self.api_json(
            [
                "--method",
                "POST",
                f"repos/{repo}/labels",
                "-f",
                f"name={name}",
                "-f",
                f"color={color}",
                "-f",
                f"description={description}",
            ]
        )


def parse_repo(value: str) -> str:
    value = value.strip()
    if value.startswith("https://github.com/"):
        value = value.removeprefix("https://github.com/").removesuffix(".git")
    value = value.strip("/")
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", value):
        raise SyncError("--repo must be in OWNER/REPO form")
    return value


def label_spec(label: str) -> tuple[str, str]:
    if label in BASE_LABEL_SPECS:
        return BASE_LABEL_SPECS[label]
    prefix = label.split(":", 1)[0]
    color = PREFIX_LABEL_COLORS.get(prefix, "d0d7de")
    return color, f"Personal PM {prefix} label."


def ensure_private_repo(client: GhClient, repo: str) -> dict[str, Any]:
    info = client.repo_info(repo)
    if not info.get("private"):
        raise SyncError(
            f"Refusing to sync private planning data to public repo {repo}. "
            "Use a private issue repo."
        )
    return info


def ensure_labels(client: GhClient, repo: str, records: list[SyncRecord]) -> list[str]:
    warnings = []
    existing = client.list_labels(repo)
    desired = sorted({label for record in records for label in record.labels})
    for label in desired:
        if label in existing:
            continue
        color, description = label_spec(label)
        try:
            client.create_label(repo, label, color, description)
            existing.add(label)
        except SyncError as exc:
            warnings.append(f"Could not create label {label!r}: {exc}")
    return warnings


def project_query(owner_type: str) -> str:
    owner_field = "organization" if owner_type == "org" else "user"
    return f"""
query($login: String!, $number: Int!) {{
  {owner_field}(login: $login) {{
    projectV2(number: $number) {{
      id
      title
      public
      fields(first: 100) {{
        nodes {{
          __typename
          ... on ProjectV2Field {{
            id
            name
            dataType
          }}
          ... on ProjectV2SingleSelectField {{
            id
            name
            options {{
              id
              name
            }}
          }}
          ... on ProjectV2IterationField {{
            id
            name
          }}
        }}
      }}
    }}
  }}
}}
"""


def fetch_project(
    client: GhClient,
    owner: str,
    number: int,
    owner_type: str,
) -> dict[str, Any]:
    payload = client.graphql(project_query(owner_type), {"login": owner, "number": number})
    owner_field = "organization" if owner_type == "org" else "user"
    project = (payload.get("data", {}).get(owner_field) or {}).get("projectV2")
    if not project:
        raise SyncError(f"Could not find GitHub Project {owner}/{number}.")
    if project.get("public"):
        raise SyncError(
            f"Refusing to sync private planning data to public GitHub Project {owner}/{number}. "
            "Make the project private."
        )
    return project


def preflight_checks(
    records: list[SyncRecord],
    repo: str | None,
    project_owner: str | None,
    project_number: int | None,
    project_owner_type: str,
) -> tuple[dict[str, Any], list[str], list[str]]:
    client = GhClient()
    warnings = []
    errors = []
    result: dict[str, Any] = {
        "auth": "unknown",
        "records": {
            "total": len(records),
            "projects": sum(1 for record in records if record.kind == "project"),
            "tasks": sum(1 for record in records if record.kind == "task"),
        },
        "repo": None,
        "project": None,
    }

    try:
        client.auth_status()
        result["auth"] = "ok"
    except SyncError as exc:
        result["auth"] = "failed"
        errors.append(str(exc))

    if repo:
        try:
            parsed_repo = parse_repo(repo)
            repo_info = ensure_private_repo(client, parsed_repo)
            result["repo"] = {
                "name": repo_info.get("full_name", parsed_repo),
                "private": bool(repo_info.get("private")),
                "issues_enabled": bool(repo_info.get("has_issues", True)),
            }
            if not result["repo"]["issues_enabled"]:
                errors.append(f"Repository {parsed_repo} does not have issues enabled.")
        except SyncError as exc:
            errors.append(str(exc))
    else:
        warnings.append("No --repo supplied; preflight skipped issue target checks.")

    if project_owner or project_number:
        if not (project_owner and project_number):
            errors.append("--project-owner and --project-number must be provided together.")
        else:
            try:
                project = fetch_project(
                    client,
                    project_owner,
                    project_number,
                    project_owner_type,
                )
                fields = project_fields_by_name(project)
                missing_fields = [
                    field_name
                    for field_name in RECOMMENDED_PROJECT_FIELDS
                    if field_name not in fields
                ]
                result["project"] = {
                    "title": project.get("title", ""),
                    "public": bool(project.get("public")),
                    "missing_recommended_fields": missing_fields,
                }
                if missing_fields:
                    warnings.append(
                        "Project field sync will be partial; missing fields: "
                        + ", ".join(missing_fields)
                    )
            except SyncError as exc:
                errors.append(str(exc))
    else:
        warnings.append("No Project v2 target supplied; preflight skipped project checks.")

    return result, warnings, errors


def print_preflight(result: dict[str, Any], warnings: list[str], errors: list[str]) -> None:
    status = "passed" if not errors else "failed"
    print(f"GitHub sync preflight {status}")
    print(f"- gh auth: {result.get('auth')}")
    records = result.get("records", {})
    print(
        "- records: "
        f"{records.get('total', 0)} total, "
        f"{records.get('projects', 0)} projects, "
        f"{records.get('tasks', 0)} tasks"
    )
    repo = result.get("repo")
    if repo:
        visibility = "private" if repo.get("private") else "public"
        issues = "enabled" if repo.get("issues_enabled") else "disabled"
        print(f"- issue repo: {repo.get('name')} ({visibility}, issues {issues})")
    project = result.get("project")
    if project:
        visibility = "public" if project.get("public") else "private"
        missing = project.get("missing_recommended_fields") or []
        print(f"- project: {project.get('title')} ({visibility})")
        print(f"- missing recommended fields: {', '.join(missing) if missing else 'none'}")
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    for error in errors:
        print(f"error: {error}", file=sys.stderr)


def project_fields_by_name(project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}
    nodes = (project.get("fields") or {}).get("nodes") or []
    for node in nodes:
        if not isinstance(node, dict) or not node.get("name"):
            continue
        fields[str(node["name"])] = node
    return fields


def add_issue_to_project(client: GhClient, project_id: str, issue_node_id: str) -> str:
    payload = client.graphql(
        """
mutation($projectId: ID!, $contentId: ID!) {
  addProjectV2ItemById(input: {projectId: $projectId, contentId: $contentId}) {
    item {
      id
    }
  }
}
""",
        {"projectId": project_id, "contentId": issue_node_id},
    )
    item = (payload.get("data", {}).get("addProjectV2ItemById") or {}).get("item") or {}
    item_id = str(item.get("id") or "")
    if not item_id:
        raise SyncError("GitHub did not return a project item id.")
    return item_id


def graph_string(value: str) -> str:
    return json.dumps(str(value))


def update_project_field(
    client: GhClient,
    project_id: str,
    item_id: str,
    field: dict[str, Any],
    value: str,
) -> str | None:
    value = str(value or "").strip()
    if not value:
        return None

    field_id = graph_string(field["id"])
    data_type = str(field.get("dataType") or "").upper()
    typename = str(field.get("__typename") or "")
    value_expr = ""

    if typename == "ProjectV2SingleSelectField":
        options = field.get("options") or []
        option_by_name = {str(option.get("name", "")).lower(): option for option in options}
        option = option_by_name.get(value.lower())
        if not option:
            return f"Project field {field['name']!r} has no option {value!r}; skipped."
        value_expr = f'{{ singleSelectOptionId: {graph_string(option["id"])} }}'
    elif data_type == "DATE":
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return f"Project field {field['name']!r} expected YYYY-MM-DD, got {value!r}; skipped."
        value_expr = f"{{ date: {graph_string(value)} }}"
    elif data_type == "NUMBER":
        number_match = re.search(r"\d+(?:\.\d+)?", value)
        if not number_match:
            return f"Project field {field['name']!r} expected a number, got {value!r}; skipped."
        value_expr = f"{{ number: {number_match.group(0)} }}"
    else:
        value_expr = f"{{ text: {graph_string(truncate(value, 1024))} }}"

    query = f"""
mutation {{
  updateProjectV2ItemFieldValue(
    input: {{
      projectId: {graph_string(project_id)}
      itemId: {graph_string(item_id)}
      fieldId: {field_id}
      value: {value_expr}
    }}
  ) {{
    projectV2Item {{
      id
    }}
  }}
}}
"""
    client.graphql(query)
    return None


def update_project_fields(
    client: GhClient,
    project: dict[str, Any],
    item_id: str,
    record: SyncRecord,
) -> list[str]:
    warnings = []
    fields = project_fields_by_name(project)
    for field_name, value in record.fields.items():
        field = fields.get(field_name)
        if not field:
            warnings.append(f"GitHub Project field {field_name!r} not found; skipped.")
            continue
        warning = update_project_field(client, str(project["id"]), item_id, field, value)
        if warning:
            warnings.append(warning)
    return warnings


def existing_issue_for_record(
    client: GhClient,
    repo: str,
    record: SyncRecord,
    mapped: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if mapped and mapped.get("issue_number"):
        issue = client.get_issue(repo, int(mapped["issue_number"]))
        if issue and marker(record.sync_id) in str(issue.get("body") or ""):
            return issue
    return client.search_issue_by_marker(repo, record.sync_id)


def issue_matches_record(issue: dict[str, Any], record: SyncRecord) -> bool:
    labels = {
        str(label.get("name", ""))
        for label in issue.get("labels", [])
        if isinstance(label, dict)
    }
    return (
        str(issue.get("title") or "") == record.title
        and str(issue.get("body") or "") == record.body
        and str(issue.get("state") or "") == record.state
        and labels == set(record.labels)
    )


def dry_run_actions(records: list[SyncRecord], sync_map: dict[str, Any]) -> list[PlannedAction]:
    mapped_records = sync_map.get("records", {})
    actions = []
    for record in records:
        mapped = mapped_records.get(record.sync_id)
        if not mapped:
            action = "create"
        elif mapped.get("content_hash") != record.content_hash:
            action = "update"
        else:
            action = "unchanged"
        actions.append(
            PlannedAction(
                action=action,
                record=record,
                issue_number=mapped.get("issue_number") if mapped else None,
                issue_url=mapped.get("issue_url", "") if mapped else "",
                project_item_id=mapped.get("project_item_id", "") if mapped else "",
            )
        )
    return actions


def apply_sync(
    records: list[SyncRecord],
    sync_map: dict[str, Any],
    repo: str,
    project: dict[str, Any] | None,
) -> tuple[list[PlannedAction], dict[str, Any], list[str]]:
    client = GhClient()
    ensure_private_repo(client, repo)
    warnings = ensure_labels(client, repo, records)
    mapped_records = sync_map.setdefault("records", {})
    actions: list[PlannedAction] = []

    for record in records:
        mapped = mapped_records.get(record.sync_id, {})
        issue = existing_issue_for_record(client, repo, record, mapped)
        if issue:
            issue_number = int(issue["number"])
            previous_hash = mapped.get("content_hash")
            if previous_hash == record.content_hash and issue_matches_record(issue, record):
                action = "unchanged"
                issue_payload = issue
            else:
                action = "update"
                issue_payload = client.update_issue(repo, issue_number, record)
        else:
            action = "create"
            issue_payload = client.create_issue(repo, record)
            issue_number = int(issue_payload["number"])
            if record.state == "closed":
                issue_payload = client.update_issue(repo, issue_number, record)

        project_item_id = str(mapped.get("project_item_id") or "")
        action_warnings: list[str] = []
        if project:
            try:
                if not project_item_id:
                    project_item_id = add_issue_to_project(
                        client, str(project["id"]), str(issue_payload["node_id"])
                    )
                action_warnings.extend(update_project_fields(client, project, project_item_id, record))
            except SyncError as exc:
                action_warnings.append(str(exc))

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        mapped_records[record.sync_id] = {
            "kind": record.kind,
            "issue_number": issue_number,
            "issue_node_id": issue_payload.get("node_id", ""),
            "issue_url": issue_payload.get("html_url", ""),
            "project_item_id": project_item_id,
            "content_hash": record.content_hash,
            "last_synced_at": now,
            "state": record.state,
        }
        actions.append(
            PlannedAction(
                action=action,
                record=record,
                issue_number=issue_number,
                issue_url=str(issue_payload.get("html_url", "")),
                project_item_id=project_item_id,
                warnings=action_warnings,
            )
        )
    return actions, sync_map, warnings


def print_summary(actions: list[PlannedAction], warnings: list[str], dry_run: bool) -> None:
    counts: dict[str, int] = {}
    for action in actions:
        counts[action.action] = counts.get(action.action, 0) + 1
    mode = "Dry run" if dry_run else "Applied"
    print(f"{mode}: {len(actions)} Personal PM records")
    for key in ("create", "update", "unchanged"):
        if key in counts:
            print(f"- {key}: {counts[key]}")
    for action in actions:
        issue = f" #{action.issue_number}" if action.issue_number else ""
        print(f"- {action.action}: {action.record.kind}{issue} {action.record.title}")
        for warning in action.warnings:
            print(f"  warning: {warning}", file=sys.stderr)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if dry_run:
        print("No GitHub writes were made. Re-run with --apply to create or update issues.")


def actions_json(
    actions: list[PlannedAction],
    warnings: list[str],
    data_dir: Path,
    sync_map_path: Path,
    dry_run: bool,
) -> dict[str, Any]:
    return {
        "ok": not warnings,
        "dry_run": dry_run,
        "data_dir": str(data_dir),
        "sync_map": str(sync_map_path),
        "counts": {
            action: sum(1 for item in actions if item.action == action)
            for action in sorted({item.action for item in actions})
        },
        "records": [action.summary() for action in actions],
        "warnings": warnings,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Personal PM projects and durable daily tasks to private GitHub Issues and Projects."
    )
    parser.add_argument(
        "--data-dir",
        default=os.environ.get("PERSONAL_PM_DATA_DIR", ""),
        help="Planner data root. Defaults to PERSONAL_PM_DATA_DIR or private/.",
    )
    parser.add_argument(
        "--repo",
        help="Private GitHub issue repo in OWNER/REPO form. Required with --apply.",
    )
    parser.add_argument(
        "--project-owner",
        help="GitHub user or organization that owns the Projects v2 board.",
    )
    parser.add_argument(
        "--project-owner-type",
        choices=["user", "org"],
        default=None,
        help="Whether --project-owner is a user or organization. Defaults to user.",
    )
    parser.add_argument(
        "--project-number",
        type=int,
        help="GitHub Projects v2 number to update. Omit for issue-only sync.",
    )
    parser.add_argument(
        "--tasks",
        choices=["none", "durable", "all"],
        default=None,
        help="Task sync policy. durable syncs P1, project_work, backlog, and sync:github tasks.",
    )
    parser.add_argument(
        "--projects",
        choices=["none", "open", "all"],
        default=None,
        help="Project sync policy. open excludes local projects marked Closed.",
    )
    parser.add_argument(
        "--map-path",
        help="Sync map path. Defaults to DATA_DIR/data/github_sync_map.json.",
    )
    parser.add_argument(
        "--config",
        help="Optional private config path. Defaults to DATA_DIR/config/github_sync.json when present.",
    )
    parser.add_argument(
        "--init-config",
        action="store_true",
        help="Write a private config file from the supplied target flags, then exit.",
    )
    parser.add_argument(
        "--overwrite-config",
        action="store_true",
        help="Allow --init-config to replace an existing private config file.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Create/update GitHub issues and project items. Omit for a local dry run.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Check gh auth, target privacy, and Project field coverage without writing.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        data_dir = resolve_data_dir(args.data_dir)
        config_path = Path(args.config).expanduser() if args.config else data_dir / CONFIG_RELATIVE_PATH
        if not config_path.is_absolute():
            config_path = (REPO_ROOT / config_path).resolve()
        if args.config and not config_path.exists() and not args.init_config:
            raise SyncError(f"GitHub sync config not found: {config_path}")
        config = load_config(config_path)
        settings = settings_from_args(args, config)
        sync_map_path = resolve_sync_map_path(data_dir, settings.map_path)

        records = build_records(data_dir, settings.projects, settings.tasks)
        sync_map = load_sync_map(sync_map_path)
        warnings: list[str] = []

        if settings.project_owner or settings.project_number:
            if not (settings.project_owner and settings.project_number):
                raise SyncError("--project-owner and --project-number must be provided together.")

        if args.init_config:
            payload = write_private_config(config_path, settings, args.overwrite_config)
            output = {
                "ok": True,
                "config": str(config_path),
                "settings": payload,
                "wrote_config": True,
            }
            if args.json:
                print(json.dumps(output, indent=2, sort_keys=True))
            else:
                print(f"Wrote private GitHub sync config: {config_path}")
            return 0

        if args.preflight:
            repo = parse_repo(settings.repo) if settings.repo else None
            result, warnings, errors = preflight_checks(
                records,
                repo,
                settings.project_owner,
                settings.project_number,
                settings.project_owner_type,
            )
            output = {
                "ok": not errors,
                "dry_run": True,
                "config": str(config_path) if config_path.exists() else "",
                "preflight": result,
                "warnings": warnings,
                "errors": errors,
            }
            if args.json:
                print(json.dumps(output, indent=2, sort_keys=True))
            else:
                print_preflight(result, warnings, errors)
            return 0 if not errors else 1

        if args.apply:
            if not settings.repo:
                raise SyncError("--repo is required with --apply.")
            repo = parse_repo(settings.repo)
            project = None
            if settings.project_owner and settings.project_number:
                project = fetch_project(
                    GhClient(),
                    settings.project_owner,
                    settings.project_number,
                    settings.project_owner_type,
                )
            actions, sync_map, warnings = apply_sync(
                records,
                sync_map,
                repo,
                project,
            )
            save_sync_map(sync_map_path, sync_map)
        else:
            actions = dry_run_actions(records, sync_map)

        output = actions_json(actions, warnings, data_dir, sync_map_path, dry_run=not args.apply)
        if args.json:
            print(json.dumps(output, indent=2, sort_keys=True))
        else:
            print_summary(actions, warnings, dry_run=not args.apply)
        return 0 if not warnings else 1
    except SyncError as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc)}, indent=2, sort_keys=True))
        else:
            print(f"GitHub sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
