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
require_env DARWIN_DEPLOYMENT_FILE
require_env DARWIN_REFERENCE_MARKET_BASE_AMOUNT
require_env DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT

read_deployment_field() {
  python3 - "$DARWIN_DEPLOYMENT_FILE" "$1" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1]).read())
cursor = data
for part in sys.argv[2].split("."):
    cursor = cursor[part]
print(cursor)
PY
}

POOL_ADDRESS="${DARWIN_REFERENCE_MARKET_POOL:-$(read_deployment_field market.contracts.reference_pool)}"
BASE_TOKEN="${DARWIN_REFERENCE_MARKET_BASE_TOKEN:-$(read_deployment_field market.base_token)}"
QUOTE_TOKEN="${DARWIN_REFERENCE_MARKET_QUOTE_TOKEN:-$(read_deployment_field market.quote_token)}"
SEEDER_PRIVATE_KEY="${DARWIN_REFERENCE_MARKET_SEEDER_PRIVATE_KEY:-${DARWIN_DEPLOYER_PRIVATE_KEY:-}}"

require_env SEEDER_PRIVATE_KEY

SEEDER_ADDRESS="$(cast wallet address --private-key "$SEEDER_PRIVATE_KEY")"

cast send "$BASE_TOKEN" "approve(address,uint256)" "$POOL_ADDRESS" "$DARWIN_REFERENCE_MARKET_BASE_AMOUNT" \
  --private-key "$SEEDER_PRIVATE_KEY" \
  --rpc-url "$DARWIN_RPC_URL" >/dev/null

cast send "$QUOTE_TOKEN" "approve(address,uint256)" "$POOL_ADDRESS" "$DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT" \
  --private-key "$SEEDER_PRIVATE_KEY" \
  --rpc-url "$DARWIN_RPC_URL" >/dev/null

cast send "$POOL_ADDRESS" "seedInitialLiquidity(uint256,uint256)" \
  "$DARWIN_REFERENCE_MARKET_BASE_AMOUNT" "$DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT" \
  --private-key "$SEEDER_PRIVATE_KEY" \
  --rpc-url "$DARWIN_RPC_URL"

python3 - "$DARWIN_DEPLOYMENT_FILE" "$DARWIN_REFERENCE_MARKET_BASE_AMOUNT" "$DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT" <<'PY'
import json
import sys
from pathlib import Path

deployment_path = Path(sys.argv[1])
base_amount = sys.argv[2]
quote_amount = sys.argv[3]
deployment = json.loads(deployment_path.read_text())
market = deployment.setdefault("market", {})
market["seeded"] = True
market["initial_base_amount"] = base_amount
market["initial_quote_amount"] = quote_amount
deployment_path.write_text(json.dumps(deployment, indent=2, sort_keys=True) + "\n")
PY

echo "DARWIN reference market seeded."
echo "  deployment: $DARWIN_DEPLOYMENT_FILE"
echo "  pool:       $POOL_ADDRESS"
echo "  seeder:     $SEEDER_ADDRESS"
