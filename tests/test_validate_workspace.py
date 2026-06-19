import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "scripts" / "validate_workspace.py"
SPEC = importlib.util.spec_from_file_location("validate_workspace", MODULE_PATH)
validate_workspace = importlib.util.module_from_spec(SPEC)
sys.modules["validate_workspace"] = validate_workspace
SPEC.loader.exec_module(validate_workspace)


class ValidateWorkspaceTests(unittest.TestCase):
    def make_config(self, payload: dict) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "github_sync.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_github_sync_config_rejects_auth_and_public_override_keys(self):
        path = self.make_config(
            {
                "repo": "owner/private-repo",
                "token": "do-not-store",
                "allow_public_repo": True,
            }
        )

        errors = validate_workspace.validate_github_sync_config(path)

        self.assertTrue(any("token" in error for error in errors))
        self.assertTrue(any("allow_public_repo" in error for error in errors))

    def test_github_sync_config_rejects_unknown_keys_and_map_escape(self):
        path = self.make_config(
            {
                "repo": "owner/private-repo",
                "notes": "unused",
                "map_path": "../github_sync_map.json",
            }
        )

        errors = validate_workspace.validate_github_sync_config(path)

        self.assertTrue(any("unsupported key 'notes'" in error for error in errors))
        self.assertTrue(any("map_path must stay under the data root" in error for error in errors))

    def test_github_sync_config_accepts_private_target_shape(self):
        path = self.make_config(
            {
                "repo": "owner/private-repo",
                "project_owner": "owner",
                "project_owner_type": "user",
                "project_number": 1,
                "tasks": "durable",
                "projects": "all",
                "map_path": "data/github_sync_map.json",
            }
        )

        errors = validate_workspace.validate_github_sync_config(path)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
