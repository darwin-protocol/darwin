#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DARWIN_NETWORK_PRESET="${DARWIN_NETWORK+x}"
DARWIN_EPOCH_REWARDS_FILE_PRESET="${DARWIN_EPOCH_REWARDS_FILE+x}"
DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE_PRESET="${DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE+x}"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

NETWORK_SLUG="${DARWIN_NETWORK:-base-sepolia-recovery}"
if [[ -n "$DARWIN_NETWORK_PRESET" && -z "$DARWIN_EPOCH_REWARDS_FILE_PRESET" ]]; then
  export DARWIN_EPOCH_REWARDS_FILE="$ROOT/ops/state/${NETWORK_SLUG}-epoch-rewards.json"
fi
if [[ -n "$DARWIN_NETWORK_PRESET" && -z "$DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE_PRESET" ]]; then
  export DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE="$ROOT/ops/deployments/${NETWORK_SLUG}.epoch-rewards.json"
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

resolve_python() {
  if [[ -n "${DARWIN_EPOCH_PYTHON_BIN:-}" ]]; then
    echo "$DARWIN_EPOCH_PYTHON_BIN"
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
  else
    echo "python3"
  fi
}

PYTHON_BIN="$(resolve_python)"
if [[ "$PYTHON_BIN" != */* ]]; then
  require_cmd "$PYTHON_BIN"
elif [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not executable: $PYTHON_BIN" >&2
  exit 1
fi

require_cmd forge

export DARWIN_EPOCH_REWARDS_FILE="${DARWIN_EPOCH_REWARDS_FILE:-$ROOT/ops/state/${NETWORK_SLUG}-epoch-rewards.json}"
export DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE="${DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${NETWORK_SLUG}.epoch-rewards.json}"

[[ -f "$DARWIN_EPOCH_REWARDS_FILE" ]] || {
  echo "Missing epoch rewards manifest: $DARWIN_EPOCH_REWARDS_FILE" >&2
  exit 1
}

if [[ -z "${DARWIN_EPOCH_REWARD_DISTRIBUTOR:-}" ]]; then
  if [[ ! -f "$DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE" ]]; then
    echo "Missing epoch reward deployment file: $DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE" >&2
    echo "Or set DARWIN_EPOCH_REWARD_DISTRIBUTOR directly." >&2
    exit 1
  fi
  export DARWIN_EPOCH_REWARD_DISTRIBUTOR="$("$PYTHON_BIN" - "$DARWIN_EPOCH_REWARD_DEPLOYMENT_FILE" <<'PY'
import json
import sys
data = json.loads(open(sys.argv[1]).read())
epoch_rewards = data.get("epoch_rewards") or {}
contracts = epoch_rewards.get("contracts") or data.get("contracts") or {}
value = contracts.get("drw_epoch_distributor", "")
if not value:
    raise SystemExit("missing drw_epoch_distributor in epoch reward deployment file")
print(value)
PY
)"
fi

if [[ -z "${DARWIN_EPOCH_REWARD_GOVERNANCE_PRIVATE_KEY:-}" ]]; then
  echo "Set DARWIN_EPOCH_REWARD_GOVERNANCE_PRIVATE_KEY to configure the epoch distributor." >&2
  exit 1
fi

cd "$ROOT/contracts"
forge script script/ConfigureDRWEpochDistributor.s.sol:ConfigureDRWEpochDistributor \
  --rpc-url "${DARWIN_RPC_URL:?Set DARWIN_RPC_URL}" \
  --private-key "$DARWIN_EPOCH_REWARD_GOVERNANCE_PRIVATE_KEY" \
  --broadcast \
  --slow \
  --non-interactive
