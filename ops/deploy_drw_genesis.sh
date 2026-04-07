#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

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

export DARWIN_EXPECT_CHAIN_ID="${DARWIN_EXPECT_CHAIN_ID:-0}"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.json}"

if [[ ! -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  echo "Missing core deployment artifact: $DARWIN_DEPLOYMENT_FILE" >&2
  exit 1
fi

deployment_basename="$(basename "$DARWIN_DEPLOYMENT_FILE" .json)"
export DARWIN_DRW_GENESIS_FILE="${DARWIN_DRW_GENESIS_FILE:-$ROOT/ops/deployments/.${deployment_basename}.drw.json}"

mkdir -p "$(dirname "$DARWIN_DRW_GENESIS_FILE")"

detected_chain_id="$(cast chain-id --rpc-url "$DARWIN_RPC_URL")"
if [[ "$DARWIN_EXPECT_CHAIN_ID" != "0" && "$detected_chain_id" != "$DARWIN_EXPECT_CHAIN_ID" ]]; then
  echo "Chain ID mismatch: expected $DARWIN_EXPECT_CHAIN_ID, got $detected_chain_id" >&2
  exit 1
fi

cd "$ROOT/contracts"
forge script script/DeployDRWGenesis.s.sol:DeployDRWGenesis \
  --rpc-url "$DARWIN_RPC_URL" \
  --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY" \
  --broadcast \
  --slow \
  --non-interactive

python3 - "$DARWIN_DEPLOYMENT_FILE" "$DARWIN_DRW_GENESIS_FILE" <<'PY'
import json
import sys
from pathlib import Path

deployment_path = Path(sys.argv[1])
drw_path = Path(sys.argv[2])

deployment = json.loads(deployment_path.read_text())
drw_deployment = json.loads(drw_path.read_text())

contracts = deployment.setdefault("contracts", {})
contracts.update(drw_deployment.get("contracts", {}))
deployment["drw"] = drw_deployment

deployment_path.write_text(json.dumps(deployment, indent=2, sort_keys=True) + "\n")
PY

echo "DARWIN DRW genesis merged into deployment artifact."
echo "  deployment: $DARWIN_DEPLOYMENT_FILE"
echo "  drw_json:    $DARWIN_DRW_GENESIS_FILE"
