#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

load_env_defaults() {
  local env_file="$1"
  local key value
  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    [[ -z "$key" ]] && continue
    [[ "$key" == \#* ]] && continue
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$env_file" || true)
}

ENV_FILE="${DARWIN_WATCHER_ENV_FILE:-$ROOT/.env.external-watcher}"
if [[ -f "$ENV_FILE" ]]; then
  load_env_defaults "$ENV_FILE"
fi

PYTHON_BIN="${DARWIN_PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if [[ "$PYTHON_BIN" != */* ]]; then
  require_cmd "$PYTHON_BIN"
elif [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not executable: $PYTHON_BIN" >&2
  exit 1
fi

require_cmd curl

WATCHER_PORT="${DARWIN_WATCHER_PORT:-9446}"
ARCHIVE_URL="${DARWIN_WATCHER_ARCHIVE_URL:-}"
STATE_ROOT="${DARWIN_WATCHER_STATE_ROOT:-$ROOT/ops/state/external-watcher}"
ARTIFACT_DIR="$STATE_ROOT/artifacts"
LOG_DIR="$STATE_ROOT/logs"
REPORT_DIR="$STATE_ROOT/reports"
WATCHER_POLL_SEC="${DARWIN_WATCHER_POLL_SEC:-60}"
PRIME_LATEST="${DARWIN_WATCHER_PRIME_LATEST:-1}"

if [[ -z "$ARCHIVE_URL" ]]; then
  echo "DARWIN_WATCHER_ARCHIVE_URL is required" >&2
  exit 1
fi

mkdir -p "$ARTIFACT_DIR" "$LOG_DIR" "$REPORT_DIR"

export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"
pid=""

cleanup() {
  set +e
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
  fi
}

terminate() {
  cleanup
  exit 0
}

trap cleanup EXIT
trap terminate INT TERM

write_report() {
  local ready_json="$REPORT_DIR/watcher-ready.json"
  local status_json="$REPORT_DIR/watcher-status.json"
  local archive_json="$REPORT_DIR/archive-epochs.json"
  local report_md="$REPORT_DIR/watcher-status.md"
  local ready_tmp status_tmp archive_tmp report_tmp
  local ready_body="{}"
  local ready_state="NO"

  ready_tmp="$(mktemp "$REPORT_DIR/.watcher-ready.XXXXXX")"
  status_tmp="$(mktemp "$REPORT_DIR/.watcher-status.XXXXXX")"
  archive_tmp="$(mktemp "$REPORT_DIR/.archive-epochs.XXXXXX")"
  report_tmp="$(mktemp "$REPORT_DIR/.watcher-status-md.XXXXXX")"

  if curl -fsS "http://127.0.0.1:${WATCHER_PORT}/readyz" >"$ready_tmp" 2>/dev/null; then
    ready_state="YES"
  elif curl -fsS "http://127.0.0.1:${WATCHER_PORT}/healthz" >/dev/null 2>&1; then
    printf '{"ready": false}\n' >"$ready_tmp"
    ready_state="COLD"
  fi

  curl -fsS "http://127.0.0.1:${WATCHER_PORT}/v1/status" >"$status_tmp"
  curl -fsS "${ARCHIVE_URL%/}/v1/epochs" >"$archive_tmp"

  "$PYTHON_BIN" - "$status_tmp" "$ready_tmp" "$archive_tmp" "$report_tmp" "$ready_state" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

status_path = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
archive_path = Path(sys.argv[3])
report_path = Path(sys.argv[4])
ready_state = sys.argv[5]

status = json.loads(status_path.read_text())
ready = json.loads(ready_path.read_text())
archive = json.loads(archive_path.read_text())
health = status.get("health", {})
epochs = archive.get("epochs", [])

def epoch_key(epoch):
    epoch_id = str(epoch.get("epoch_id", ""))
    try:
        return (0, int(epoch_id))
    except ValueError:
        return (1, epoch_id)

epochs = sorted(epochs, key=epoch_key)
latest = epochs[-1]["epoch_id"] if epochs else ""

lines = [
    "# DARWIN External Watcher Report",
    "",
    f"- Generated at: `{datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')}`",
    f"- Watcher readiness: `{ready_state}`",
    f"- Epochs replayed: `{health.get('epochs_replayed', 0)}`",
    f"- Last mirrored epoch: `{health.get('last_mirrored_epoch', '')}`",
    f"- Archive latest epoch: `{latest}`",
    f"- Auto-sync: `{health.get('auto_sync', False)}` every `{health.get('poll_interval_sec', 0)}`s",
    "",
    "## Epoch Results",
    "",
]

epoch_rows = status.get("epochs", {})
if not epoch_rows:
    lines.append("- none")
else:
    for epoch_id, epoch_status in sorted(epoch_rows.items(), key=lambda item: item[0]):
        lines.append(
            f"- epoch `{epoch_id}`: passed=`{epoch_status.get('passed', False)}` mismatches=`{epoch_status.get('mismatches', 0)}`"
        )

if ready_state != "YES":
    lines.extend(["", "## Blockers", "", "- watcher still needs a successful archive replay before it is ready"])

report_path.write_text("\n".join(lines) + "\n")
PY

  mv "$ready_tmp" "$ready_json"
  mv "$archive_tmp" "$archive_json"
  mv "$report_tmp" "$report_md"
  mv "$status_tmp" "$status_json"
}

log_file="$LOG_DIR/watcher.log"
"$PYTHON_BIN" "$ROOT/overlay/watcher/service.py" "$WATCHER_PORT" "$ARTIFACT_DIR" "$ARCHIVE_URL" "$WATCHER_POLL_SEC" >"$log_file" 2>&1 &
pid=$!

for _ in {1..100}; do
  if curl -fsS "http://127.0.0.1:${WATCHER_PORT}/healthz" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

if ! curl -fsS "http://127.0.0.1:${WATCHER_PORT}/healthz" >/dev/null 2>&1; then
  echo "watcher failed health check on :${WATCHER_PORT}" >&2
  exit 1
fi

if [[ "$PRIME_LATEST" == "1" ]]; then
  curl -fsS -X POST -H "Content-Type: application/json" -d '{}' \
    "http://127.0.0.1:${WATCHER_PORT}/v1/replay/latest" >/dev/null 2>&1 || true
fi

write_report

echo "DARWIN external watcher is running."
echo "  archive_url: $ARCHIVE_URL"
echo "  port:        $WATCHER_PORT"
echo "  state_root:  $STATE_ROOT"
echo "  log:         $log_file"
echo "  report:      $REPORT_DIR/watcher-status.md"
if [[ -f "$ENV_FILE" ]]; then
  echo "  env_file:    $ENV_FILE"
fi
echo
echo "Press Ctrl-C to stop."

while true; do
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "watcher exited unexpectedly" >&2
    exit 1
  fi
  write_report
  sleep 10
done
