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

GATEWAY_URL="${DARWIN_GATEWAY_URL:-http://127.0.0.1:9443}"
ROUTER_URL="${DARWIN_ROUTER_URL:-http://127.0.0.1:9444}"
DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
STATE_ROOT="${DARWIN_STATE_ROOT:-$ROOT/ops/state/base-sepolia-canary}"
REPORT_DIR="${DARWIN_INTENT_SMOKE_REPORT_DIR:-$STATE_ROOT/reports}"
WALLET_LABEL="${DARWIN_WALLET_LABEL:-darwin-smoke-trader}"
PAIR="${DARWIN_INTENT_PAIR:-ETH_USDC}"
SIDE="${DARWIN_INTENT_SIDE:-BUY}"
QTY="${DARWIN_INTENT_QTY:-1.0}"
PRICE="${DARWIN_INTENT_PRICE:-3500.0}"
SLIPPAGE="${DARWIN_INTENT_SLIPPAGE:-50}"
PROFILE="${DARWIN_INTENT_PROFILE:-BALANCED}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
INTENT_NONCE="${DARWIN_INTENT_NONCE:-$("$PYTHON_BIN" - <<'PY'
import time
print(time.time_ns() // 1_000_000)
PY
)}"

mkdir -p "$REPORT_DIR"
export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"

AUTH_ARGS=()
if [[ -n "${DARWIN_ADMIN_TOKEN:-}" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${DARWIN_ADMIN_TOKEN}")
fi

INTENT_FILE="$REPORT_DIR/smoke-intent-${STAMP}.json"
ADMISSION_JSON="$REPORT_DIR/smoke-intent-${STAMP}-admission.json"
ROUTE_JSON="$REPORT_DIR/smoke-intent-${STAMP}-route.json"
SUMMARY_JSON="$REPORT_DIR/smoke-intent-${STAMP}-summary.json"

before_gateway="$(curl -fsS "${GATEWAY_URL%/}/v1/stats")"
before_router="$(curl -fsS "${ROUTER_URL%/}/v1/stats")"

DARWIN_WALLET_LABEL="$WALLET_LABEL" \
DARWIN_INTENT_FILE="$INTENT_FILE" \
DARWIN_DEPLOYMENT_FILE="$DEPLOYMENT_FILE" \
DARWIN_INTENT_PAIR="$PAIR" \
DARWIN_INTENT_SIDE="$SIDE" \
DARWIN_INTENT_QTY="$QTY" \
DARWIN_INTENT_PRICE="$PRICE" \
DARWIN_INTENT_SLIPPAGE="$SLIPPAGE" \
DARWIN_INTENT_PROFILE="$PROFILE" \
DARWIN_INTENT_NONCE="$INTENT_NONCE" \
bash "$ROOT/ops/init_demo_wallet.sh" >/dev/null

curl -fsS \
  -X POST \
  -H "Content-Type: application/json" \
  -d @"$INTENT_FILE" \
  "${GATEWAY_URL%/}/v1/intents" >"$ADMISSION_JSON"

INTENT_ID="$("$PYTHON_BIN" - "$ADMISSION_JSON" <<'PY'
import json
import sys
payload = json.loads(open(sys.argv[1]).read())
intent_id = payload.get("intent_id", "")
if not intent_id:
    raise SystemExit("missing intent_id in gateway admission")
print(intent_id)
PY
)"

route_payload=$(printf '{"intent_id":"%s","profile":"%s"}' "$INTENT_ID" "$PROFILE")
curl -fsS \
  -X POST \
  -H "Content-Type: application/json" \
  ${AUTH_ARGS[@]+"${AUTH_ARGS[@]}"} \
  -d "$route_payload" \
  "${ROUTER_URL%/}/v1/route" >"$ROUTE_JSON"

after_gateway="$(curl -fsS "${GATEWAY_URL%/}/v1/stats")"
after_router="$(curl -fsS "${ROUTER_URL%/}/v1/stats")"

"$PYTHON_BIN" - "$INTENT_FILE" "$ADMISSION_JSON" "$ROUTE_JSON" "$SUMMARY_JSON" "$INTENT_NONCE" "$before_gateway" "$after_gateway" "$before_router" "$after_router" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

intent_path = Path(sys.argv[1])
admission_path = Path(sys.argv[2])
route_path = Path(sys.argv[3])
summary_path = Path(sys.argv[4])
intent_nonce = int(sys.argv[5])
before_gateway = json.loads(sys.argv[6])
after_gateway = json.loads(sys.argv[7])
before_router = json.loads(sys.argv[8])
after_router = json.loads(sys.argv[9])

intent = json.loads(intent_path.read_text())
admission = json.loads(admission_path.read_text())
route = json.loads(route_path.read_text())

summary = {
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "intent_nonce": intent_nonce,
    "intent_hash": intent.get("intent_hash", ""),
    "intent_file": str(intent_path),
    "admission": admission,
    "route": route,
    "gateway_delta": {
        "admitted": int(after_gateway.get("admitted", 0)) - int(before_gateway.get("admitted", 0)),
        "rejected": int(after_gateway.get("rejected", 0)) - int(before_gateway.get("rejected", 0)),
        "total": int(after_gateway.get("total", 0)) - int(before_gateway.get("total", 0)),
    },
    "router_delta": {
        "total_routed": int(after_router.get("total_routed", 0)) - int(before_router.get("total_routed", 0)),
    },
    "gateway_after": after_gateway,
    "router_after": after_router,
}
summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
PY

echo "Smoked DARWIN intent path."
echo "  intent_file:   $INTENT_FILE"
echo "  nonce:         $INTENT_NONCE"
echo "  admission:     $ADMISSION_JSON"
echo "  route:         $ROUTE_JSON"
echo "  summary:       $SUMMARY_JSON"
