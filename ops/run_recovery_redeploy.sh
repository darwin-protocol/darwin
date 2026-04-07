#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"

CONFIG_DIR="$(darwin_config_dir)"
RECOVERY_ENV_FILE="${DARWIN_RECOVERY_ENV_FILE:-$(resolve_darwin_env_file "$CONFIG_DIR/recovery.env" "$ROOT/.env.recovery")}"
load_env_defaults "$RECOVERY_ENV_FILE"

DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia}"
DARWIN_RPC_URL="${DARWIN_RPC_URL:-https://sepolia.base.org}"
DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-84532}"
DARWIN_SOURCE_DEPLOYMENT_FILE="${DARWIN_SOURCE_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia-recovery.json}"

DARWIN_RECOVERY_ENABLE_DRW="${DARWIN_RECOVERY_ENABLE_DRW:-1}"
DARWIN_RECOVERY_ENABLE_MARKET="${DARWIN_RECOVERY_ENABLE_MARKET:-1}"
DARWIN_RECOVERY_ENABLE_MARKET_SEED="${DARWIN_RECOVERY_ENABLE_MARKET_SEED:-1}"
DARWIN_RECOVERY_ENABLE_FAUCET="${DARWIN_RECOVERY_ENABLE_FAUCET:-1}"

"$ROOT/ops/preflight_recovery_redeploy.sh"

echo "[recovery-redeploy] Deploying core DARWIN contracts"
"$ROOT/ops/deploy_contracts.sh"

if [[ "$DARWIN_RECOVERY_ENABLE_DRW" == "1" ]]; then
  echo "[recovery-redeploy] Deploying DRW genesis"
  DARWIN_SKIP_PREFLIGHT=1 "$ROOT/ops/init_drw_genesis.sh"
fi

if [[ "$DARWIN_RECOVERY_ENABLE_MARKET" == "1" ]]; then
  echo "[recovery-redeploy] Deploying reference market"
  "$ROOT/ops/init_reference_market.sh"

  if [[ "$DARWIN_RECOVERY_ENABLE_MARKET_SEED" == "1" ]]; then
    echo "[recovery-redeploy] Wrapping WETH for market seed"
    "$ROOT/ops/wrap_base_sepolia_weth.sh" --amount-wei "${DARWIN_WRAP_WETH_WEI:-${DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT:-500000000000000}}"

    echo "[recovery-redeploy] Seeding reference market"
    "$ROOT/ops/seed_reference_market.sh"
  fi
fi

if [[ "$DARWIN_RECOVERY_ENABLE_FAUCET" == "1" ]]; then
  echo "[recovery-redeploy] Deploying and funding DRW faucet"
  "$ROOT/ops/init_drw_faucet.sh"
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  echo "[recovery-redeploy] Final artifact"
  exec "$ROOT/.venv/bin/python" -m darwin_sim.cli.darwinctl deployment-show --deployment-file "$DARWIN_DEPLOYMENT_FILE"
fi

exec python3 -m darwin_sim.cli.darwinctl deployment-show --deployment-file "$DARWIN_DEPLOYMENT_FILE"
