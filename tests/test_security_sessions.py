"""Multiple loopback servers share a browser cookie jar, but not sessions."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask, jsonify
from werkzeug.test import Client
from werkzeug.wrappers import Response

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import security  # noqa: E402


class WorkspaceSessionTests(unittest.TestCase):
    def test_two_ports_keep_independent_sessions_in_one_browser(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(os.environ, {"PERSONAL_PM_DATA_DIR": root}),
        ):
            apps = {}
            for port in ("5151", "5152"):
                app = Flask(f"workspace_{port}")
                security.install(app)
                app.add_url_rule(
                    "/api/check", "check", lambda: jsonify(ok=True), methods=["GET", "POST"]
                )
                apps[port] = app

            def serve(environ, start_response):
                return apps[environ["SERVER_PORT"]](environ, start_response)

            browser = Client(serve, Response, use_cookies=True)
            tokens = {}
            cookies = []
            for port in apps:
                response = browser.get("/api/session", base_url=f"http://127.0.0.1:{port}")
                tokens[port] = response.get_json()["csrf"]
                cookies.append(response.headers["Set-Cookie"].split("=", 1)[0])
                self.assertNotIn(root, response.headers["Set-Cookie"])
            self.assertNotEqual(cookies[0], cookies[1])
            for port in apps:
                base = f"http://127.0.0.1:{port}"
                self.assertEqual(browser.get("/api/check", base_url=base).status_code, 200)
                self.assertEqual(
                    browser.post(
                        "/api/check",
                        base_url=base,
                        json={},
                        headers={"X-PM-CSRF": tokens[port], "Origin": base},
                    ).status_code,
                    200,
                )
            self.assertEqual(
                browser.post(
                    "/api/check",
                    base_url="http://127.0.0.1:5152",
                    json={},
                    headers={"X-PM-CSRF": tokens["5151"]},
                ).status_code,
                403,
            )

    def test_same_port_does_not_accept_another_workspaces_cookie(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(os.environ, {"PERSONAL_PM_DATA_DIR": root}),
        ):
            app = Flask("workspace")
            security.install(app)
            app.add_url_rule("/api/check", "check", lambda: jsonify(ok=True))
            client = app.test_client()
            client.get("/api/session")
            self.assertEqual(client.get("/api/check").status_code, 200)
            with patch.dict(os.environ, {"PERSONAL_PM_DATA_DIR": str(Path(root) / "other")}):
                self.assertEqual(client.get("/api/check").status_code, 403)


if __name__ == "__main__":
    unittest.main()
