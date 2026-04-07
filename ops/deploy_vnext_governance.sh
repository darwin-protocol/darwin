#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

read_manifest_field() {
  python3 - "$DARWIN_VNEXT_DISTRIBUTION_FILE" "$1" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1]).read())
cursor = data
for part in sys.argv[2].split("."):
    cursor = cursor[part]
print(cursor)
PY
}

"$ROOT/ops/preflight_vnext_governance.sh"

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.json}"
export DARWIN_VNEXT_DISTRIBUTION_FILE="${DARWIN_VNEXT_DISTRIBUTION_FILE:-$ROOT/ops/state/${DARWIN_NETWORK}-drw-merkle.json}"
export DARWIN_VNEXT_FILE="${DARWIN_VNEXT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.vnext.json}"

if [[ -z "${DARWIN_VNEXT_DISTRIBUTION_TOKEN:-}" ]]; then
  DARWIN_VNEXT_DISTRIBUTION_TOKEN="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" contracts.drw_token)"
  export DARWIN_VNEXT_DISTRIBUTION_TOKEN
fi

if [[ -f "$DARWIN_VNEXT_DISTRIBUTION_FILE" ]]; then
  if [[ -z "${DARWIN_VNEXT_MERKLE_ROOT:-}" ]]; then
    DARWIN_VNEXT_MERKLE_ROOT="$(read_manifest_field merkle_root)"
    export DARWIN_VNEXT_MERKLE_ROOT
  fi
  if [[ -z "${DARWIN_VNEXT_CLAIM_COUNT:-}" ]]; then
    DARWIN_VNEXT_CLAIM_COUNT="$(read_manifest_field claims_count)"
    export DARWIN_VNEXT_CLAIM_COUNT
  fi
  if [[ -z "${DARWIN_VNEXT_TOTAL_AMOUNT:-}" ]]; then
    DARWIN_VNEXT_TOTAL_AMOUNT="$(read_manifest_field total_amount)"
    export DARWIN_VNEXT_TOTAL_AMOUNT
  fi
  if [[ -z "${DARWIN_VNEXT_CLAIM_DEADLINE:-}" ]]; then
    DARWIN_VNEXT_CLAIM_DEADLINE="$(read_manifest_field claim_deadline)"
    export DARWIN_VNEXT_CLAIM_DEADLINE
  fi
fi

mkdir -p "$(dirname "$DARWIN_VNEXT_FILE")"

cd "$ROOT/contracts"
forge script script/DeployVNextGovernance.s.sol:DeployVNextGovernance \
  --rpc-url "$DARWIN_RPC_URL" \
  --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY" \
  --broadcast \
  --slow \
  --non-interactive

echo "DARWIN vNext governance deployment complete."
echo "  vnext_json: $DARWIN_VNEXT_FILE"
