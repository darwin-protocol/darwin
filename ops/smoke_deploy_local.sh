#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ANVIL_HOST="${ANVIL_HOST:-127.0.0.1}"
ANVIL_PORT="${ANVIL_PORT:-8545}"
ANVIL_RPC_URL="http://${ANVIL_HOST}:${ANVIL_PORT}"
ANVIL_LOG="${ANVIL_LOG:-/tmp/darwin-anvil.log}"

cleanup() {
  if [[ -n "${ANVIL_PID:-}" ]]; then
    kill "$ANVIL_PID" >/dev/null 2>&1 || true
    wait "$ANVIL_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

anvil --host "$ANVIL_HOST" --port "$ANVIL_PORT" >"$ANVIL_LOG" 2>&1 &
ANVIL_PID="$!"

for _ in $(seq 1 30); do
  if cast chain-id --rpc-url "$ANVIL_RPC_URL" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

cast chain-id --rpc-url "$ANVIL_RPC_URL" >/dev/null

export DARWIN_NETWORK="local-anvil"
export DARWIN_RPC_URL="$ANVIL_RPC_URL"
export DARWIN_EXPECT_CHAIN_ID="31337"
export DARWIN_DEPLOYER_PRIVATE_KEY="${DARWIN_DEPLOYER_PRIVATE_KEY:-0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80}"
export DARWIN_GOVERNANCE="${DARWIN_GOVERNANCE:-0x70997970C51812dc3A010C7d01b50e0d17dc79C8}"
export DARWIN_EPOCH_OPERATOR="${DARWIN_EPOCH_OPERATOR:-0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC}"
export DARWIN_SAFE_MODE_AUTHORITY="${DARWIN_SAFE_MODE_AUTHORITY:-0x90F79bf6EB2c4f870365E785982E1f101E93b906}"
export DARWIN_DEPLOY_BOND_ASSET_MOCK="1"
export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/local-anvil.json}"

"$ROOT/ops/deploy_contracts.sh"

if [[ "${DARWIN_DEPLOY_DRW_GENESIS:-0}" == "1" ]]; then
  export DARWIN_DRW_GENESIS_FILE="${DARWIN_DRW_GENESIS_FILE:-$ROOT/ops/deployments/.local-anvil.drw.json}"
  "$ROOT/ops/init_drw_genesis.sh"
fi

source "$ROOT/.venv/bin/activate" 2>/dev/null || true
python3 - <<'PY'
import json, os, pathlib
path = pathlib.Path(os.environ["DARWIN_DEPLOYMENT_FILE"])
data = json.loads(path.read_text())
print("local deployment artifact:")
print(f"  file: {path}")
print(f"  chain_id: {data['chain_id']}")
for name, addr in data["contracts"].items():
    print(f"  {name}: {addr}")
if data.get("drw"):
    print("  drw:")
    print(f"    total_supply: {data['drw'].get('total_supply')}")
    print(f"    staking_duration: {data['drw'].get('staking_duration')}")
PY
