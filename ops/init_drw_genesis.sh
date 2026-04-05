#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"

if [[ ! -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  echo "Missing deployment artifact: $DARWIN_DEPLOYMENT_FILE" >&2
  exit 1
fi

read_deployment_field() {
  python3 - "$DARWIN_DEPLOYMENT_FILE" "$1" <<'PY'
import json
import sys

path = sys.argv[1]
field = sys.argv[2]
data = json.loads(open(path).read())

cursor = data
for part in field.split("."):
    cursor = cursor[part]
print(cursor)
PY
}

export DARWIN_NETWORK="${DARWIN_NETWORK:-$(read_deployment_field network)}"
export DARWIN_GOVERNANCE="${DARWIN_GOVERNANCE:-$(read_deployment_field roles.governance)}"
export DARWIN_DRW_TOTAL_SUPPLY="${DARWIN_DRW_TOTAL_SUPPLY:-1000000000000000000000000000}"
export DARWIN_DRW_TREASURY_RECIPIENT="${DARWIN_DRW_TREASURY_RECIPIENT:-$DARWIN_GOVERNANCE}"
export DARWIN_DRW_INSURANCE_RECIPIENT="${DARWIN_DRW_INSURANCE_RECIPIENT:-$DARWIN_GOVERNANCE}"
export DARWIN_DRW_SPONSOR_REWARDS_RECIPIENT="${DARWIN_DRW_SPONSOR_REWARDS_RECIPIENT:-$DARWIN_GOVERNANCE}"
export DARWIN_DRW_COMMUNITY_RECIPIENT="${DARWIN_DRW_COMMUNITY_RECIPIENT:-$DARWIN_GOVERNANCE}"
export DARWIN_DRW_TREASURY_BPS="${DARWIN_DRW_TREASURY_BPS:-2000}"
export DARWIN_DRW_INSURANCE_BPS="${DARWIN_DRW_INSURANCE_BPS:-2000}"
export DARWIN_DRW_SPONSOR_REWARDS_BPS="${DARWIN_DRW_SPONSOR_REWARDS_BPS:-1000}"
export DARWIN_DRW_STAKING_BPS="${DARWIN_DRW_STAKING_BPS:-3000}"
export DARWIN_DRW_COMMUNITY_BPS="${DARWIN_DRW_COMMUNITY_BPS:-2000}"
export DARWIN_DRW_STAKING_DURATION="${DARWIN_DRW_STAKING_DURATION:-31536000}"

if [[ "${DARWIN_SKIP_PREFLIGHT:-0}" != "1" ]]; then
  "$ROOT/ops/preflight_drw_genesis.sh"
fi

exec "$ROOT/ops/deploy_drw_genesis.sh"
