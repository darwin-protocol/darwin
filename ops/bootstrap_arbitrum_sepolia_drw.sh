#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_arbitrum_sepolia_env "$ROOT"

CONFIG_DIR="$(darwin_config_dir)"
export DARWIN_ENV_FILE="${DARWIN_ENV_FILE:-$(resolve_darwin_env_file "$CONFIG_DIR/arbitrum-sepolia.env" "$ROOT/.env.arbitrum-sepolia")}"
export DARWIN_NETWORK="${DARWIN_NETWORK:-arbitrum-sepolia}"
export DARWIN_RPC_URL="${DARWIN_RPC_URL:-${ARBITRUM_SEPOLIA_RPC_URL:-https://sepolia-rollup.arbitrum.io/rpc}}"
export DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-421614}"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/arbitrum-sepolia.json}"
export DARWIN_REFERENCE_MARKET_BASE_AMOUNT="${DARWIN_REFERENCE_MARKET_BASE_AMOUNT:-1000000000000000000000}"
export DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT="${DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT:-500000000000000}"
export DARWIN_ARBITRUM_GOVERNANCE_TOPUP_WEI="${DARWIN_ARBITRUM_GOVERNANCE_TOPUP_WEI:-1000000000000000}"
export DARWIN_DRW_FAUCET_INITIAL_TOKEN_FUNDING="${DARWIN_DRW_FAUCET_INITIAL_TOKEN_FUNDING:-100000000000000000000000}"
export DARWIN_DRW_FAUCET_INITIAL_NATIVE_FUNDING="${DARWIN_DRW_FAUCET_INITIAL_NATIVE_FUNDING:-200000000000000}"
export DARWIN_VNEXT_DISTRIBUTION_CLAIMS_FILE="${DARWIN_VNEXT_DISTRIBUTION_CLAIMS_FILE:-$ROOT/ops/state/base-sepolia-recovery-claims.csv}"
export DARWIN_VNEXT_DISTRIBUTION_FILE="${DARWIN_VNEXT_DISTRIBUTION_FILE:-$ROOT/ops/state/${DARWIN_NETWORK}-drw-merkle.json}"
export DARWIN_VNEXT_FILE="${DARWIN_VNEXT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.vnext.json}"
export DARWIN_VNEXT_TIMELOCK_MIN_DELAY="${DARWIN_VNEXT_TIMELOCK_MIN_DELAY:-172800}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

require_cmd cast
require_cmd python3

if [[ ! -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  echo "Missing core deployment artifact: $DARWIN_DEPLOYMENT_FILE" >&2
  exit 1
fi

if [[ -z "${DARWIN_GOVERNANCE_PRIVATE_KEY:-}" || -z "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" ]]; then
  echo "Missing deployer/governance private keys in the Arbitrum env." >&2
  exit 1
fi

GOV_BALANCE="$(cast balance "$DARWIN_GOVERNANCE" --rpc-url "$DARWIN_RPC_URL")"
if [[ "$GOV_BALANCE" -lt "$DARWIN_ARBITRUM_GOVERNANCE_TOPUP_WEI" ]]; then
  cast send "$DARWIN_GOVERNANCE" \
    --value "$DARWIN_ARBITRUM_GOVERNANCE_TOPUP_WEI" \
    --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY" \
    --rpc-url "$DARWIN_RPC_URL" >/dev/null
fi

"$ROOT/ops/preflight_drw_genesis.sh"
"$ROOT/ops/init_drw_genesis.sh"

export DARWIN_QUOTE_TOKEN_RECIPIENT="$DARWIN_GOVERNANCE"
export DARWIN_QUOTE_TOKEN_FUNDER_PRIVATE_KEY="$DARWIN_DEPLOYER_PRIVATE_KEY"
"$ROOT/ops/fund_quote_token.sh" --amount-wei "$DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT"

"$ROOT/ops/init_reference_market.sh"
export DARWIN_REFERENCE_MARKET_SEEDER_PRIVATE_KEY="$DARWIN_GOVERNANCE_PRIVATE_KEY"
"$ROOT/ops/seed_reference_market.sh"

"$ROOT/ops/init_drw_faucet.sh"

CLAIM_DEADLINE="$(python3 - <<'PY'
import time
print(int(time.time()) + 30 * 24 * 60 * 60)
PY
)"
python3 "$ROOT/ops/build_drw_merkle_distribution.py" \
  --claims-file "$DARWIN_VNEXT_DISTRIBUTION_CLAIMS_FILE" \
  --out "$DARWIN_VNEXT_DISTRIBUTION_FILE" \
  --format csv \
  --network "$DARWIN_NETWORK" \
  --claim-deadline "$CLAIM_DEADLINE"

"$ROOT/ops/deploy_vnext_governance.sh"
"$ROOT/ops/execute_vnext_promotion.sh"

echo "DARWIN Arbitrum Sepolia DRW bootstrap complete."
echo "  deployment: $DARWIN_DEPLOYMENT_FILE"
echo "  vnext:      $DARWIN_VNEXT_FILE"
echo "  claims:     $DARWIN_VNEXT_DISTRIBUTION_FILE"
