import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USAGE_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def _clean_model(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    model = value.strip()
    return model if 0 < len(model) <= 120 else ""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def token_usage_log_path(data_root: Path | str) -> Path:
    override = os.environ.get("PERSONAL_PM_TOKEN_USAGE_LOG", "").strip()
    root = Path(data_root)
    if override:
        path = Path(override).expanduser()
        return path if path.is_absolute() else root / path
    return root / "data" / "agent_token_usage.jsonl"


def append_jsonl(path: Path | str, record: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def parse_json_event(line: str) -> dict[str, Any] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None


def _payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    if event.get("type") == "event_msg" and isinstance(payload, dict):
        return payload
    return event


def _nested_dict(value: Any, key: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get(key)
    return nested if isinstance(nested, dict) else {}


def model_from_event(event: dict[str, Any]) -> str:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else event
    info = _nested_dict(payload, "info")
    collaboration_mode = _nested_dict(payload, "collaboration_mode")
    collaboration_settings = _nested_dict(collaboration_mode, "settings")

    candidates = (
        event.get("model"),
        event.get("model_name"),
        payload.get("model"),
        payload.get("model_name"),
        info.get("model"),
        info.get("model_name"),
        collaboration_settings.get("model"),
    )
    for candidate in candidates:
        model = _clean_model(candidate)
        if model:
            return model
    return ""


def _usage_value(usage: dict[str, Any], field: str) -> int:
    value = usage.get(field, 0)
    return value if isinstance(value, int) else 0


def codex_token_record(
    event: dict[str, Any],
    *,
    run_id: str,
    flow: str,
    provider: str,
    step: str,
    sequence: int,
    source: str,
    model: str = "",
    model_source: str = "",
) -> dict[str, Any] | None:
    payload = _payload(event)
    if payload.get("type") != "token_count":
        return None

    info = payload.get("info")
    if not isinstance(info, dict):
        return None

    last_usage = info.get("last_token_usage") or {}
    total_usage = info.get("total_token_usage") or {}
    if not isinstance(last_usage, dict):
        last_usage = {}
    if not isinstance(total_usage, dict):
        total_usage = {}

    record: dict[str, Any] = {
        "recorded_at": utc_now_iso(),
        "run_id": run_id,
        "flow": flow,
        "provider": provider,
        "step": step,
        "sequence": sequence,
        "source": source,
        "usage_available": True,
    }
    model_name = _clean_model(model) or model_from_event(event)
    if model_name:
        record["model"] = model_name
        if model_source:
            record["model_source"] = model_source

    for field in USAGE_FIELDS:
        record[field] = _usage_value(last_usage, field)
        record[f"cumulative_{field}"] = _usage_value(total_usage, field)

    context_window = info.get("model_context_window")
    if isinstance(context_window, int):
        record["model_context_window"] = context_window

    rate_limits = payload.get("rate_limits")
    if isinstance(rate_limits, dict):
        record["rate_limits"] = rate_limits

    return record


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {"model_calls": len(records)}
    for field in USAGE_FIELDS:
        summary[field] = sum(_usage_value(record, field) for record in records)

    if records:
        models: list[str] = []
        for record in records:
            model = _clean_model(record.get("model"))
            if model and model not in models:
                models.append(model)
        if models:
            summary["models"] = models
            if len(models) == 1:
                summary["model"] = models[0]

        latest = records[-1]
        for field in USAGE_FIELDS:
            summary[f"cumulative_{field}"] = _usage_value(latest, f"cumulative_{field}")
        if latest.get("model_context_window"):
            summary["model_context_window"] = latest["model_context_window"]

    return summary


def summarize_log(path: Path | str, run_id: str) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    source = Path(path)
    if not source.exists():
        return summarize_records(records)

    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("run_id") == run_id:
            records.append(record)

    return summarize_records(records)


def token_summary_line(summary: dict[str, Any]) -> str:
    calls = summary.get("model_calls", 0)
    if not calls:
        return "Token usage: unavailable"
    models = summary.get("models") or []
    model_text = ""
    if isinstance(models, list) and len(models) == 1:
        model_text = f" on {models[0]}"
    elif isinstance(models, list) and len(models) > 1:
        model_text = f" across {', '.join(str(model) for model in models)}"

    return (
        f"Token usage: {calls} model calls{model_text}, "
        f"{summary.get('input_tokens', 0)} input "
        f"({summary.get('cached_input_tokens', 0)} cached), "
        f"{summary.get('output_tokens', 0)} output, "
        f"{summary.get('reasoning_output_tokens', 0)} reasoning, "
        f"{summary.get('total_tokens', 0)} total"
    )


def codex_display_lines(event: dict[str, Any] | None, raw_line: str) -> list[str]:
    if event is None:
        stripped = raw_line.rstrip("\n")
        return [stripped] if stripped else []

    payload = _payload(event)
    payload_type = payload.get("type")
    if payload_type == "agent_message":
        message = str(payload.get("message", "")).strip()
        phase = str(payload.get("phase", ""))
        if message and phase in {"final_answer", "assistant_message", ""}:
            return [message]
    if payload_type == "error":
        message = str(payload.get("message") or payload.get("error") or "").strip()
        return [f"Error: {message}"] if message else []
    return []


def stream_codex_jsonl(args: argparse.Namespace) -> int:
    usage_log = Path(args.usage_log)
    raw_output = Path(args.raw_output) if args.raw_output else None
    sequence = 0
    records: list[dict[str, Any]] = []
    current_model = _clean_model(args.model) or _clean_model(
        os.environ.get("PERSONAL_PM_MODEL_HINT")
    )
    current_model_source = "configured_hint" if current_model else ""

    if raw_output:
        raw_output.parent.mkdir(parents=True, exist_ok=True)
        raw_handle = raw_output.open("a", encoding="utf-8")
    else:
        raw_handle = None

    try:
        for line in sys.stdin:
            if raw_handle:
                raw_handle.write(line)
                raw_handle.flush()

            event = parse_json_event(line)
            event_model = model_from_event(event or {})
            if event_model:
                current_model = event_model
                current_model_source = "codex_event"
            record = codex_token_record(
                event or {},
                run_id=args.run_id,
                flow=args.flow,
                provider=args.provider,
                step=args.step,
                sequence=sequence + 1,
                source=args.source,
                model=current_model,
                model_source=current_model_source,
            )
            if record:
                sequence += 1
                records.append(record)
                append_jsonl(usage_log, record)
                if args.print_token_lines:
                    print(
                        f"Tokens {args.step}#{sequence}: "
                        f"{record.get('model', 'unknown model')}, "
                        f"{record['total_tokens']} total "
                        f"({record['input_tokens']} input, "
                        f"{record['output_tokens']} output, "
                        f"{record['reasoning_output_tokens']} reasoning)",
                        flush=True,
                    )
                continue

            for display_line in codex_display_lines(event, line):
                print(display_line, flush=True)
    finally:
        if raw_handle:
            raw_handle.close()

    if not args.quiet:
        summary = summarize_records(records)
        print(f"{token_summary_line(summary)}; log: {usage_log}", flush=True)
        if raw_output:
            print(f"Codex event log: {raw_output}", flush=True)

    return 0


def summarize_command(args: argparse.Namespace) -> int:
    print(json.dumps(summarize_log(args.usage_log, args.run_id), sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Log Personal PM agent token usage.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stream_parser = subparsers.add_parser("stream-codex-jsonl")
    stream_parser.add_argument("--usage-log", required=True)
    stream_parser.add_argument("--raw-output", default="")
    stream_parser.add_argument("--run-id", required=True)
    stream_parser.add_argument("--flow", default="personal_pm")
    stream_parser.add_argument("--provider", default="codex")
    stream_parser.add_argument("--step", default="codex_planning")
    stream_parser.add_argument("--source", default="codex_exec_json")
    stream_parser.add_argument("--model", default="")
    stream_parser.add_argument("--print-token-lines", action="store_true")
    stream_parser.add_argument("--quiet", action="store_true")
    stream_parser.set_defaults(func=stream_codex_jsonl)

    summarize_parser = subparsers.add_parser("summarize")
    summarize_parser.add_argument("--usage-log", required=True)
    summarize_parser.add_argument("--run-id", required=True)
    summarize_parser.set_defaults(func=summarize_command)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
