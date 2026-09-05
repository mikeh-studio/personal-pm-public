"""Goal preflight shared by workspace checks and skill commands."""

import re
from pathlib import Path

REQUIRED_GOAL_SECTIONS = [
    "Overall Goals",
    "Current Near-Term Deadlines",
    "Key Disciplines",
    "Suggested Daily Practice",
]

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
    errors = []
    text = path.read_text(encoding="utf-8")
    for heading in REQUIRED_GOAL_SECTIONS:
        body = section_body(text, heading)
        if not body:
            errors.append(f"goals/goal.md: missing section '{heading}'")
        elif not has_meaningful_content(body):
            errors.append(f"goals/goal.md: section '{heading}' is placeholder-only")
    return errors
