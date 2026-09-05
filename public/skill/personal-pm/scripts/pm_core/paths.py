"""Repo-backed skills resolve relative data roots consistently across entrypoints."""

import os
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[2]
# A copied skill can also operate on an explicit data root from any working directory.
_candidate = SKILL_DIR.parents[2]
REPO_ROOT = (
    _candidate if (_candidate / "public/skill/personal-pm").resolve() == SKILL_DIR else Path.cwd()
)
DEFAULT_DATA_DIR = REPO_ROOT / "private"


def resolve_data_dir(value: str | None = None) -> Path:
    raw = value if value is not None else os.environ.get("PERSONAL_PM_DATA_DIR", "")
    path = Path(raw.strip() or "private").expanduser()
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


def data_dir() -> Path:
    return resolve_data_dir()


def data_path(*parts: str) -> Path:
    return data_dir().joinpath(*parts)
