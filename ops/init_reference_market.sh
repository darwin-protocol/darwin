#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

export DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK:-base-sepolia}.json}"

if [[ ! -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  echo "Missing deployment artifact: $DARWIN_DEPLOYMENT_FILE" >&2
  exit 1
fi

read_deployment_field() {
  python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" "$1"
}

if ! python3 - "$DARWIN_DEPLOYMENT_FILE" <<'PY' >/dev/null 2>&1
import json, sys
data = json.loads(open(sys.argv[1]).read())
raise SystemExit(0 if data.get("drw") else 1)
PY
then
  echo "Deployment artifact has no DRW section. Run DRW genesis before deploying the reference market." >&2
  exit 1
fi

export DARWIN_NETWORK="${DARWIN_NETWORK:-$(read_deployment_field network)}"
export DARWIN_GOVERNANCE="${DARWIN_GOVERNANCE:-$(read_deployment_field roles.governance)}"
export DARWIN_REFERENCE_MARKET_OPERATOR="${DARWIN_REFERENCE_MARKET_OPERATOR:-$DARWIN_GOVERNANCE}"
export DARWIN_REFERENCE_MARKET_BASE_TOKEN="${DARWIN_REFERENCE_MARKET_BASE_TOKEN:-$(read_deployment_field drw.contracts.drw_token)}"
export DARWIN_REFERENCE_MARKET_QUOTE_TOKEN="${DARWIN_REFERENCE_MARKET_QUOTE_TOKEN:-$(read_deployment_field contracts.bond_asset)}"
export DARWIN_REFERENCE_MARKET_FEE_BPS="${DARWIN_REFERENCE_MARKET_FEE_BPS:-30}"

exec "$ROOT/ops/deploy_reference_market.sh"
