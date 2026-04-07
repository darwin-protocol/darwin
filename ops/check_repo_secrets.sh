#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_FILE="${GITLEAKS_CONFIG:-$ROOT_DIR/.gitleaks.toml}"
REPORT_PATH="${GITLEAKS_REPORT_PATH:-$ROOT_DIR/ops/state/gitleaks-report.json}"

if ! command -v gitleaks >/dev/null 2>&1; then
  echo "[gitleaks] gitleaks is not installed" >&2
  exit 127
fi

mkdir -p "$(dirname "$REPORT_PATH")"

cd "$ROOT_DIR"
gitleaks detect \
  --source . \
  --config "$CONFIG_FILE" \
  --redact \
  --no-banner \
  --report-format json \
  --report-path "$REPORT_PATH"
