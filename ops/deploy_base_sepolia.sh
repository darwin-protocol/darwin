#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

if [[ -z "${BASE_SEPOLIA_RPC_URL:-}" && -n "${ALCHEMY_API_KEY:-}" ]]; then
  export BASE_SEPOLIA_RPC_URL="https://base-sepolia.g.alchemy.com/v2/$ALCHEMY_API_KEY"
fi

export DARWIN_NETWORK="base-sepolia"
export DARWIN_RPC_URL="${BASE_SEPOLIA_RPC_URL:-${DARWIN_RPC_URL:-}}"
export DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-84532}"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"

if [[ "${DARWIN_SKIP_PREFLIGHT:-0}" != "1" ]]; then
  "$ROOT/ops/preflight_base_sepolia.sh"
fi

exec "$ROOT/ops/deploy_contracts.sh"
