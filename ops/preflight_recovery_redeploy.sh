#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"

CONFIG_DIR="$(darwin_config_dir)"
RECOVERY_ENV_FILE="${DARWIN_RECOVERY_ENV_FILE:-$(resolve_darwin_env_file "$CONFIG_DIR/recovery.env" "$ROOT/.env.recovery")}"
load_env_defaults "$RECOVERY_ENV_FILE"

if [[ -z "${BASE_SEPOLIA_RPC_URL:-}" && -n "${ALCHEMY_API_KEY:-}" ]]; then
  BASE_SEPOLIA_RPC_URL="https://base-sepolia.g.alchemy.com/v2/$ALCHEMY_API_KEY"
fi

DARWIN_RPC_URL="${DARWIN_RPC_URL:-${BASE_SEPOLIA_RPC_URL:-https://sepolia.base.org}}"
DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia-recovery}"
DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-84532}"
DARWIN_SOURCE_DEPLOYMENT_FILE="${DARWIN_SOURCE_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia-recovery.json}"

DARWIN_RECOVERY_MIN_DEPLOYER_ETH_WEI="${DARWIN_RECOVERY_MIN_DEPLOYER_ETH_WEI:-1500000000000000}" # 0.0015 ETH
DARWIN_RECOVERY_MIN_GOVERNANCE_ETH_WEI="${DARWIN_RECOVERY_MIN_GOVERNANCE_ETH_WEI:-1200000000000000}" # 0.0012 ETH
DARWIN_RECOVERY_ENABLE_DRW="${DARWIN_RECOVERY_ENABLE_DRW:-1}"
DARWIN_RECOVERY_ENABLE_MARKET="${DARWIN_RECOVERY_ENABLE_MARKET:-1}"
DARWIN_RECOVERY_ENABLE_MARKET_SEED="${DARWIN_RECOVERY_ENABLE_MARKET_SEED:-1}"
DARWIN_RECOVERY_ENABLE_FAUCET="${DARWIN_RECOVERY_ENABLE_FAUCET:-1}"

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
print(f"{(wei / Decimal(10**18)):.8f}")
PY
}

read_artifact_field() {
  python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_SOURCE_DEPLOYMENT_FILE" "$1"
}

require_cmd cast
require_cmd python3

PYTHON_BIN="$ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi

for path in "$DARWIN_SOURCE_DEPLOYMENT_FILE" "$RECOVERY_ENV_FILE"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
done

RPC_CHAIN_ID="$(cast chain-id --rpc-url "$DARWIN_RPC_URL" 2>/dev/null || true)"
CURRENT_GOVERNANCE="$(read_artifact_field roles.governance)"
CURRENT_DEPLOYER="$(read_artifact_field deployer)"

DEPLOYER_ADDRESS=""
GOVERNANCE_ADDRESS=""
if [[ -n "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" ]]; then
  DEPLOYER_ADDRESS="$(cast wallet address --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY")"
fi
if [[ -n "${DARWIN_GOVERNANCE_PRIVATE_KEY:-}" ]]; then
  GOVERNANCE_ADDRESS="$(cast wallet address --private-key "$DARWIN_GOVERNANCE_PRIVATE_KEY")"
fi

DEPLOYER_BALANCE_WEI="0"
GOVERNANCE_BALANCE_WEI="0"
if [[ -n "$DEPLOYER_ADDRESS" && -n "$RPC_CHAIN_ID" ]]; then
  DEPLOYER_BALANCE_WEI="$(cast balance "$DEPLOYER_ADDRESS" --rpc-url "$DARWIN_RPC_URL")"
fi
if [[ -n "$GOVERNANCE_ADDRESS" && -n "$RPC_CHAIN_ID" ]]; then
  GOVERNANCE_BALANCE_WEI="$(cast balance "$GOVERNANCE_ADDRESS" --rpc-url "$DARWIN_RPC_URL")"
fi

READY=1
declare -a BLOCKERS=()

if [[ -z "$RPC_CHAIN_ID" || "$RPC_CHAIN_ID" != "$DARWIN_EXPECT_CHAIN_ID" ]]; then
  READY=0
  BLOCKERS+=("chain_mismatch_or_rpc_unreachable")
fi
if [[ -z "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" || -z "$DEPLOYER_ADDRESS" ]]; then
  READY=0
  BLOCKERS+=("missing_future_deployer_key")
