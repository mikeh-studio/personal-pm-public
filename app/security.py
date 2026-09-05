"""Local-browser sessions and same-origin mutation protection."""

import hashlib
import hmac
import secrets
from urllib.parse import urlsplit

from flask import jsonify, request, session
from flask.sessions import SecureCookieSessionInterface


class WorkspaceSessions(SecureCookieSessionInterface):
    def get_cookie_name(self, app):
        from paths import data_dir

        # Browser cookies ignore ports; isolate workspaces and server instances
        # without putting a private filesystem path into the cookie name.
        identity = f"{data_dir()}\n{request.host}"
        suffix = hashlib.sha256(identity.encode()).hexdigest()[:24]
        return f"pm_session_{suffix}"


def install(app):
    app.secret_key = secrets.token_bytes(32)
    app.session_interface = WorkspaceSessions()
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict", MAX_CONTENT_LENGTH=160_000
    )

    @app.before_request
    def protect_local_api():
        if not request.path.startswith("/api/"):
            return None
        host = urlsplit(request.host_url).hostname
        if host not in {"localhost", "127.0.0.1", "::1"}:
            return jsonify(ok=False, error="Use the local app URL."), 403
        origin = request.headers.get("Origin")
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            return jsonify(ok=False, error="Cross-origin API access is not allowed."), 403
        if request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify(ok=False, error="Cross-site API access is not allowed."), 403
        if request.path in {"/api/session", "/api/health"} and request.method == "GET":
            return None
        token = session.get("csrf")
        if not token:
            return jsonify(ok=False, error="Reload the app to establish a local session."), 403
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            supplied = request.headers.get("X-PM-CSRF", "")
            if not request.is_json or not hmac.compare_digest(token, supplied):
                return jsonify(
                    ok=False,
                    error="Session expired or request verification failed. Reload the app.",
                ), 403
        return None

    @app.get("/api/session")
    def bootstrap_session():
        session.setdefault("csrf", secrets.token_urlsafe(32))
        return jsonify(csrf=session["csrf"])

    @app.get("/api/health")
    def health():
        from paths import data_dir

        return jsonify(service="personal-pm", data_root=str(data_dir()), ui_contract_version=2)

    @app.after_request
    def private_responses(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        return response
