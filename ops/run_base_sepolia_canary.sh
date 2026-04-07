#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
export DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia}"
export DARWIN_RPC_URL="${BASE_SEPOLIA_RPC_URL:-${DARWIN_RPC_URL:-https://base-sepolia-rpc.publicnode.com}}"
export DARWIN_STATE_ROOT="${DARWIN_STATE_ROOT:-$ROOT/ops/state/base-sepolia-canary}"
export DARWIN_NODE_ALLOW_COLD_WATCHER="${DARWIN_NODE_ALLOW_COLD_WATCHER:-1}"
export DARWIN_NODE_SEED_DIR="${DARWIN_NODE_SEED_DIR:-${DARWIN_CANARY_SEED_DIR:-}}"
export DARWIN_NODE_SEED_EPOCH_ID="${DARWIN_NODE_SEED_EPOCH_ID:-${DARWIN_CANARY_SEED_EPOCH_ID:-canary-1}}"

exec "$ROOT/ops/run_darwin_node.sh"
