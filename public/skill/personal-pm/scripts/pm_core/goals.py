"""Goal preflight shared by workspace checks and skill commands."""

import re
from pathlib import Path

REQUIRED_GOAL_SECTIONS = [
    "Overall Goals",
    "Current Near-Term Deadlines",
    "Key Disciplines",
    "Suggested Daily Practice",
]

SETUP_FIELDS = (
    {
        "key": "deadlines",
        "heading": "Current Near-Term Deadlines",
        "label": "Near-term deadlines",
        "help": "One per line. If there are none, write 'No fixed deadlines'.",
    },
    {
        "key": "disciplines",
        "heading": "Key Disciplines",
        "label": "Relevant disciplines",
        "help": "One per line, optionally followed by why it matters: Data engineering — Build reliable reports.",
    },
    {
        "key": "daily_practice",
        "heading": "Suggested Daily Practice",
        "label": "Daily practice preferences",
        "help": "Describe a useful practice and any time or energy limits. One per line.",
    },
)

PLACEHOLDER_RE = re.compile(
    r"^(tbd|todo|placeholder|none|n/a|na|\[.*\]|\{\{.*\}\})$", re.IGNORECASE
)


def section_body(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"^##\s+{re.escape(heading)}\s*$\n(.*?)(?=^##\s+|\Z)", re.MULTILINE | re.DOTALL
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def has_meaningful_content(body: str) -> bool:
    for line in body.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if cleaned.startswith("|") and ("---" in cleaned or "Discipline Area" in cleaned):
            continue
        cleaned = cleaned.strip("-*`#>| ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if cleaned and not PLACEHOLDER_RE.match(cleaned):
            return True
    return False


def validate_goal_file(path: Path) -> list[str]:
    return validate_goal_text(path.read_text(encoding="utf-8"))


def validate_goal_text(text: str) -> list[str]:
    errors = []
    for heading in REQUIRED_GOAL_SECTIONS:
        body = section_body(text, heading)
        if not body:
            errors.append(f"goals/goal.md: missing section '{heading}'")
        elif not has_meaningful_content(body):
            errors.append(f"goals/goal.md: section '{heading}' is placeholder-only")
    return errors


def missing_setup_fields(text):
    return [
        dict(field)
        for field in SETUP_FIELDS
        if not has_meaningful_content(section_body(text, field["heading"]))
    ]


def setup_sections(context):
    if not isinstance(context, dict) or set(context) - {field["key"] for field in SETUP_FIELDS}:
        raise ValueError("Expected deadlines, disciplines, and daily practice context.")
    sections = {}
    for field in SETUP_FIELDS:
        if field["key"] not in context:
            continue
        value = context[field["key"]]
        if not isinstance(value, str) or len(value) > 4000 or "\x00" in value:
            raise ValueError(f"{field['label']} must be text of at most 4000 characters.")
        lines = [
            " ".join(line.split()).lstrip("*-• ") for line in value.splitlines() if line.strip()
        ]
        if not has_meaningful_content("\n".join(lines)):
            raise ValueError(f"Add {field['label'].lower()} before continuing.")
        if field["key"] == "disciplines":
            rows = ["| Discipline Area | Why It Matters |", "| --- | --- |"]
            for line in lines:
                name, _, reason = line.replace("|", "/").partition(" — ")
                rows.append(f"| {name} | {reason} |")
            sections[field["heading"]] = "\n".join(rows)
        else:
            sections[field["heading"]] = "\n".join(f"* {line}" for line in lines)
    return sections
