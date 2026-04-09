#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DARWIN_NETWORK_PRESET="${DARWIN_NETWORK+x}"
DARWIN_DEPLOYMENT_FILE_PRESET="${DARWIN_DEPLOYMENT_FILE+x}"
DARWIN_EPOCH_ACTIVITY_REPORT_PRESET="${DARWIN_EPOCH_ACTIVITY_REPORT+x}"
DARWIN_EPOCH_REWARDS_FILE_PRESET="${DARWIN_EPOCH_REWARDS_FILE+x}"
DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE_PRESET="${DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE+x}"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

NETWORK_SLUG="${DARWIN_NETWORK:-base-sepolia-recovery}"
if [[ -n "$DARWIN_NETWORK_PRESET" && -z "$DARWIN_DEPLOYMENT_FILE_PRESET" ]]; then
  export DARWIN_DEPLOYMENT_FILE="$ROOT/ops/deployments/${NETWORK_SLUG}.json"
fi
if [[ -n "$DARWIN_NETWORK_PRESET" && -z "$DARWIN_EPOCH_ACTIVITY_REPORT_PRESET" ]]; then
  export DARWIN_EPOCH_ACTIVITY_REPORT="$ROOT/ops/state/activity/external-activity-${NETWORK_SLUG}.json"
fi
if [[ -n "$DARWIN_NETWORK_PRESET" && -z "$DARWIN_EPOCH_REWARDS_FILE_PRESET" ]]; then
  export DARWIN_EPOCH_REWARDS_FILE="$ROOT/ops/state/${NETWORK_SLUG}-epoch-rewards.json"
fi
if [[ -n "$DARWIN_NETWORK_PRESET" && -z "$DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE_PRESET" ]]; then
  export DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE="$ROOT/ops/deployments/${NETWORK_SLUG}.epoch-rewards.json"
fi

if [[ -n "${DARWIN_EPOCH_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$DARWIN_EPOCH_PYTHON_BIN"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

if [[ "$PYTHON_BIN" != */* ]]; then
  require_cmd "$PYTHON_BIN"
elif [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not executable: $PYTHON_BIN" >&2
  exit 1
fi

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${NETWORK_SLUG}.json}"
export DARWIN_EPOCH_FILE="${DARWIN_EPOCH_FILE:-$ROOT/ops/community_epoch.json}"
export DARWIN_EPOCH_ACTIVITY_REPORT="${DARWIN_EPOCH_ACTIVITY_REPORT:-$ROOT/ops/state/activity/external-activity-${NETWORK_SLUG}.json}"
export DARWIN_EPOCH_REWARDS_FILE="${DARWIN_EPOCH_REWARDS_FILE:-$ROOT/ops/state/${NETWORK_SLUG}-epoch-rewards.json}"
export DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE="${DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${NETWORK_SLUG}.epoch-rewards.json}"
export DARWIN_ACTIVITY_LOOKBACK_BLOCKS="${DARWIN_ACTIVITY_LOOKBACK_BLOCKS:-50000}"

TOKEN_ADDRESS="$("$PYTHON_BIN" "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" contracts.drw_token)"
NETWORK_NAME="$("$PYTHON_BIN" "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" network)"

DISTRIBUTOR_ADDRESS="${DARWIN_EPOCH_REWARD_DISTRIBUTOR:-}"
if [[ -z "$DISTRIBUTOR_ADDRESS" && -f "$DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE" ]]; then
  DISTRIBUTOR_ADDRESS="$("$PYTHON_BIN" - "$DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE" <<'PY'
import json
import sys
data = json.loads(open(sys.argv[1]).read())
epoch_rewards = data.get("epoch_rewards") or {}
contracts = epoch_rewards.get("contracts") or data.get("contracts") or {}
print(contracts.get("drw_epoch_distributor", ""))
PY
)"
fi

"$PYTHON_BIN" "$ROOT/ops/report_external_activity.py" \
  --deployment-file "$DARWIN_DEPLOYMENT_FILE" \
  --lookback-blocks "$DARWIN_ACTIVITY_LOOKBACK_BLOCKS" \
  --json-out "$DARWIN_EPOCH_ACTIVITY_REPORT"

args=(
  "$ROOT/ops/build_drw_epoch_distribution.py"
  --activity-report "$DARWIN_EPOCH_ACTIVITY_REPORT"
  --epoch-file "$DARWIN_EPOCH_FILE"
  --out "$DARWIN_EPOCH_REWARDS_FILE"
  --token "$TOKEN_ADDRESS"
  --network "$NETWORK_NAME"
)

if [[ -n "$DISTRIBUTOR_ADDRESS" ]]; then
  args+=(--distributor "$DISTRIBUTOR_ADDRESS")
fi

"$PYTHON_BIN" "${args[@]}"

echo "DARWIN epoch reward manifest ready."
echo "  deployment:      $DARWIN_DEPLOYMENT_FILE"
echo "  activity_report: $DARWIN_EPOCH_ACTIVITY_REPORT"
echo "  epoch_file:      $DARWIN_EPOCH_FILE"
echo "  out:             $DARWIN_EPOCH_REWARDS_FILE"
if [[ -n "$DISTRIBUTOR_ADDRESS" ]]; then
  echo "  distributor:     $DISTRIBUTOR_ADDRESS"
fi
