#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required env var: $name" >&2
    exit 1
  fi
}

require_env DARWIN_RPC_URL
require_env DARWIN_NETWORK
require_env DARWIN_DEPLOYER_PRIVATE_KEY
require_env DARWIN_GOVERNANCE
require_env DARWIN_EPOCH_OPERATOR
require_env DARWIN_SAFE_MODE_AUTHORITY

if [[ "${DARWIN_DEPLOY_BOND_ASSET_MOCK:-0}" != "1" ]]; then
  require_env DARWIN_BOND_ASSET
fi

export DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-0}"
export DARWIN_CHALLENGE_WINDOW_SEC="${DARWIN_CHALLENGE_WINDOW_SEC:-1800}"
export DARWIN_RESPONSE_WINDOW_SEC="${DARWIN_RESPONSE_WINDOW_SEC:-86400}"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.json}"

mkdir -p "$(dirname "$DARWIN_DEPLOYMENT_FILE")"

detected_chain_id="$(cast chain-id --rpc-url "$DARWIN_RPC_URL")"
if [[ "$DARWIN_EXPECT_CHAIN_ID" != "0" && "$detected_chain_id" != "$DARWIN_EXPECT_CHAIN_ID" ]]; then
  echo "Chain ID mismatch: expected $DARWIN_EXPECT_CHAIN_ID, got $detected_chain_id" >&2
  exit 1
fi

cd "$ROOT/contracts"
forge script script/DeployDarwin.s.sol:DeployDarwin \
  --rpc-url "$DARWIN_RPC_URL" \
  --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY" \
  --broadcast \
  --slow \
  --non-interactive
