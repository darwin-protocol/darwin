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

export DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY="${DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY:-${DARWIN_GOVERNANCE_PRIVATE_KEY:-${DARWIN_DEPLOYER_PRIVATE_KEY:-}}}"
require_env DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY

FAUCET_ADDRESS="${DARWIN_DRW_FAUCET_ADDRESS:-$(read_deployment_field faucet.contracts.drw_faucet)}"
TOKEN_ADDRESS="${DARWIN_DRW_FAUCET_TOKEN:-$(read_deployment_field drw.contracts.drw_token)}"
TOKEN_FUNDING="${DARWIN_DRW_FAUCET_INITIAL_TOKEN_FUNDING:-100000000000000000000000}"
NATIVE_FUNDING="${DARWIN_DRW_FAUCET_INITIAL_NATIVE_FUNDING:-200000000000000}"
FUNDER_ADDRESS="$(cast wallet address --private-key "$DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY")"
NEXT_NONCE="$(cast nonce "$FUNDER_ADDRESS" --block pending --rpc-url "$DARWIN_RPC_URL")"

if [[ "$TOKEN_FUNDING" != "0" ]]; then
  cast send "$TOKEN_ADDRESS" "transfer(address,uint256)" "$FAUCET_ADDRESS" "$TOKEN_FUNDING" \
    --nonce "$NEXT_NONCE" \
    --private-key "$DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY" \
    --rpc-url "$DARWIN_RPC_URL" >/dev/null
  NEXT_NONCE="$((NEXT_NONCE + 1))"
fi

if [[ "$NATIVE_FUNDING" != "0" ]]; then
  cast send "$FAUCET_ADDRESS" "fundNative()" \
    --nonce "$NEXT_NONCE" \
    --value "$NATIVE_FUNDING" \
    --private-key "$DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY" \
    --rpc-url "$DARWIN_RPC_URL" >/dev/null
fi

python3 - "$DARWIN_DEPLOYMENT_FILE" "$TOKEN_FUNDING" "$NATIVE_FUNDING" <<'PY'
import json
import sys
from pathlib import Path

deployment_path = Path(sys.argv[1])
token_funding = sys.argv[2]
native_funding = sys.argv[3]

deployment = json.loads(deployment_path.read_text())
faucet = deployment.setdefault("faucet", {})
faucet["funded"] = token_funding != "0" or native_funding != "0"
faucet["initial_token_funding"] = token_funding
faucet["initial_native_funding"] = native_funding

deployment_path.write_text(json.dumps(deployment, indent=2, sort_keys=True) + "\n")
PY

echo "DARWIN DRW faucet funded."
echo "  deployment: $DARWIN_DEPLOYMENT_FILE"
echo "  faucet:     $FAUCET_ADDRESS"
echo "  token:      $TOKEN_FUNDING"
echo "  native:     $NATIVE_FUNDING"
