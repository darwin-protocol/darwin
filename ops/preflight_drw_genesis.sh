#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

if [[ -z "${DARWIN_RPC_URL:-}" ]]; then
  case "${DARWIN_NETWORK:-base-sepolia}" in
    arbitrum-sepolia)
      DARWIN_RPC_URL="${ARBITRUM_SEPOLIA_RPC_URL:-https://sepolia-rollup.arbitrum.io/rpc}"
      ;;
    *)
      if [[ -z "${BASE_SEPOLIA_RPC_URL:-}" && -n "${ALCHEMY_API_KEY:-}" ]]; then
        BASE_SEPOLIA_RPC_URL="https://base-sepolia.g.alchemy.com/v2/$ALCHEMY_API_KEY"
      fi
      DARWIN_RPC_URL="${BASE_SEPOLIA_RPC_URL:-https://sepolia.base.org}"
      ;;
  esac
fi

DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia}"
DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.json}"
DARWIN_DRW_MIN_NATIVE_ETH_WEI="${DARWIN_DRW_MIN_NATIVE_ETH_WEI:-1000000000000000}" # 0.001 ETH

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

read_artifact_field() {
  python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" "$1"
}

require_cmd cast
require_cmd python3

if [[ ! -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  echo "Missing deployment artifact: $DARWIN_DEPLOYMENT_FILE" >&2
  exit 1
fi

ARTIFACT_CHAIN_ID="$(read_artifact_field chain_id)"
ARTIFACT_NETWORK="$(read_artifact_field network)"
ARTIFACT_GOVERNANCE="$(read_artifact_field roles.governance)"
export DARWIN_GOVERNANCE="${DARWIN_GOVERNANCE:-$ARTIFACT_GOVERNANCE}"

if [[ -n "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" ]]; then
  DEPLOYER_ADDRESS="$(cast wallet address --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY")"
elif [[ -n "${DARWIN_DEPLOYER_ADDRESS:-}" ]]; then
  DEPLOYER_ADDRESS="$DARWIN_DEPLOYER_ADDRESS"
else
  DEPLOYER_ADDRESS=""
fi

RPC_CHAIN_ID=""
if RPC_CHAIN_ID="$(cast chain-id --rpc-url "$DARWIN_RPC_URL" 2>/dev/null)"; then
  :
else
  RPC_CHAIN_ID=""
fi

BASE_BALANCE_WEI="0"
if [[ -n "$DEPLOYER_ADDRESS" && -n "$RPC_CHAIN_ID" ]]; then
  BASE_BALANCE_WEI="$(cast balance "$DEPLOYER_ADDRESS" --rpc-url "$DARWIN_RPC_URL")"
fi

EXISTING_DRW="no"
if python3 - "$DARWIN_DEPLOYMENT_FILE" <<'PY' >/dev/null 2>&1
import json, sys
data = json.loads(open(sys.argv[1]).read())
drw = data.get("drw")
raise SystemExit(0 if drw else 1)
PY
then
  EXISTING_DRW="yes"
fi

READY=1
declare -a BLOCKERS=()

if [[ -z "$RPC_CHAIN_ID" || "$RPC_CHAIN_ID" != "$ARTIFACT_CHAIN_ID" ]]; then
  READY=0
  BLOCKERS+=("chain_mismatch_or_rpc_unreachable")
fi
if [[ -z "$DEPLOYER_ADDRESS" ]]; then
  READY=0
  BLOCKERS+=("missing_deployer")
fi
if [[ -n "$DEPLOYER_ADDRESS" && "$BASE_BALANCE_WEI" -lt "$DARWIN_DRW_MIN_NATIVE_ETH_WEI" ]]; then
  READY=0
  BLOCKERS+=("insufficient_native_eth")
fi
if [[ "$EXISTING_DRW" == "yes" && "${DARWIN_ALLOW_DRW_REDEPLOY:-0}" != "1" ]]; then
  READY=0
  BLOCKERS+=("drw_already_present")
fi

echo "DARWIN DRW genesis preflight"
echo "  rpc_url:              $DARWIN_RPC_URL"
echo "  rpc_chain_id:         ${RPC_CHAIN_ID:-unreachable}"
echo "  artifact_network:     $ARTIFACT_NETWORK"
echo "  artifact_chain_id:    $ARTIFACT_CHAIN_ID"
echo "  artifact_file:        $DARWIN_DEPLOYMENT_FILE"
echo "  governance:           $DARWIN_GOVERNANCE"
echo "  deployer_address:     ${DEPLOYER_ADDRESS:-missing}"
echo "  native_balance_eth:   $(to_eth "$BASE_BALANCE_WEI")"
echo "  min_native_eth:       $(to_eth "$DARWIN_DRW_MIN_NATIVE_ETH_WEI")"
echo "  existing_drw:         $EXISTING_DRW"
echo "  total_supply:         ${DARWIN_DRW_TOTAL_SUPPLY:-1000000000000000000000000000}"

if [[ $READY -eq 1 ]]; then
  echo "  ready_to_deploy:      yes"
else
  echo "  ready_to_deploy:      no"
  echo "  blocked_by:           ${BLOCKERS[*]:-unknown}"
  exit 1
fi
