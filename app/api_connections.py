"""Thin HTTP adapter for skill-owned API planning and connections."""

from flask import jsonify, request
from pm_core import api_provider, connections
from pm_core.api_planning import apply_draft, draft_plan


def install(app):
    @app.get("/api/connections")
    def list_connections():
        try:
            return jsonify(ok=True, connections=connections.public_connections())
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400

    @app.post("/api/connections/<key>/<action>")
    def connection_action(key, action):
        body = request.get_json() or {}
        if not isinstance(body, dict):
            return jsonify(ok=False, error="Expected a settings object."), 400
        try:
            if action == "save":
                if set(body) - {"model", "storage", "api_key", "upstream"}:
                    raise ValueError(
                        "Unsupported connection setting; custom endpoints are not accepted."
                    )
                result = connections.save(
                    key,
                    body.get("model", ""),
                    body.get("storage", ""),
                    body.get("api_key", ""),
                    body.get("upstream", ""),
                )
            elif action == "disconnect":
                result = connections.disconnect(key)
            elif action == "test":
                result = api_provider.test_connection(key)
            else:
                raise ValueError("Unknown connection action.")
            return jsonify(ok=True, **result)
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except OSError:
            return jsonify(ok=False, error="Local connection storage failed."), 500

    @app.post("/api/plan/draft")
    def api_draft():
        body = request.get_json() or {}
        if not isinstance(body, dict):
            return jsonify(ok=False, error="Expected planning inputs."), 400
        try:
            return jsonify(
                ok=True,
                **draft_plan(
                    body.get("provider"),
                    body.get("mode", "normal"),
                    body.get("focus", ""),
                    body.get("context", ""),
                ),
            )
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except OSError:
            return jsonify(ok=False, error="Local planning files could not be read."), 500

    @app.post("/api/plan/apply")
    def api_apply():
        body = request.get_json() or {}
        if not isinstance(body, dict) or not isinstance(body.get("draft_id"), str):
            return jsonify(ok=False, error="Expected a draft ID."), 400
        try:
            return jsonify(ok=True, **apply_draft(body["draft_id"]))
        except ValueError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except OSError:
            return jsonify(
                ok=False, error="Could not save the plan. Check local files before retrying."
            ), 500