fi
if [[ -z "${DARWIN_GOVERNANCE_PRIVATE_KEY:-}" || -z "$GOVERNANCE_ADDRESS" ]]; then
  READY=0
  BLOCKERS+=("missing_future_governance_key")
fi
if [[ -n "$DEPLOYER_ADDRESS" && "$DEPLOYER_ADDRESS" == "$CURRENT_DEPLOYER" ]]; then
  READY=0
  BLOCKERS+=("future_deployer_matches_current_deployer")
fi
if [[ -n "$GOVERNANCE_ADDRESS" && "$GOVERNANCE_ADDRESS" == "$CURRENT_GOVERNANCE" ]]; then
  READY=0
  BLOCKERS+=("future_governance_matches_current_governance")
fi
if [[ -n "$DEPLOYER_ADDRESS" && -n "$GOVERNANCE_ADDRESS" && "$DEPLOYER_ADDRESS" == "$GOVERNANCE_ADDRESS" ]]; then
  READY=0
  BLOCKERS+=("future_deployer_matches_future_governance")
fi
if [[ "$DARWIN_DEPLOYMENT_FILE" == "$DARWIN_SOURCE_DEPLOYMENT_FILE" && "${DARWIN_ALLOW_OVERWRITE_LIVE_ARTIFACT:-0}" != "1" ]]; then
  READY=0
  BLOCKERS+=("recovery_artifact_overwrites_live_artifact")
fi
if [[ -f "$DARWIN_DEPLOYMENT_FILE" && "${DARWIN_ALLOW_RECOVERY_ARTIFACT_OVERWRITE:-0}" != "1" ]]; then
  READY=0
  BLOCKERS+=("recovery_artifact_already_exists")
fi
if [[ -n "$DEPLOYER_ADDRESS" && "$DEPLOYER_BALANCE_WEI" -lt "$DARWIN_RECOVERY_MIN_DEPLOYER_ETH_WEI" ]]; then
  READY=0
  BLOCKERS+=("insufficient_future_deployer_eth")
fi
if [[ -n "$GOVERNANCE_ADDRESS" && "$GOVERNANCE_BALANCE_WEI" -lt "$DARWIN_RECOVERY_MIN_GOVERNANCE_ETH_WEI" ]]; then
  READY=0
  BLOCKERS+=("insufficient_future_governance_eth")
fi

echo "DARWIN recovery redeploy preflight"
echo "  env_file:               $RECOVERY_ENV_FILE"
echo "  rpc_url:                $DARWIN_RPC_URL"
echo "  rpc_chain_id:           ${RPC_CHAIN_ID:-unreachable}"
echo "  source_artifact:        $DARWIN_SOURCE_DEPLOYMENT_FILE"
echo "  recovery_artifact:      $DARWIN_DEPLOYMENT_FILE"
echo "  current_deployer:       $CURRENT_DEPLOYER"
echo "  current_governance:     $CURRENT_GOVERNANCE"
echo "  future_deployer:        ${DEPLOYER_ADDRESS:-missing}"
echo "  future_governance:      ${GOVERNANCE_ADDRESS:-missing}"
echo "  future_deployer_eth:    $(to_eth "$DEPLOYER_BALANCE_WEI")"
echo "  future_governance_eth:  $(to_eth "$GOVERNANCE_BALANCE_WEI")"
echo "  enable_drw:             $DARWIN_RECOVERY_ENABLE_DRW"
echo "  enable_market:          $DARWIN_RECOVERY_ENABLE_MARKET"
echo "  enable_market_seed:     $DARWIN_RECOVERY_ENABLE_MARKET_SEED"
echo "  enable_faucet:          $DARWIN_RECOVERY_ENABLE_FAUCET"

if [[ "${DARWIN_SKIP_ROLE_AUDIT:-0}" != "1" ]]; then
  echo "  role_audit:"
  PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m darwin_sim.cli.darwinctl role-audit --deployment-file "$DARWIN_SOURCE_DEPLOYMENT_FILE" | sed 's/^/    /'
fi

if [[ $READY -eq 1 ]]; then
  echo "  ready_to_redeploy:      yes"
else
  echo "  ready_to_redeploy:      no"
  echo "  blocked_by:             ${BLOCKERS[*]:-unknown}"
  exit 1
fi
