#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_arbitrum_sepolia_env "$ROOT"

export DARWIN_NETWORK="${DARWIN_NETWORK:-arbitrum-sepolia}"
export DARWIN_RPC_URL="${ARBITRUM_SEPOLIA_RPC_URL:-${DARWIN_RPC_URL:-https://sepolia-rollup.arbitrum.io/rpc}}"
export DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-421614}"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/arbitrum-sepolia.json}"
export DARWIN_GATEWAY_PORT="${DARWIN_GATEWAY_PORT:-9543}"
export DARWIN_ROUTER_PORT="${DARWIN_ROUTER_PORT:-9544}"
export DARWIN_SCORER_PORT="${DARWIN_SCORER_PORT:-9545}"
export DARWIN_WATCHER_PORT="${DARWIN_WATCHER_PORT:-9546}"
export DARWIN_ARCHIVE_PORT="${DARWIN_ARCHIVE_PORT:-9547}"
export DARWIN_FINALIZER_PORT="${DARWIN_FINALIZER_PORT:-9548}"
export DARWIN_SENTINEL_PORT="${DARWIN_SENTINEL_PORT:-9549}"

exec "$ROOT/ops/run_darwin_node.sh"
