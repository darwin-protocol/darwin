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

require_cmd cast
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

CLAIM_INDEX="${DARWIN_EPOCH_REWARD_CLAIM_INDEX:-}"
if [[ -z "$CLAIM_INDEX" ]]; then
  echo "Missing claim index. Set DARWIN_EPOCH_REWARD_CLAIM_INDEX." >&2
  exit 1
fi

CLAIM_PRIVATE_KEY="${DARWIN_EPOCH_REWARD_CLAIM_PRIVATE_KEY:-}"
if [[ -z "$CLAIM_PRIVATE_KEY" ]]; then
  echo "Missing claim signer. Set DARWIN_EPOCH_REWARD_CLAIM_PRIVATE_KEY." >&2
  exit 1
fi

CLAIM_ACCOUNT="$("$PYTHON_BIN" - "$DARWIN_EPOCH_REWARDS_FILE" "$CLAIM_INDEX" <<'PY'
import json
import sys
manifest = json.loads(open(sys.argv[1]).read())
index = int(sys.argv[2])
for claim in manifest["claims"]:
    if int(claim["index"]) == index:
        print(claim["account"])
        raise SystemExit(0)
raise SystemExit(f"missing claim index: {index}")
PY
)"

CLAIM_AMOUNT="$("$PYTHON_BIN" - "$DARWIN_EPOCH_REWARDS_FILE" "$CLAIM_INDEX" <<'PY'
import json
import sys
manifest = json.loads(open(sys.argv[1]).read())
index = int(sys.argv[2])
for claim in manifest["claims"]:
    if int(claim["index"]) == index:
        print(claim["amount"])
        raise SystemExit(0)
raise SystemExit(f"missing claim index: {index}")
PY
)"

SIGNER_ADDRESS="$(cast wallet address --private-key "$CLAIM_PRIVATE_KEY" | tr '[:upper:]' '[:lower:]')"
EXPECTED_ADDRESS="$(printf '%s' "$CLAIM_ACCOUNT" | tr '[:upper:]' '[:lower:]')"
if [[ "$SIGNER_ADDRESS" != "$EXPECTED_ADDRESS" ]]; then
  echo "Claim signer does not match claim account." >&2
  echo "  expected: $CLAIM_ACCOUNT" >&2
  echo "  signer:   $SIGNER_ADDRESS" >&2
  exit 1
fi

echo "DARWIN epoch claim"
echo "  distributor: $DARWIN_EPOCH_REWARD_DISTRIBUTOR"
echo "  account:     $CLAIM_ACCOUNT"
echo "  index:       $CLAIM_INDEX"
echo "  amount:      $CLAIM_AMOUNT"

cd "$ROOT/contracts"
forge script script/ClaimDRWEpoch.s.sol:ClaimDRWEpoch \
  --rpc-url "${DARWIN_RPC_URL:?Set DARWIN_RPC_URL}" \
  --private-key "$CLAIM_PRIVATE_KEY" \
  --broadcast \
  --slow \
  --non-interactive
