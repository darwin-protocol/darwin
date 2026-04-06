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

DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
BASE_SEPOLIA_RPC_URL="${BASE_SEPOLIA_RPC_URL:-${DARWIN_RPC_URL:-https://base-sepolia-rpc.publicnode.com}}"
STATE_ROOT="${DARWIN_STATE_ROOT:-$ROOT/ops/state/base-sepolia-canary}"
LOG_DIR="$STATE_ROOT/logs"
REPORT_DIR="$STATE_ROOT/reports"
WATCHER_ARCHIVE_URL="${DARWIN_WATCHER_ARCHIVE_URL:-http://127.0.0.1:9447}"
WATCHER_POLL_SEC="${DARWIN_WATCHER_POLL_SEC:-60}"
FINALIZER_POLL_SEC="${DARWIN_FINALIZER_POLL_SEC:-60}"
HEARTBEAT_SEC="${DARWIN_HEARTBEAT_SEC:-30}"
CHALLENGE_WINDOW_SEC="${DARWIN_CHALLENGE_WINDOW_SEC:-1800}"
SEED_DIR="${DARWIN_CANARY_SEED_DIR:-}"
SEED_EPOCH_ID="${DARWIN_CANARY_SEED_EPOCH_ID:-canary-1}"

if [[ ! -f "$DEPLOYMENT_FILE" ]]; then
  echo "Missing deployment artifact: $DEPLOYMENT_FILE" >&2
  exit 1
fi

if [[ -n "$SEED_DIR" ]]; then
  if [[ ! -d "$SEED_DIR" ]]; then
    echo "Seed artifact directory not found: $SEED_DIR" >&2
    exit 1
  fi
  SEED_DIR="$(cd "$SEED_DIR" && pwd)"
fi

mkdir -p \
  "$STATE_ROOT/gateway" \
  "$STATE_ROOT/router" \
  "$STATE_ROOT/archive" \
  "$STATE_ROOT/watcher" \
  "$STATE_ROOT/finalizer" \
  "$STATE_ROOT/sentinel" \
  "$LOG_DIR" \
  "$REPORT_DIR"

export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"
export DARWIN_DEPLOYMENT_FILE="$DEPLOYMENT_FILE"
export DARWIN_NETWORK="base-sepolia"
export DARWIN_WATCHER_POLL_SEC="$WATCHER_POLL_SEC"

pids=()
services=()
heartbeat_pid=""

cleanup() {
  set +e
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
        -d "{\"service\":\"$service\"}" \
        "http://127.0.0.1:9449/v1/heartbeat" >/dev/null 2>&1 || true
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
  if [[ "$phase" == "cold" ]]; then
    "$PYTHON_BIN" -m darwin_sim.cli.darwinctl status-check \
      --archive-url "http://127.0.0.1:9447" \
      --gateway-url "http://127.0.0.1:9443" \
      --router-url "http://127.0.0.1:9444" \
      --scorer-url "http://127.0.0.1:9445" \
      --watcher-url "http://127.0.0.1:9446" \
      --finalizer-url "http://127.0.0.1:9448" \
      --sentinel-url "http://127.0.0.1:9449" \
      --deployment-file "$DEPLOYMENT_FILE" \
      --base-rpc-url "$BASE_SEPOLIA_RPC_URL" \
      --json-out "$phase_json" \
      --markdown-out "$phase_md" \
      --allow-cold-watcher
  else
    "$PYTHON_BIN" -m darwin_sim.cli.darwinctl status-check \
      --archive-url "http://127.0.0.1:9447" \
      --gateway-url "http://127.0.0.1:9443" \
      --router-url "http://127.0.0.1:9444" \
      --scorer-url "http://127.0.0.1:9445" \
      --watcher-url "http://127.0.0.1:9446" \
      --finalizer-url "http://127.0.0.1:9448" \
      --sentinel-url "http://127.0.0.1:9449" \
      --deployment-file "$DEPLOYMENT_FILE" \
      --base-rpc-url "$BASE_SEPOLIA_RPC_URL" \
      --json-out "$phase_json" \
      --markdown-out "$phase_md"
  fi

  cp "$phase_json" "$latest_json"
  cp "$phase_md" "$latest_md"
}

start_service gateway "$PYTHON_BIN" "$ROOT/overlay/gateway/server.py" 9443 "$STATE_ROOT/gateway"
start_service router "$PYTHON_BIN" "$ROOT/overlay/router/service.py" 9444 1500 "$STATE_ROOT/router/state.json"
start_service scorer "$PYTHON_BIN" "$ROOT/overlay/scorer/service.py" 9445
start_service archive "$PYTHON_BIN" "$ROOT/overlay/archive/service.py" 9447 "$STATE_ROOT/archive"
start_service watcher "$PYTHON_BIN" "$ROOT/overlay/watcher/service.py" 9446 "$STATE_ROOT/watcher" "$WATCHER_ARCHIVE_URL"
start_service finalizer "$PYTHON_BIN" "$ROOT/overlay/finalizer/service.py" 9448 "$CHALLENGE_WINDOW_SEC" "$STATE_ROOT/finalizer/state.json" "$FINALIZER_POLL_SEC"
start_service sentinel "$PYTHON_BIN" "$ROOT/overlay/sentinel/service.py" 9449 "$STATE_ROOT/sentinel/state.json"

wait_healthy gateway 9443
wait_healthy router 9444
wait_healthy scorer 9445
wait_healthy archive 9447
wait_healthy watcher 9446
wait_healthy finalizer 9448
wait_healthy sentinel 9449

heartbeat_loop &
heartbeat_pid=$!

run_status_check cold

if [[ -n "$SEED_DIR" ]]; then
  ingest_payload=$(printf '{"epoch_id":"%s","source_dir":"%s"}' "$SEED_EPOCH_ID" "$SEED_DIR")
  curl -fsS \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$ingest_payload" \
    "http://127.0.0.1:9447/v1/ingest" >/dev/null

  curl -fsS \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{}' \
    "http://127.0.0.1:9446/v1/replay/latest" >/dev/null

  run_status_check warm
fi

echo
echo "DARWIN Base Sepolia canary stack is running."
echo "  deployment: $DEPLOYMENT_FILE"
echo "  state_root:  $STATE_ROOT"
echo "  archive_url: $WATCHER_ARCHIVE_URL"
echo "  logs:        $LOG_DIR"
echo "  reports:     $REPORT_DIR"
if [[ -n "$SEED_DIR" ]]; then
  echo "  watcher:     seeded from $SEED_DIR as epoch $SEED_EPOCH_ID"
else
  echo "  watcher:     cold start allowed until the first archive replay"
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
