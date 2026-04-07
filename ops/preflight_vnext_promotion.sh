#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

require_cmd cast
require_cmd python3

read_vnext_field() {
  python3 - "$DARWIN_VNEXT_FILE" "$1" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1]).read())
cursor = data
for part in sys.argv[2].split("."):
    cursor = cursor[part]
print(cursor)
PY
}

norm() {
  tr '[:upper:]' '[:lower:]'
}

rpc_address() {
  cast call --rpc-url "$DARWIN_RPC_URL" "$1" "governance()(address)" | norm
}

rpc_balance() {
  cast call --rpc-url "$DARWIN_RPC_URL" "$1" "balanceOf(address)(uint256)" "$2" | awk '{print $1}'
}

uint_lt() {
  python3 - "$1" "$2" <<'PY'
import sys
print(1 if int(sys.argv[1]) < int(sys.argv[2]) else 0)
PY
}

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"
export DARWIN_VNEXT_FILE="${DARWIN_VNEXT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.vnext.json}"
export DARWIN_VNEXT_PROMOTION_FILE="${DARWIN_VNEXT_PROMOTION_FILE:-$ROOT/ops/state/${DARWIN_NETWORK:-base-sepolia}-vnext-safe-batch.json}"

if [[ -z "${DARWIN_VNEXT_CURRENT_GOVERNANCE:-}" && -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  DARWIN_VNEXT_CURRENT_GOVERNANCE="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" --default "" roles.governance 2>/dev/null || true)"
  export DARWIN_VNEXT_CURRENT_GOVERNANCE
fi

DARWIN_VNEXT_DISTRIBUTION_TOKEN=""
DARWIN_VNEXT_TIMELOCK=""
DARWIN_VNEXT_DISTRIBUTOR=""
DARWIN_VNEXT_TOTAL_AMOUNT="0"
DARWIN_VNEXT_STAKING=""
DARWIN_VNEXT_FAUCET=""
DARWIN_VNEXT_REFERENCE_POOL=""

if [[ -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  DARWIN_VNEXT_DISTRIBUTION_TOKEN="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" contracts.drw_token)"
  DARWIN_VNEXT_STAKING="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" --default "" contracts.drw_staking)"
  DARWIN_VNEXT_FAUCET="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" --default "" contracts.drw_faucet)"
  DARWIN_VNEXT_REFERENCE_POOL="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" --default "" contracts.reference_pool)"
fi

if [[ -f "$DARWIN_VNEXT_FILE" ]]; then
  DARWIN_VNEXT_TIMELOCK="$(read_vnext_field vnext.contracts.darwin_timelock)"
  DARWIN_VNEXT_DISTRIBUTOR="$(read_vnext_field vnext.contracts.drw_merkle_distributor)"
  DARWIN_VNEXT_TOTAL_AMOUNT="$(read_vnext_field vnext.distribution.total_amount)"
fi

export DARWIN_VNEXT_DISTRIBUTION_TOKEN DARWIN_VNEXT_TIMELOCK DARWIN_VNEXT_DISTRIBUTOR DARWIN_VNEXT_TOTAL_AMOUNT

blockers=()
[[ -f "$DARWIN_DEPLOYMENT_FILE" ]] || blockers+=("missing_deployment_file")
[[ -f "$DARWIN_VNEXT_FILE" ]] || blockers+=("missing_vnext_file")
[[ -n "${DARWIN_RPC_URL:-}" ]] || blockers+=("missing_rpc_url")
[[ -n "${DARWIN_VNEXT_CURRENT_GOVERNANCE:-}" ]] || blockers+=("missing_current_governance")
[[ -n "${DARWIN_VNEXT_DISTRIBUTION_TOKEN:-}" ]] || blockers+=("missing_distribution_token")
[[ -n "${DARWIN_VNEXT_TIMELOCK:-}" ]] || blockers+=("missing_vnext_timelock")
[[ -n "${DARWIN_VNEXT_DISTRIBUTOR:-}" ]] || blockers+=("missing_vnext_distributor")

if [[ -n "${DARWIN_RPC_URL:-}" && -n "${DARWIN_VNEXT_CURRENT_GOVERNANCE:-}" ]]; then
  expected_governance="$(printf '%s' "$DARWIN_VNEXT_CURRENT_GOVERNANCE" | norm)"
  token_governance="$(rpc_address "$DARWIN_VNEXT_DISTRIBUTION_TOKEN" || true)"
  [[ "$token_governance" == "$expected_governance" ]] || blockers+=("token_governance_mismatch")

  if [[ -n "${DARWIN_VNEXT_STAKING:-}" ]]; then
    staking_governance="$(rpc_address "$DARWIN_VNEXT_STAKING" || true)"
    [[ "$staking_governance" == "$expected_governance" ]] || blockers+=("staking_governance_mismatch")
  fi

  if [[ -n "${DARWIN_VNEXT_FAUCET:-}" ]]; then
    faucet_governance="$(rpc_address "$DARWIN_VNEXT_FAUCET" || true)"
    [[ "$faucet_governance" == "$expected_governance" ]] || blockers+=("faucet_governance_mismatch")
  fi

  if [[ -n "${DARWIN_VNEXT_REFERENCE_POOL:-}" ]]; then
    pool_governance="$(rpc_address "$DARWIN_VNEXT_REFERENCE_POOL" || true)"
    [[ "$pool_governance" == "$expected_governance" ]] || blockers+=("reference_pool_governance_mismatch")
  fi

  if [[ "${DARWIN_VNEXT_TOTAL_AMOUNT:-0}" != "0" ]]; then
    current_balance="$(rpc_balance "$DARWIN_VNEXT_DISTRIBUTION_TOKEN" "$DARWIN_VNEXT_CURRENT_GOVERNANCE" || true)"
    if [[ -z "$current_balance" || "$current_balance" == "0" ]]; then
      blockers+=("missing_distribution_balance")
    elif [[ "$(uint_lt "$current_balance" "$DARWIN_VNEXT_TOTAL_AMOUNT")" == "1" ]]; then
      blockers+=("insufficient_distribution_balance")
    fi
  fi
fi

echo "DARWIN vNext promotion preflight"
echo "  deployment_file:    $DARWIN_DEPLOYMENT_FILE"
echo "  vnext_file:         $DARWIN_VNEXT_FILE"
echo "  promotion_file:     $DARWIN_VNEXT_PROMOTION_FILE"
echo "  current_governance: ${DARWIN_VNEXT_CURRENT_GOVERNANCE:-missing}"
echo "  timelock:           ${DARWIN_VNEXT_TIMELOCK:-missing}"
echo "  distributor:        ${DARWIN_VNEXT_DISTRIBUTOR:-missing}"
echo "  token:              ${DARWIN_VNEXT_DISTRIBUTION_TOKEN:-missing}"
echo "  total_amount:       ${DARWIN_VNEXT_TOTAL_AMOUNT:-0}"
echo "  staking:            ${DARWIN_VNEXT_STAKING:-}"
echo "  faucet:             ${DARWIN_VNEXT_FAUCET:-}"
echo "  reference_pool:     ${DARWIN_VNEXT_REFERENCE_POOL:-}"
echo "  market_operator:    ${DARWIN_VNEXT_MARKET_OPERATOR:-unchanged}"

if ((${#blockers[@]} > 0)); then
  echo "  ready_to_build:     no"
  for blocker in "${blockers[@]}"; do
    echo "  blocked_by:         $blocker"
  done
  exit 1
fi

echo "  ready_to_build:     yes"
