"""Workspace metadata vocabulary; existing workspaces retain their original values."""

import json
import re

from .paths import data_dir

DEFAULTS = {
    "goals": ["data_owner", "experience_design"],
    "sub_categories": [
        "decision_science",
        "data_foundation",
        "evaluation_discipline",
        "service_platform_eng",
        "website",
        "writing",
        "physical_ai",
        "career_assets",
    ],
}
TOKEN = re.compile(r"^[a-z][a-z0-9_]*$")


def load(root=None):
    path = (root or data_dir()) / "config/planner.json"
    config = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(config, dict) or set(config) - set(DEFAULTS):
        raise ValueError("config/planner.json supports only goals and sub_categories.")
    result = {}
    for key, default in DEFAULTS.items():
        values = config.get(key, default)
        if (
            not isinstance(values, list)
            or not values
            or len(values) > 100
            or any(not isinstance(v, str) or not TOKEN.fullmatch(v) for v in values)
            or len(set(values)) != len(values)
        ):
            raise ValueError(
                f"config/planner.json: {key} must contain unique snake_case identifiers."
            )
        result[key] = set(values)
    return result
