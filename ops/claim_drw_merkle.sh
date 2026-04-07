#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"
export DARWIN_VNEXT_FILE="${DARWIN_VNEXT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.vnext.json}"
export DARWIN_VNEXT_DISTRIBUTION_FILE="${DARWIN_VNEXT_DISTRIBUTION_FILE:-$ROOT/ops/state/${DARWIN_NETWORK:-base-sepolia}-drw-merkle.json}"

if [[ -n "${DARWIN_MERKLE_CLAIM_PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$DARWIN_MERKLE_CLAIM_PYTHON_BIN"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
else
  PYTHON_BIN="python3"
fi

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

require_cmd cast
require_cmd forge

CLAIM_INDEX="${DARWIN_MERKLE_CLAIM_INDEX:-}"
if [[ -z "$CLAIM_INDEX" ]]; then
  echo "Missing claim index. Set DARWIN_MERKLE_CLAIM_INDEX." >&2
  exit 1
fi

CLAIM_PRIVATE_KEY="${DARWIN_MERKLE_CLAIM_PRIVATE_KEY:-}"
if [[ -z "$CLAIM_PRIVATE_KEY" ]]; then
  echo "Missing claim signer. Set DARWIN_MERKLE_CLAIM_PRIVATE_KEY." >&2
  exit 1
fi

CLAIM_ACCOUNT="$("$PYTHON_BIN" - "$DARWIN_VNEXT_DISTRIBUTION_FILE" "$CLAIM_INDEX" <<'PY'
import json
import sys
manifest = json.loads(open(sys.argv[1]).read())
index = int(sys.argv[2])
for claim in manifest["claims"]:
    if int(claim["index"]) == index:
        print(claim["account"])
        raise SystemExit(0)
raise SystemExit(f"missing claim index: {index}")
PY
)"

CLAIM_AMOUNT="$("$PYTHON_BIN" - "$DARWIN_VNEXT_DISTRIBUTION_FILE" "$CLAIM_INDEX" <<'PY'
import json
import sys
manifest = json.loads(open(sys.argv[1]).read())
index = int(sys.argv[2])
for claim in manifest["claims"]:
    if int(claim["index"]) == index:
        print(claim["amount"])
        raise SystemExit(0)
raise SystemExit(f"missing claim index: {index}")
PY
)"

DISTRIBUTOR_ADDRESS="$("$PYTHON_BIN" - "$DARWIN_VNEXT_FILE" <<'PY'
import json
import sys
data = json.loads(open(sys.argv[1]).read())
print(data["vnext"]["contracts"]["drw_merkle_distributor"])
PY
)"

SIGNER_ADDRESS="$(cast wallet address --private-key "$CLAIM_PRIVATE_KEY" | tr '[:upper:]' '[:lower:]')"
EXPECTED_ADDRESS="$(printf '%s' "$CLAIM_ACCOUNT" | tr '[:upper:]' '[:lower:]')"
if [[ "$SIGNER_ADDRESS" != "$EXPECTED_ADDRESS" ]]; then
  echo "Claim signer does not match claim account." >&2
  echo "  expected: $CLAIM_ACCOUNT" >&2
  echo "  signer:   $SIGNER_ADDRESS" >&2
  exit 1
fi

echo "DARWIN Merkle claim"
echo "  distributor: $DISTRIBUTOR_ADDRESS"
echo "  account:     $CLAIM_ACCOUNT"
echo "  index:       $CLAIM_INDEX"
echo "  amount:      $CLAIM_AMOUNT"

cd "$ROOT/contracts"
forge script script/ClaimDRWMerkle.s.sol:ClaimDRWMerkle \
  --rpc-url "$DARWIN_RPC_URL" \
  --private-key "$CLAIM_PRIVATE_KEY" \
  --broadcast \
  --slow \
  --non-interactive
