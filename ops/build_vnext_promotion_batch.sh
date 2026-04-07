#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

"$ROOT/ops/preflight_vnext_promotion.sh"

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"
export DARWIN_VNEXT_FILE="${DARWIN_VNEXT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.vnext.json}"
export DARWIN_VNEXT_PROMOTION_FILE="${DARWIN_VNEXT_PROMOTION_FILE:-$ROOT/ops/state/${DARWIN_NETWORK:-base-sepolia}-vnext-safe-batch.json}"

args=(
  "$ROOT/ops/build_vnext_safe_batch.py"
  --deployment-file "$DARWIN_DEPLOYMENT_FILE"
  --vnext-file "$DARWIN_VNEXT_FILE"
  --out "$DARWIN_VNEXT_PROMOTION_FILE"
)

if [[ -n "${DARWIN_VNEXT_SAFE_ADDRESS:-}" ]]; then
  args+=(--safe-address "$DARWIN_VNEXT_SAFE_ADDRESS")
fi

if [[ -n "${DARWIN_VNEXT_MARKET_OPERATOR:-}" ]]; then
  args+=(--market-operator "$DARWIN_VNEXT_MARKET_OPERATOR")
fi

python3 "${args[@]}"

echo "DARWIN vNext promotion batch ready."
echo "  batch_json: $DARWIN_VNEXT_PROMOTION_FILE"
