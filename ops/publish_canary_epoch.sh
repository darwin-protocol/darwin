#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

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
require_cmd cp

EPOCH_ID="${1:-${DARWIN_CANARY_EPOCH_ID:-}}"
SOURCE_DIR="${2:-${DARWIN_CANARY_SOURCE_DIR:-}}"

if [[ -z "$EPOCH_ID" || -z "$SOURCE_DIR" ]]; then
  echo "Usage: $0 <epoch_id> <source_dir>" >&2
  echo "Or export DARWIN_CANARY_EPOCH_ID and DARWIN_CANARY_SOURCE_DIR." >&2
  exit 1
fi

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Source directory not found: $SOURCE_DIR" >&2
  exit 1
fi

ARCHIVE_URL="${DARWIN_ARCHIVE_URL:-http://127.0.0.1:9447}"
WATCHER_URL="${DARWIN_WATCHER_URL:-http://127.0.0.1:9446}"
GATEWAY_URL="${DARWIN_GATEWAY_URL:-http://127.0.0.1:9443}"
ROUTER_URL="${DARWIN_ROUTER_URL:-http://127.0.0.1:9444}"
SCORER_URL="${DARWIN_SCORER_URL:-http://127.0.0.1:9445}"
FINALIZER_URL="${DARWIN_FINALIZER_URL:-http://127.0.0.1:9448}"
SENTINEL_URL="${DARWIN_SENTINEL_URL:-http://127.0.0.1:9449}"
DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
BASE_SEPOLIA_RPC_URL="${BASE_SEPOLIA_RPC_URL:-${DARWIN_RPC_URL:-https://base-sepolia-rpc.publicnode.com}}"
REPORT_DIR="${DARWIN_CANARY_REPORT_DIR:-$ROOT/ops/state/base-sepolia-canary/reports}"
RUN_STATUS_CHECK="${DARWIN_CANARY_RUN_STATUS_CHECK:-1}"

mkdir -p "$REPORT_DIR"
export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"
AUTH_ARGS=()
if [[ -n "${DARWIN_ADMIN_TOKEN:-}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${DARWIN_ADMIN_TOKEN}")
fi

ingest_json="$REPORT_DIR/publish-${EPOCH_ID}-ingest.json"
replay_json="$REPORT_DIR/publish-${EPOCH_ID}-replay.json"
summary_json="$REPORT_DIR/publish-${EPOCH_ID}-summary.json"
summary_md="$REPORT_DIR/publish-${EPOCH_ID}-summary.md"

ingest_payload=$(printf '{"epoch_id":"%s","source_dir":"%s"}' "$EPOCH_ID" "$(cd "$SOURCE_DIR" && pwd)")
curl -fsS \
  -X POST \
  -H "Content-Type: application/json" \
  ${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"} \
  -d "$ingest_payload" \
  "${ARCHIVE_URL%/}/v1/ingest" >"$ingest_json"

replay_payload=$(printf '{"epoch_id":"%s"}' "$EPOCH_ID")
curl -fsS \
  -X POST \
  -H "Content-Type: application/json" \
  ${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"} \
  -d "$replay_payload" \
  "${WATCHER_URL%/}/v1/replay/archive" >"$replay_json"

status_json=""
status_md=""
if [[ "$RUN_STATUS_CHECK" == "1" ]]; then
  status_json="$REPORT_DIR/status-after-${EPOCH_ID}.json"
  status_md="$REPORT_DIR/status-after-${EPOCH_ID}.md"
  "$PYTHON_BIN" -m darwin_sim.cli.darwinctl status-check \
    --archive-url "$ARCHIVE_URL" \
    --gateway-url "$GATEWAY_URL" \
    --router-url "$ROUTER_URL" \
    --scorer-url "$SCORER_URL" \
    --watcher-url "$WATCHER_URL" \
    --finalizer-url "$FINALIZER_URL" \
    --sentinel-url "$SENTINEL_URL" \
    --deployment-file "$DEPLOYMENT_FILE" \
    --base-rpc-url "$BASE_SEPOLIA_RPC_URL" \
    --json-out "$status_json" \
    --markdown-out "$status_md"

  cp "$status_json" "$REPORT_DIR/status-report.json"
  cp "$status_md" "$REPORT_DIR/status-report.md"
fi

"$PYTHON_BIN" - "$ingest_json" "$replay_json" "$summary_json" "$summary_md" "$status_json" "$EPOCH_ID" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ingest_path = Path(sys.argv[1])
replay_path = Path(sys.argv[2])
summary_json_path = Path(sys.argv[3])
summary_md_path = Path(sys.argv[4])
status_json_path = Path(sys.argv[5]) if sys.argv[5] else None
epoch_id = sys.argv[6]

ingest = json.loads(ingest_path.read_text())
replay = json.loads(replay_path.read_text())
status = json.loads(status_json_path.read_text()) if status_json_path and status_json_path.exists() else {}

summary = {
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "epoch_id": epoch_id,
    "archive_ingest": ingest,
    "watcher_replay": replay,
    "status_check": status,
    "ready": bool(status.get("ready", replay.get("passed", False))),
}
summary_json_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")

lines = [
    "# DARWIN Canary Epoch Publish",
    "",
    f"- Generated at: `{summary['generated_at']}`",
    f"- Epoch: `{epoch_id}`",
    f"- Archive ingest: `{ingest.get('status', '')}` with `{ingest.get('files', 0)}` files",
    f"- Watcher replay: `{'PASS' if replay.get('passed') else 'FAIL'}`",
    f"- Ready after publish: `{summary['ready']}`",
]
if replay.get("mismatches"):
    lines.extend(["", "## Replay Mismatches", ""])
    lines.extend(f"- `{mismatch}`" for mismatch in replay["mismatches"])
if status:
    lines.extend([
        "",
        "## Status Snapshot",
        "",
        f"- Overall status: `{'READY' if status.get('ready') else 'BLOCKED'}`",
        f"- Deployment: `{status.get('deployment', {}).get('network', '')}`",
    ])
    blockers = status.get("blockers", [])
    lines.extend(["", "## Blockers", ""])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")

summary_md_path.write_text("\n".join(lines) + "\n")
PY

echo "Published DARWIN canary epoch."
echo "  epoch:        $EPOCH_ID"
echo "  source_dir:   $(cd "$SOURCE_DIR" && pwd)"
echo "  ingest:       $ingest_json"
echo "  replay:       $replay_json"
echo "  summary:      $summary_md"
if [[ -n "$status_json" ]]; then
  echo "  status:       $status_json"
fi
