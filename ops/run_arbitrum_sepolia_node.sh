#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_arbitrum_sepolia_env "$ROOT"

export DARWIN_NETWORK="${DARWIN_NETWORK:-arbitrum-sepolia}"
export DARWIN_RPC_URL="${ARBITRUM_SEPOLIA_RPC_URL:-${DARWIN_RPC_URL:-https://sepolia-rollup.arbitrum.io/rpc}}"
export DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-421614}"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/arbitrum-sepolia.json}"

exec "$ROOT/ops/run_darwin_node.sh"
