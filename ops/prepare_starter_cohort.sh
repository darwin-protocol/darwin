#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

export DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia-recovery}"
export DARWIN_STARTER_COHORT_FILE="${DARWIN_STARTER_COHORT_FILE:-$ROOT/ops/state/${DARWIN_NETWORK}-starter-cohort.csv}"
export DARWIN_STARTER_COHORT_OUT="${DARWIN_STARTER_COHORT_OUT:-$ROOT/ops/state/${DARWIN_NETWORK}-starter-cohort-merkle.json}"
export DARWIN_STARTER_COHORT_EXAMPLE="${DARWIN_STARTER_COHORT_EXAMPLE:-$ROOT/ops/community-starter-cohort.example.csv}"

if [[ -z "${DARWIN_STARTER_COHORT_DEADLINE:-}" ]]; then
  DARWIN_STARTER_COHORT_DEADLINE="$(python3 - <<'PY'
import time
print(int(time.time()) + 30 * 24 * 60 * 60)
PY
)"
fi
export DARWIN_STARTER_COHORT_DEADLINE

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

require_cmd python3
require_cmd cast

if [[ ! -f "$DARWIN_STARTER_COHORT_FILE" ]]; then
  echo "Missing starter cohort CSV: $DARWIN_STARTER_COHORT_FILE" >&2
  echo "Copy the tracked example first:" >&2
  echo "  cp \"$DARWIN_STARTER_COHORT_EXAMPLE\" \"$DARWIN_STARTER_COHORT_FILE\"" >&2
  echo "Then replace the placeholder addresses with real outside wallet addresses." >&2
  exit 1
fi

python3 "$ROOT/ops/build_drw_merkle_distribution.py" \
  --claims-file "$DARWIN_STARTER_COHORT_FILE" \
  --format csv \
  --network "$DARWIN_NETWORK" \
  --claim-deadline "$DARWIN_STARTER_COHORT_DEADLINE" \
  --out "$DARWIN_STARTER_COHORT_OUT"

echo "DARWIN starter cohort ready."
echo "  network:        $DARWIN_NETWORK"
echo "  claims_file:    $DARWIN_STARTER_COHORT_FILE"
echo "  manifest:       $DARWIN_STARTER_COHORT_OUT"
echo "  claim_deadline: $DARWIN_STARTER_COHORT_DEADLINE"
echo
echo "Next:"
echo "  1. Review the cohort manifest."
echo "  2. Point DARWIN_VNEXT_DISTRIBUTION_FILE at the new manifest."
echo "  3. Deploy or rotate a distributor before public claims."
echo "  4. Send recipients to the canonical tiny-swap path after claim."
