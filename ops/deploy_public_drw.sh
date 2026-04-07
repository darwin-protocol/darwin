#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

export PYTHONPATH="$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"

"$ROOT/ops/preflight_drw_genesis.sh"
"$ROOT/ops/init_drw_genesis.sh"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -m darwin_sim.cli.darwinctl deployment-show --deployment-file "$DARWIN_DEPLOYMENT_FILE"
fi

exec python3 -m darwin_sim.cli.darwinctl deployment-show --deployment-file "$DARWIN_DEPLOYMENT_FILE"
