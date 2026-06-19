#!/bin/zsh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="${PERSONAL_PM_REPO_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
RUNNER="$REPO_ROOT/private/automation/scripts/autonomous_daily_runner.sh"
HOST="${PERSONAL_PM_HOST:-127.0.0.1}"
DEFAULT_PORT="${PERSONAL_PM_PORT:-5151}"
APP_STDOUT_LOG="${PERSONAL_PM_APP_STDOUT_LOG:-/tmp/personal-pm-app.log}"
APP_STDERR_LOG="${PERSONAL_PM_APP_STDERR_LOG:-/tmp/personal-pm-app.err}"

if [[ -n "${PERSONAL_PM_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PERSONAL_PM_PYTHON_BIN"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3.11)"
else
  PYTHON_BIN="$(command -v python3)"
fi
PYTHON_BIN_DIR="$(dirname "$PYTHON_BIN")"

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "No usable Python interpreter found. Set PERSONAL_PM_PYTHON_BIN to Python 3.10+." >&2
  exit 1
fi

if ! "$PYTHON_BIN" - <<'PY'
import sys

raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  echo "Personal PM requires Python 3.10+. Set PERSONAL_PM_PYTHON_BIN to a compatible interpreter." >&2
  exit 1
fi

if [[ -n "${PERSONAL_PM_DATA_DIR:-}" ]]; then
  if [[ "$PERSONAL_PM_DATA_DIR" == /* ]]; then
    DATA_DIR="$PERSONAL_PM_DATA_DIR"
  else
    DATA_DIR="$REPO_ROOT/$PERSONAL_PM_DATA_DIR"
  fi
else
  DATA_DIR="$REPO_ROOT/private"
fi

TODAY_FILE="$DATA_DIR/tasks/today.md"
RUN_LOG="${PERSONAL_PM_RUN_LOG:-$DATA_DIR/data/agent_runs.jsonl}"

planner_state() {
  TODAY_FILE_PATH="$TODAY_FILE" RUN_LOG_PATH="$RUN_LOG" "$PYTHON_BIN" - <<'PY'
import json
import os
import re
from datetime import date
from pathlib import Path

today = date.today().isoformat()
today_file = Path(os.environ["TODAY_FILE_PATH"])
run_log = Path(os.environ["RUN_LOG_PATH"])

plan_date = ""
if today_file.exists():
    match = re.search(r"## (\d{4}-\d{2}-\d{2})", today_file.read_text(encoding="utf-8"))
    if match:
        plan_date = match.group(1)

latest = None
if run_log.exists():
    for line in run_log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("mode") in {"daily_autonomous", "daily_autonomous_local"}:
            latest = record

latest_date = str((latest or {}).get("started_at", ""))[:10]
latest_status = str((latest or {}).get("status", ""))
plan_current = plan_date == today
latest_failed_today = latest_date == today and latest_status == "failed"

needs_run = (not plan_current) or latest_failed_today
if not plan_date:
    reason = "missing plan date"
elif not plan_current:
    reason = f"stale plan date {plan_date}; expected {today}"
elif latest_failed_today:
    reason = "latest autonomous run failed today"
else:
    reason = "current plan is ready"

print(json.dumps({
    "today": today,
    "plan_date": plan_date,
    "plan_current": plan_current,
    "latest_run": latest,
    "latest_run_date": latest_date,
    "latest_run_status": latest_status,
    "needs_run": needs_run,
    "reason": reason,
}, sort_keys=True))
PY
}

json_field() {
  local field="$1"
  local payload="$2"
  FIELD="$field" "$PYTHON_BIN" -c 'import json, os, sys; print(json.load(sys.stdin).get(os.environ["FIELD"], ""))' <<< "$payload"
}

port_in_use() {
  local port="$1"
  "$PYTHON_BIN" - "$HOST" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.3)
    sys.exit(0 if sock.connect_ex((host, port)) == 0 else 1)
PY
}

port_has_personal_pm() {
  local port="$1"
  local payload

  if ! payload="$(curl -fsS "http://$HOST:$port/api/morning-status" 2>/dev/null)"; then
    return 1
  fi

  STATUS_PAYLOAD="$payload" EXPECTED_DATA_DIR="$DATA_DIR" "$PYTHON_BIN" -c '
import json
import os
import sys

try:
    payload = json.loads(os.environ["STATUS_PAYLOAD"])
except json.JSONDecodeError:
    raise SystemExit(1)

raise SystemExit(0 if payload.get("data_root") == os.environ["EXPECTED_DATA_DIR"] else 1)
'
}

pick_port() {
  local port="$DEFAULT_PORT"
  local max_port=$((DEFAULT_PORT + 50))

  while (( port <= max_port )); do
    if port_has_personal_pm "$port"; then
      echo "$port"
      return 0
    fi
    if ! port_in_use "$port"; then
      echo "$port"
      return 0
    fi
    port=$((port + 1))
  done

  echo "No available Personal PM port found from $DEFAULT_PORT to $max_port" >&2
  return 1
}

wait_for_app() {
  local port="$1"
  local i

  for i in {1..40}; do
    if port_has_personal_pm "$port"; then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

start_app_if_needed() {
  local port="$1"

  if port_has_personal_pm "$port"; then
    echo "Personal PM app already running at http://$HOST:$port"
    return 0
  fi

  echo "Starting Personal PM app at http://$HOST:$port"
  mkdir -p "$(dirname "$APP_STDOUT_LOG")" "$(dirname "$APP_STDERR_LOG")"
  (
    cd "$REPO_ROOT"
    exec nohup env PERSONAL_PM_DATA_DIR="$DATA_DIR" PERSONAL_PM_PORT="$port" PYTHONPATH="$REPO_ROOT/app" PATH="$PYTHON_BIN_DIR:$PATH" \
      "$PYTHON_BIN" -m flask --app server run --host "$HOST" --port "$port" \
      >"$APP_STDOUT_LOG" 2>"$APP_STDERR_LOG"
  ) &
  disown 2>/dev/null || true

  if wait_for_app "$port"; then
    return 0
  fi

  echo "Personal PM app did not become ready. Check $APP_STDERR_LOG" >&2
  return 1
}

open_app() {
  local port="$1"
  local url="http://$HOST:$port"

  if [[ "${PERSONAL_PM_DRY_RUN:-0}" == "1" ]]; then
    echo "Dry run: would open $url"
    return 0
  fi

  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 || echo "Open failed; use $url"
  else
    echo "Open $url"
  fi
}

if [[ ! -x "$RUNNER" ]]; then
  echo "Missing or non-executable autonomous runner: $RUNNER" >&2
  exit 1
fi

STATE="$(planner_state)"
NEEDS_RUN="$(json_field needs_run "$STATE")"
REASON="$(json_field reason "$STATE")"

echo "personal-pm morning"
echo "repo: $REPO_ROOT"
echo "data root: $DATA_DIR"
echo "python: $PYTHON_BIN"
echo "state: $REASON"

run_exit=0
if [[ "$NEEDS_RUN" == "True" || "$NEEDS_RUN" == "true" ]]; then
  if [[ "${PERSONAL_PM_DRY_RUN:-0}" == "1" ]]; then
    echo "Dry run: would run $RUNNER"
  else
    echo "Running autonomous daily workflow..."
    set +e
    PERSONAL_PM_DATA_DIR="$DATA_DIR" PATH="$PYTHON_BIN_DIR:$PATH" "$RUNNER"
    run_exit=$?
    set -e
    if (( run_exit != 0 )); then
      echo "Autonomous daily workflow exited with code $run_exit; opening the app for review."
    fi
  fi
else
  echo "Skipping autonomous workflow."
fi

PORT="$(pick_port)"
if [[ "${PERSONAL_PM_DRY_RUN:-0}" == "1" ]]; then
  echo "Dry run: would start or reuse Personal PM app on port $PORT"
  open_app "$PORT"
  exit "$run_exit"
fi

start_app_if_needed "$PORT"
open_app "$PORT"
exit "$run_exit"
