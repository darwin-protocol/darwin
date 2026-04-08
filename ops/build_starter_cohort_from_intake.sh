#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

export DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia-recovery}"
export DARWIN_STARTER_COHORT_INTAKE="${DARWIN_STARTER_COHORT_INTAKE:-$ROOT/ops/state/${DARWIN_NETWORK}-starter-cohort-intake.csv}"
export DARWIN_STARTER_COHORT_FILE="${DARWIN_STARTER_COHORT_FILE:-$ROOT/ops/state/${DARWIN_NETWORK}-starter-cohort.csv}"

if [[ ! -f "$DARWIN_STARTER_COHORT_INTAKE" ]]; then
  echo "Missing starter cohort intake CSV: $DARWIN_STARTER_COHORT_INTAKE" >&2
  echo "Add rows first with:" >&2
  echo "  python3 ops/intake_starter_cohort.py --network \"$DARWIN_NETWORK\" --row '{\"account\":\"0x...\"}'" >&2
  exit 1
fi

python3 "$ROOT/ops/normalize_starter_cohort.py" \
  --intake-file "$DARWIN_STARTER_COHORT_INTAKE" \
  --out "$DARWIN_STARTER_COHORT_FILE"

"$ROOT/ops/prepare_starter_cohort.sh"
