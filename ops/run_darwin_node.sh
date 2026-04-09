#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

resolve_python() {
  if [[ -n "${DARWIN_PYTHON_BIN:-}" ]]; then
    echo "$DARWIN_PYTHON_BIN"
    return 0
  fi
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
    return 0
  fi
  echo "python3"
}

default_deployment_file() {
  if [[ -f "$ROOT/ops/deployments/base-sepolia-recovery.json" ]]; then
    echo "$ROOT/ops/deployments/base-sepolia-recovery.json"
  else
    echo "$ROOT/ops/deployments/base-sepolia.json"
  fi
}

default_rpc_url() {
  case "$1" in
    84532) echo "https://sepolia.base.org" ;;
    8453) echo "https://mainnet.base.org" ;;
    421614) echo "https://sepolia-rollup.arbitrum.io/rpc" ;;
    42161) echo "https://arb1.arbitrum.io/rpc" ;;
    *) echo "" ;;
  esac
}

PYTHON_BIN="$(resolve_python)"
if [[ "$PYTHON_BIN" != */* ]]; then
  require_cmd "$PYTHON_BIN"
elif [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not executable: $PYTHON_BIN" >&2
  exit 1
fi

require_cmd curl

DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$(default_deployment_file)}"
if [[ ! -f "$DEPLOYMENT_FILE" ]]; then
  echo "Missing deployment artifact: $DEPLOYMENT_FILE" >&2
  exit 1
fi

read -r RESOLVED_NETWORK RESOLVED_CHAIN_ID RESOLVED_SETTLEMENT_HUB <<EOF
$("$PYTHON_BIN" - "$DEPLOYMENT_FILE" <<'PY'
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
contracts = data.get("contracts") or {}
print(data["network"], int(data["chain_id"]), contracts.get("settlement_hub", ""))
PY
)
EOF

export DARWIN_DEPLOYMENT_FILE="$DEPLOYMENT_FILE"
export DARWIN_NETWORK="${DARWIN_NETWORK:-$RESOLVED_NETWORK}"
export DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-$RESOLVED_CHAIN_ID}"
export DARWIN_RPC_URL="${DARWIN_RPC_URL:-$(default_rpc_url "$RESOLVED_CHAIN_ID")}"
export DARWIN_BIND_HOST="${DARWIN_BIND_HOST:-127.0.0.1}"

if [[ "$DARWIN_BIND_HOST" != "127.0.0.1" && "$DARWIN_BIND_HOST" != "::1" && "$DARWIN_BIND_HOST" != "localhost" ]]; then
  if [[ -z "${DARWIN_ADMIN_TOKEN:-}" ]]; then
    echo "DARWIN_ADMIN_TOKEN is required when DARWIN_BIND_HOST exposes the overlay off-host" >&2
    exit 1
  fi
fi

STATE_ROOT="${DARWIN_STATE_ROOT:-$ROOT/ops/state/${DARWIN_NETWORK}-node}"
LOG_DIR="$STATE_ROOT/logs"
REPORT_DIR="$STATE_ROOT/reports"
PID_FILE="${DARWIN_NODE_PID_FILE:-$STATE_ROOT/darwin-node.pid}"

GATEWAY_PORT="${DARWIN_GATEWAY_PORT:-9443}"
ROUTER_PORT="${DARWIN_ROUTER_PORT:-9444}"
SCORER_PORT="${DARWIN_SCORER_PORT:-9445}"
WATCHER_PORT="${DARWIN_WATCHER_PORT:-9446}"
ARCHIVE_PORT="${DARWIN_ARCHIVE_PORT:-9447}"
FINALIZER_PORT="${DARWIN_FINALIZER_PORT:-9448}"
SENTINEL_PORT="${DARWIN_SENTINEL_PORT:-9449}"

WATCHER_ARCHIVE_URL="${DARWIN_WATCHER_ARCHIVE_URL:-http://127.0.0.1:${ARCHIVE_PORT}}"
WATCHER_POLL_SEC="${DARWIN_WATCHER_POLL_SEC:-60}"
FINALIZER_POLL_SEC="${DARWIN_FINALIZER_POLL_SEC:-60}"
HEARTBEAT_SEC="${DARWIN_HEARTBEAT_SEC:-30}"
CHALLENGE_WINDOW_SEC="${DARWIN_CHALLENGE_WINDOW_SEC:-1800}"
ALLOW_COLD_WATCHER="${DARWIN_NODE_ALLOW_COLD_WATCHER:-1}"
STRICT_STATUS_CHECK="${DARWIN_NODE_STRICT_STATUS_CHECK:-0}"
SEED_DIR="${DARWIN_NODE_SEED_DIR:-}"
SEED_EPOCH_ID="${DARWIN_NODE_SEED_EPOCH_ID:-node-1}"

mkdir -p \
  "$STATE_ROOT/gateway" \
  "$STATE_ROOT/router" \
  "$STATE_ROOT/archive" \
  "$STATE_ROOT/watcher" \
  "$STATE_ROOT/finalizer" \
  "$STATE_ROOT/sentinel" \
  "$LOG_DIR" \
  "$REPORT_DIR"

"$PYTHON_BIN" "$ROOT/ops/preflight_darwin_node.py" \
  --deployment-file "$DEPLOYMENT_FILE" \
  --rpc-url "$DARWIN_RPC_URL" \
  --state-root "$STATE_ROOT" \
  --gateway-port "$GATEWAY_PORT" \
  --router-port "$ROUTER_PORT" \
  --scorer-port "$SCORER_PORT" \
  --watcher-port "$WATCHER_PORT" \
  --archive-port "$ARCHIVE_PORT" \
  --finalizer-port "$FINALIZER_PORT" \
  --sentinel-port "$SENTINEL_PORT" \
  --json-out "$REPORT_DIR/node-preflight.json" \
  --markdown-out "$REPORT_DIR/node-preflight.md"

if [[ -n "$SEED_DIR" ]]; then
  if [[ ! -d "$SEED_DIR" ]]; then
    echo "Seed artifact directory not found: $SEED_DIR" >&2
    exit 1
  fi
  SEED_DIR="$(cd "$SEED_DIR" && pwd)"
fi

export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"

pids=()
services=()
heartbeat_pid=""
AUTH_ARGS=()
if [[ -n "${DARWIN_ADMIN_TOKEN:-}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${DARWIN_ADMIN_TOKEN}")
fi

cleanup() {
  set +e
  rm -f "$PID_FILE"
  if [[ -n "$heartbeat_pid" ]] && kill -0 "$heartbeat_pid" 2>/dev/null; then
    kill "$heartbeat_pid" 2>/dev/null || true
  fi
  for pid in "${pids[@]}"; do
    kill "$pid" 2>/dev/null || true
  done
  for pid in "${pids[@]}"; do
    wait "$pid" 2>/dev/null || true
  done
  if [[ -n "$heartbeat_pid" ]]; then
    wait "$heartbeat_pid" 2>/dev/null || true
  fi
}

terminate() {
  cleanup
  exit 0
}

trap cleanup EXIT
trap terminate INT TERM

start_service() {
  local name="$1"
  shift
  local log_file="$LOG_DIR/$name.log"
  "$@" >"$log_file" 2>&1 &
  local pid=$!
  services+=("$name")
  pids+=("$pid")
  echo "started $name pid=$pid log=$log_file"
}

wait_healthy() {
  local name="$1"
  local port="$2"
  for _ in {1..100}; do
    if curl -fsS "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
      echo "healthy $name :$port"
      return 0
    fi
    sleep 0.2
  done
  echo "service failed health check: $name :$port" >&2
  return 1
}

heartbeat_loop() {
  while true; do
    for service in archive gateway router scorer watcher finalizer; do
      curl -fsS \
        -X POST \
        -H "Content-Type: application/json" \
        "${AUTH_ARGS[@]}" \
        -d "{\"service\":\"$service\"}" \
        "http://127.0.0.1:${SENTINEL_PORT}/v1/heartbeat" >/dev/null 2>&1 || true
    done
    sleep "$HEARTBEAT_SEC"
  done
}

run_status_check() {
  local phase="${1:-warm}"
  local latest_json="$REPORT_DIR/status-report.json"
  local latest_md="$REPORT_DIR/status-report.md"
  local phase_json="$REPORT_DIR/status-${phase}.json"
  local phase_md="$REPORT_DIR/status-${phase}.md"
  local rc=0

  local args=(
    -m darwin_sim.cli.darwinctl status-check
    --archive-url "http://127.0.0.1:${ARCHIVE_PORT}"
    --gateway-url "http://127.0.0.1:${GATEWAY_PORT}"
    --router-url "http://127.0.0.1:${ROUTER_PORT}"
    --scorer-url "http://127.0.0.1:${SCORER_PORT}"
    --watcher-url "http://127.0.0.1:${WATCHER_PORT}"
    --finalizer-url "http://127.0.0.1:${FINALIZER_PORT}"
    --sentinel-url "http://127.0.0.1:${SENTINEL_PORT}"
    --deployment-file "$DEPLOYMENT_FILE"
    --rpc-url "$DARWIN_RPC_URL"
    --json-out "$phase_json"
    --markdown-out "$phase_md"
  )

  if [[ "$phase" == "cold" && "$ALLOW_COLD_WATCHER" == "1" ]]; then
    args+=(--allow-cold-watcher)
  fi

  if ! "$PYTHON_BIN" "${args[@]}"; then
    rc=$?
  fi

  if [[ -f "$phase_json" ]]; then
    cp "$phase_json" "$latest_json"
  fi
  if [[ -f "$phase_md" ]]; then
    cp "$phase_md" "$latest_md"
  fi

  if [[ "$rc" -ne 0 ]]; then
    echo "status-check reported warnings/failures during ${phase} phase (exit=${rc})" >&2
    if [[ "$STRICT_STATUS_CHECK" == "1" ]]; then
      return "$rc"
    fi
  fi
}

echo "$$" >"$PID_FILE"

start_service gateway "$PYTHON_BIN" "$ROOT/overlay/gateway/server.py" "$GATEWAY_PORT" "$STATE_ROOT/gateway"
start_service router "$PYTHON_BIN" "$ROOT/overlay/router/service.py" "$ROUTER_PORT" 1500 "$STATE_ROOT/router/state.json"
start_service scorer "$PYTHON_BIN" "$ROOT/overlay/scorer/service.py" "$SCORER_PORT"
start_service archive "$PYTHON_BIN" "$ROOT/overlay/archive/service.py" "$ARCHIVE_PORT" "$STATE_ROOT/archive"
start_service watcher "$PYTHON_BIN" "$ROOT/overlay/watcher/service.py" "$WATCHER_PORT" "$STATE_ROOT/watcher" "$WATCHER_ARCHIVE_URL" "$WATCHER_POLL_SEC"
start_service finalizer "$PYTHON_BIN" "$ROOT/overlay/finalizer/service.py" "$FINALIZER_PORT" "$CHALLENGE_WINDOW_SEC" "$STATE_ROOT/finalizer/state.json" "$FINALIZER_POLL_SEC"
start_service sentinel "$PYTHON_BIN" "$ROOT/overlay/sentinel/service.py" "$SENTINEL_PORT" "$STATE_ROOT/sentinel/state.json"

wait_healthy gateway "$GATEWAY_PORT"
wait_healthy router "$ROUTER_PORT"
wait_healthy scorer "$SCORER_PORT"
wait_healthy archive "$ARCHIVE_PORT"
wait_healthy watcher "$WATCHER_PORT"
wait_healthy finalizer "$FINALIZER_PORT"
wait_healthy sentinel "$SENTINEL_PORT"

heartbeat_loop &
heartbeat_pid=$!

run_status_check cold

if [[ -n "$SEED_DIR" ]]; then
  ingest_payload=$(printf '{"epoch_id":"%s","source_dir":"%s"}' "$SEED_EPOCH_ID" "$SEED_DIR")
  curl -fsS \
    -X POST \
    -H "Content-Type: application/json" \
    "${AUTH_ARGS[@]}" \
    -d "$ingest_payload" \
    "http://127.0.0.1:${ARCHIVE_PORT}/v1/ingest" >/dev/null

  curl -fsS \
    -X POST \
    -H "Content-Type: application/json" \
    "${AUTH_ARGS[@]}" \
    -d '{}' \
    "http://127.0.0.1:${WATCHER_PORT}/v1/replay/latest" >/dev/null

  run_status_check warm
fi

echo
echo "DARWIN overlay node is running."
echo "  deployment:   $DEPLOYMENT_FILE"
echo "  network:      $DARWIN_NETWORK"
echo "  chain_id:     $DARWIN_EXPECT_CHAIN_ID"
echo "  rpc_url:      $DARWIN_RPC_URL"
echo "  bind_host:    $DARWIN_BIND_HOST"
echo "  state_root:   $STATE_ROOT"
echo "  archive_url:  $WATCHER_ARCHIVE_URL"
echo "  admin_token:  $([[ -n "${DARWIN_ADMIN_TOKEN:-}" ]] && echo enabled || echo disabled)"
echo "  logs:         $LOG_DIR"
echo "  reports:      $REPORT_DIR"
echo "  pid_file:     $PID_FILE"
if [[ -n "$SEED_DIR" ]]; then
  echo "  watcher:      seeded from $SEED_DIR as epoch $SEED_EPOCH_ID"
elif [[ "$ALLOW_COLD_WATCHER" == "1" ]]; then
  echo "  watcher:      cold start allowed until the first archive replay"
else
  echo "  watcher:      requires a replay before readiness turns green"
fi
echo
echo "Press Ctrl-C to stop."

while true; do
  for i in "${!pids[@]}"; do
    if ! kill -0 "${pids[$i]}" 2>/dev/null; then
      echo "service exited unexpectedly: ${services[$i]}" >&2
      exit 1
    fi
  done
  sleep 5
done
