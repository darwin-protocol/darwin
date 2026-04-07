#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"
export DARWIN_VNEXT_FILE="${DARWIN_VNEXT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.vnext.json}"
export DARWIN_VNEXT_PROMOTION_FILE="${DARWIN_VNEXT_PROMOTION_FILE:-$ROOT/ops/state/${DARWIN_NETWORK:-base-sepolia}-vnext-safe-batch.json}"

if [[ -n "${DARWIN_VNEXT_PROMOTION_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$DARWIN_VNEXT_PROMOTION_PYTHON_BIN"
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

require_cmd cast
require_cmd "$PYTHON_BIN"

read_field() {
  "$PYTHON_BIN" - "$1" "$2" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1]).read())
cursor = data
for part in sys.argv[2].split("."):
    cursor = cursor[part]
print(cursor)
PY
}

read_deployment_field() {
  "$PYTHON_BIN" "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" "$1"
}

normalize_address() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]'
}

"$ROOT/ops/preflight_vnext_promotion.sh"
"$ROOT/ops/build_vnext_promotion_batch.sh"

PROMOTION_PRIVATE_KEY="${DARWIN_VNEXT_PROMOTION_PRIVATE_KEY:-${DARWIN_GOVERNANCE_PRIVATE_KEY:-}}"
if [[ -z "$PROMOTION_PRIVATE_KEY" ]]; then
  echo "Missing promotion signer. Set DARWIN_VNEXT_PROMOTION_PRIVATE_KEY or DARWIN_GOVERNANCE_PRIVATE_KEY." >&2
  exit 1
fi

CURRENT_GOVERNANCE="$(read_deployment_field roles.governance)"
EXPECTED_SIGNER="$(normalize_address "$CURRENT_GOVERNANCE")"
SIGNER_ADDRESS="$(normalize_address "$(cast wallet address --private-key "$PROMOTION_PRIVATE_KEY")")"
if [[ "$EXPECTED_SIGNER" != "$SIGNER_ADDRESS" ]]; then
  echo "Promotion signer does not match current governance." >&2
  echo "  expected: $CURRENT_GOVERNANCE" >&2
  echo "  signer:   $SIGNER_ADDRESS" >&2
  exit 1
fi

TOKEN_ADDRESS="$(read_deployment_field contracts.drw_token)"
STAKING_ADDRESS="$(read_deployment_field contracts.drw_staking)"
FAUCET_ADDRESS="$(read_deployment_field contracts.drw_faucet)"
REFERENCE_POOL_ADDRESS="$(read_deployment_field contracts.reference_pool)"
TIMELOCK_ADDRESS="$(read_field "$DARWIN_VNEXT_FILE" vnext.contracts.darwin_timelock)"
DISTRIBUTOR_ADDRESS="$(read_field "$DARWIN_VNEXT_FILE" vnext.contracts.drw_merkle_distributor)"
TOTAL_AMOUNT="$(read_field "$DARWIN_VNEXT_FILE" vnext.distribution.total_amount)"
MARKET_OPERATOR="${DARWIN_VNEXT_MARKET_OPERATOR:-}"

send_tx() {
  local target="$1"
  local signature="$2"
  shift 2
  LAST_TX_HASH="$(cast send "$target" "$signature" "$@" \
    --rpc-url "$DARWIN_RPC_URL" \
    --private-key "$PROMOTION_PRIVATE_KEY" \
    --nonce "$NEXT_NONCE" | awk '/transactionHash/ {print $2}')"
  if [[ -z "$LAST_TX_HASH" ]]; then
    echo "Failed to capture transaction hash for $signature" >&2
    exit 1
  fi
  NEXT_NONCE=$((NEXT_NONCE + 1))
}

NEXT_NONCE="$(cast nonce --rpc-url "$DARWIN_RPC_URL" "$CURRENT_GOVERNANCE")"

echo "DARWIN vNext promotion execution"
echo "  signer:       $CURRENT_GOVERNANCE"
echo "  timelock:     $TIMELOCK_ADDRESS"
echo "  distributor:  $DISTRIBUTOR_ADDRESS"
echo "  total_amount: $TOTAL_AMOUNT"
echo "  start_nonce:  $NEXT_NONCE"

if [[ "$TOTAL_AMOUNT" != "0" ]]; then
  send_tx "$TOKEN_ADDRESS" "transfer(address,uint256)" "$DISTRIBUTOR_ADDRESS" "$TOTAL_AMOUNT"
  echo "  distributor_funding_tx: $LAST_TX_HASH"
fi

if [[ -n "$MARKET_OPERATOR" ]]; then
  send_tx "$REFERENCE_POOL_ADDRESS" "setMarketOperator(address)" "$MARKET_OPERATOR"
  echo "  market_operator_tx:     $LAST_TX_HASH"
fi

send_tx "$TOKEN_ADDRESS" "setGovernance(address)" "$TIMELOCK_ADDRESS"
echo "  token_governance_tx:    $LAST_TX_HASH"
send_tx "$STAKING_ADDRESS" "setGovernance(address)" "$TIMELOCK_ADDRESS"
echo "  staking_governance_tx:  $LAST_TX_HASH"
send_tx "$FAUCET_ADDRESS" "setGovernance(address)" "$TIMELOCK_ADDRESS"
echo "  faucet_governance_tx:   $LAST_TX_HASH"
send_tx "$REFERENCE_POOL_ADDRESS" "setGovernance(address)" "$TIMELOCK_ADDRESS"
echo "  pool_governance_tx:     $LAST_TX_HASH"

echo "DARWIN vNext promotion execution complete."
echo "  batch_json: $DARWIN_VNEXT_PROMOTION_FILE"
