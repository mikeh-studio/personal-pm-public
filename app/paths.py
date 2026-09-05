"""Expose the skill's shared paths to existing app entrypoints."""

import sys
from pathlib import Path

_HELPERS = Path(__file__).resolve().parents[1] / "public/skill/personal-pm/scripts"
if str(_HELPERS) not in sys.path:
    sys.path.insert(0, str(_HELPERS))

from pm_core.paths import (  # noqa: E402, F401
    DEFAULT_DATA_DIR,
    REPO_ROOT,
    data_dir,
    data_path,
    resolve_data_dir,
)
