#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

resolve_python() {
  if [[ -n "${DARWIN_PYTHON_BIN:-}" ]]; then
    echo "$DARWIN_PYTHON_BIN"
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then
    echo "$ROOT/.venv/bin/python"
  else
    echo "python3"
  fi
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 127
  fi
}

PYTHON_BIN="$(resolve_python)"
if [[ "$PYTHON_BIN" != */* ]]; then
  require_cmd "$PYTHON_BIN"
elif [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not executable: $PYTHON_BIN" >&2
  exit 1
fi

OUT="${DARWIN_FLEET_STATUS_FILE:-$ROOT/ops/state/darwin-fleet-status.json}"
"$PYTHON_BIN" "$ROOT/ops/export_darwin_fleet_status.py" --out "$OUT" "$@"

"$PYTHON_BIN" - "$OUT" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text())
summary = payload.get("summary") or {}
print()
print("DARWIN fleet")
print(f"  public:   {summary.get('public_summary', '-')}")
print(f"  operator: {summary.get('operator_summary', '-')}")
for lane in payload.get("lanes") or []:
    smoke = lane.get("latest_intent_smoke") or {}
    smoke_text = ""
    if smoke.get("generated_at"):
        routed = ((smoke.get("router_delta") or {}).get("total_routed"))
        smoke_text = f" | last_smoke={smoke.get('generated_at')} routed={routed}"
    print(f"  - {lane.get('label')}: {lane.get('status_label')} | {lane.get('summary')}{smoke_text}")
PY
