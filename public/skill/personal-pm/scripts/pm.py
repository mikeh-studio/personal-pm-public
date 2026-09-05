#!/usr/bin/env python3
"""Headless file helpers. The host agent supplies planning decisions and drafts."""

import argparse
import getpass
import json
import os
import sys
from pathlib import Path

if sys.version_info < (3, 10):  # noqa: UP036 — explain unsupported system Python before imports
    raise SystemExit(
        "Personal PM requires Python 3.10+. Run this helper with a supported interpreter, such as python3.11."
    )

from pm_core import api_planning, api_provider, connections, workflow  # noqa: E402
from pm_core.paths import resolve_data_dir  # noqa: E402
from pm_core.weekly import save_weekly  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="Read context, preflight errors, and adaptive limits")
    commands.add_parser("connections", help="List API connection metadata, never keys")
    connect = commands.add_parser(
        "connect", help="Configure an optional API; keys use a hidden terminal prompt"
    )
    connect.add_argument("--provider", choices=connections.PROVIDERS, required=True)
    connect.add_argument("--model", required=True)
    connect.add_argument("--storage", choices=["keychain", "environment"], default="keychain")
    connect.add_argument("--upstream", default="")
    for name in ("disconnect", "test-connection"):
        command = commands.add_parser(name)
        command.add_argument("--provider", choices=connections.PROVIDERS, required=True)
    draft = commands.add_parser(
        "api-draft",
        help="Send local context to the selected API and return a validated draft without applying it",
    )
    draft.add_argument("--provider", choices=connections.PROVIDERS, required=True)
    draft.add_argument("--context-file", type=Path, required=True)
    draft.add_argument("--mode", choices=["normal", "focus"], default="normal")
    draft.add_argument("--focus", default="")
    weekly = commands.add_parser("save-weekly", help="Save a validated weekly JSON draft")
    weekly.add_argument("--week-of", required=True)
    weekly.add_argument("--file", type=Path, required=True)
    weekly.add_argument("--replace", action="store_true")
    plan = commands.add_parser("save-plan", help="Validate and save a Markdown daily draft")
    plan.add_argument("--file", type=Path, required=True)
    plan.add_argument("--replace", action="store_true")
    plan.add_argument("--focus", default="", help="Explicitly selected paused project")
    complete = commands.add_parser("complete", help="Idempotently mark a task complete")
    complete.add_argument("--task-index", type=int, required=True)
    complete.add_argument("--date", required=True, help="Date of the plan you inspected")
    report = commands.add_parser("report", help="Record an explicitly reported task outcome")
    report.add_argument("--task-index", type=int, required=True)
    report.add_argument(
        "--outcome",
        choices=["completed", "incomplete", "blocked", "dropped", "unknown"],
        required=True,
    )
    report.add_argument("--date", required=True, help="Date of the plan you inspected")
    feedback = commands.add_parser("feedback")
    feedback.add_argument("--field", choices=["worked", "did_not_work", "new_goal"], required=True)
    feedback.add_argument("--text", required=True)
    feedback.add_argument("--date", required=True)
    rollover = commands.add_parser(
        "rollover", help="Archive the prior day and refresh outcome memory"
    )
    rollover.add_argument(
        "--date", required=True, help="New planning date; never rewrite a future plan"
    )
    args = parser.parse_args()
    os.environ["PERSONAL_PM_DATA_DIR"] = str(resolve_data_dir(args.data_dir))
    try:
        if args.command == "status":
            result = workflow.status()
        elif args.command == "connections":
            result = {"connections": connections.public_connections()}
        elif args.command == "connect":
            if args.storage == "keychain" and not sys.stdin.isatty():
                raise ValueError(
                    "Keychain setup needs an interactive terminal for hidden input; use environment storage in automation."
                )
            secret = getpass.getpass("API key (hidden): ") if args.storage == "keychain" else ""
            try:
                result = connections.save(
                    args.provider, args.model, args.storage, secret, args.upstream
                )
            finally:
                secret = ""
        elif args.command == "disconnect":
            result = connections.disconnect(args.provider)
        elif args.command == "test-connection":
            result = api_provider.test_connection(args.provider)
        elif args.command == "api-draft":
            result = api_planning.draft_plan(
                args.provider, args.mode, args.focus, args.context_file.read_text(encoding="utf-8")
            )
            # Browser draft IDs only live in their server process. CLI users review
            # plan_markdown, then use the ordinary rollover/save-plan helpers.
            result.pop("draft_id", None)
        elif args.command == "save-weekly":
            result = save_weekly(
                args.week_of, json.loads(args.file.read_text(encoding="utf-8")), args.replace
            )
        elif args.command == "save-plan":
            result = workflow.save_plan(args.file, args.replace, args.focus)
        elif args.command == "complete":
            result = workflow.complete(args.task_index, args.date)
        elif args.command == "report":
            result = workflow.report(args.task_index, args.outcome, args.date)
        elif args.command == "feedback":
            result = workflow.feedback(args.field, args.text, args.date)
        else:
            result = workflow.rollover(args.date)
        print(json.dumps({"ok": True, **result}, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
