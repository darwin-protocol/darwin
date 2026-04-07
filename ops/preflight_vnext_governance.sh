#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

require_cmd cast
require_cmd forge

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

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"
export DARWIN_VNEXT_DISTRIBUTION_FILE="${DARWIN_VNEXT_DISTRIBUTION_FILE:-$ROOT/ops/state/${DARWIN_NETWORK:-base-sepolia}-drw-merkle.json}"
export DARWIN_VNEXT_FILE="${DARWIN_VNEXT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.vnext.json}"

if [[ -z "${DARWIN_VNEXT_DISTRIBUTION_TOKEN:-}" && -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  DARWIN_VNEXT_DISTRIBUTION_TOKEN="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" contracts.drw_token)"
  export DARWIN_VNEXT_DISTRIBUTION_TOKEN
fi

if [[ -z "${DARWIN_VNEXT_COUNCIL:-}" && -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  DARWIN_VNEXT_COUNCIL="$(python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" roles.governance 2>/dev/null || true)"
  export DARWIN_VNEXT_COUNCIL
fi

if [[ -z "${DARWIN_VNEXT_GUARDIAN:-}" && -n "${DARWIN_VNEXT_COUNCIL:-}" ]]; then
  DARWIN_VNEXT_GUARDIAN="$DARWIN_VNEXT_COUNCIL"
  export DARWIN_VNEXT_GUARDIAN
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
    DARWIN_VNEXT_CLAIM_DEADLINE="$(read_manifest_field claim_deadline 2>/dev/null || true)"
    export DARWIN_VNEXT_CLAIM_DEADLINE
  fi
fi

blockers=()
[[ -n "${DARWIN_RPC_URL:-}" ]] || blockers+=("missing_rpc_url")
[[ -n "${DARWIN_NETWORK:-}" ]] || blockers+=("missing_network")
[[ -n "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" ]] || blockers+=("missing_deployer")
[[ -n "${DARWIN_VNEXT_COUNCIL:-}" ]] || blockers+=("missing_vnext_council")
[[ -n "${DARWIN_VNEXT_GUARDIAN:-}" ]] || blockers+=("missing_vnext_guardian")
[[ -n "${DARWIN_VNEXT_DISTRIBUTION_TOKEN:-}" ]] || blockers+=("missing_vnext_token")
[[ -n "${DARWIN_VNEXT_MERKLE_ROOT:-}" ]] || blockers+=("missing_vnext_merkle_root")
[[ -n "${DARWIN_VNEXT_CLAIM_DEADLINE:-}" ]] || blockers+=("missing_vnext_claim_deadline")

if [[ -n "${DARWIN_EXPECT_CHAIN_ID:-}" && "${DARWIN_EXPECT_CHAIN_ID:-0}" != "0" && -n "${DARWIN_RPC_URL:-}" ]]; then
  detected_chain_id="$(cast chain-id --rpc-url "$DARWIN_RPC_URL")"
  if [[ "$detected_chain_id" != "${DARWIN_EXPECT_CHAIN_ID}" ]]; then
    blockers+=("unexpected_chain_id")
  fi
fi

if [[ -n "${DARWIN_VNEXT_CLAIM_DEADLINE:-}" ]]; then
  now_epoch="$(date +%s)"
  if (( DARWIN_VNEXT_CLAIM_DEADLINE <= now_epoch )); then
    blockers+=("claim_deadline_not_future")
  fi
fi

echo "DARWIN vNext governance preflight"
echo "  deployment_file: $DARWIN_DEPLOYMENT_FILE"
echo "  vnext_file:      $DARWIN_VNEXT_FILE"
echo "  manifest_file:   $DARWIN_VNEXT_DISTRIBUTION_FILE"
echo "  token:           ${DARWIN_VNEXT_DISTRIBUTION_TOKEN:-missing}"
echo "  council:         ${DARWIN_VNEXT_COUNCIL:-missing}"
echo "  guardian:        ${DARWIN_VNEXT_GUARDIAN:-missing}"
echo "  merkle_root:     ${DARWIN_VNEXT_MERKLE_ROOT:-missing}"
echo "  claim_deadline:  ${DARWIN_VNEXT_CLAIM_DEADLINE:-missing}"
echo "  claim_count:     ${DARWIN_VNEXT_CLAIM_COUNT:-0}"
echo "  total_amount:    ${DARWIN_VNEXT_TOTAL_AMOUNT:-0}"

if ((${#blockers[@]} > 0)); then
  echo "  ready_to_deploy: no"
  for blocker in "${blockers[@]}"; do
    echo "  blocked_by:      $blocker"
  done
  exit 1
fi

echo "  ready_to_deploy: yes"
