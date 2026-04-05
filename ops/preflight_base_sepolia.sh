#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${BASE_SEPOLIA_RPC_URL:-}" && -n "${ALCHEMY_API_KEY:-}" ]]; then
  BASE_SEPOLIA_RPC_URL="https://base-sepolia.g.alchemy.com/v2/$ALCHEMY_API_KEY"
fi
if [[ -z "${SEPOLIA_RPC_URL:-}" && -n "${ALCHEMY_API_KEY:-}" ]]; then
  SEPOLIA_RPC_URL="https://eth-sepolia.g.alchemy.com/v2/$ALCHEMY_API_KEY"
fi
BASE_SEPOLIA_RPC_URL="${BASE_SEPOLIA_RPC_URL:-${DARWIN_RPC_URL:-https://sepolia.base.org}}"
SEPOLIA_RPC_URL="${SEPOLIA_RPC_URL:-https://ethereum-sepolia-rpc.publicnode.com}"
DARWIN_MIN_BASE_ETH_WEI="${DARWIN_MIN_BASE_ETH_WEI:-10000000000000000}" # 0.01 ETH
DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

to_eth() {
  python3 - "$1" <<'PY'
from decimal import Decimal, getcontext
import sys
getcontext().prec = 40
wei = Decimal(sys.argv[1])
eth = wei / Decimal(10**18)
print(f"{eth:.8f}")
PY
}

require_cmd cast
require_cmd python3

if [[ -n "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" ]]; then
  DEPLOYER_ADDRESS="$(cast wallet address --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY")"
elif [[ -n "${DARWIN_DEPLOYER_ADDRESS:-}" ]]; then
  DEPLOYER_ADDRESS="$DARWIN_DEPLOYER_ADDRESS"
else
  DEPLOYER_ADDRESS=""
fi

BASE_CHAIN_ID=""
if BASE_CHAIN_ID="$(cast chain-id --rpc-url "$BASE_SEPOLIA_RPC_URL" 2>/dev/null)"; then
  :
else
  BASE_CHAIN_ID=""
fi

SEPOLIA_CHAIN_ID=""
if SEPOLIA_CHAIN_ID="$(cast chain-id --rpc-url "$SEPOLIA_RPC_URL" 2>/dev/null)"; then
  :
else
  SEPOLIA_CHAIN_ID=""
fi

BASE_BALANCE_WEI="0"
SEPOLIA_BALANCE_WEI="0"
if [[ -n "$DEPLOYER_ADDRESS" && -n "$BASE_CHAIN_ID" ]]; then
  BASE_BALANCE_WEI="$(cast balance "$DEPLOYER_ADDRESS" --rpc-url "$BASE_SEPOLIA_RPC_URL")"
fi
if [[ -n "$DEPLOYER_ADDRESS" && -n "$SEPOLIA_CHAIN_ID" ]]; then
  SEPOLIA_BALANCE_WEI="$(cast balance "$DEPLOYER_ADDRESS" --rpc-url "$SEPOLIA_RPC_URL")"
fi

declare -a REQUIRED_ENV=(DARWIN_GOVERNANCE DARWIN_EPOCH_OPERATOR DARWIN_SAFE_MODE_AUTHORITY)
if [[ "${DARWIN_DEPLOY_BOND_ASSET_MOCK:-0}" != "1" ]]; then
  REQUIRED_ENV+=(DARWIN_BOND_ASSET)
fi

declare -a MISSING_ENV=()
for name in "${REQUIRED_ENV[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    MISSING_ENV+=("$name")
  fi
done

READY=1
if [[ "$BASE_CHAIN_ID" != "84532" ]]; then
  READY=0
fi
if [[ -z "$DEPLOYER_ADDRESS" ]]; then
  READY=0
fi
if [[ ${#MISSING_ENV[@]} -gt 0 ]]; then
  READY=0
fi
if [[ "$BASE_BALANCE_WEI" -lt "$DARWIN_MIN_BASE_ETH_WEI" ]]; then
  READY=0
fi

echo "DARWIN Base Sepolia preflight"
echo "  base_rpc_url:         $BASE_SEPOLIA_RPC_URL"
echo "  base_chain_id:        ${BASE_CHAIN_ID:-unreachable}"
echo "  sepolia_rpc_url:      $SEPOLIA_RPC_URL"
echo "  sepolia_chain_id:     ${SEPOLIA_CHAIN_ID:-unreachable}"
echo "  deployer_address:     ${DEPLOYER_ADDRESS:-missing}"
echo "  base_balance_eth:     $(to_eth "$BASE_BALANCE_WEI")"
echo "  sepolia_balance_eth:  $(to_eth "$SEPOLIA_BALANCE_WEI")"
echo "  min_base_eth:         $(to_eth "$DARWIN_MIN_BASE_ETH_WEI")"
echo "  deployment_artifact:  $DARWIN_DEPLOYMENT_FILE"

if [[ -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  echo "  existing_artifact:    present"
else
  echo "  existing_artifact:    missing"
fi

if [[ ${#MISSING_ENV[@]} -gt 0 ]]; then
  echo "  missing_env:          ${MISSING_ENV[*]}"
else
  echo "  missing_env:          none"
fi

if [[ "$BASE_BALANCE_WEI" -lt "$DARWIN_MIN_BASE_ETH_WEI" ]]; then
  echo "  balance_status:       insufficient Base Sepolia ETH"
else
  echo "  balance_status:       sufficient"
fi

if [[ $READY -eq 1 ]]; then
  echo "  ready_to_deploy:      yes"
else
  echo "  ready_to_deploy:      no"
  exit 1
fi
