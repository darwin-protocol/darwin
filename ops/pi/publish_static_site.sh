#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <pi-host> [pi-user]"
  exit 1
fi

PI_HOST="$1"
PI_USER="${2:-pi}"
DEST_DIR="${DARWIN_PI_SITE_DIR:-/srv/usedarwin/site/current}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SITE_DOMAIN="${DARWIN_SITE_DOMAIN:-usedarwin.xyz}"
PORTAL_DEPLOYMENT_FILE="${DARWIN_PORTAL_DEPLOYMENT_FILE:-$REPO_ROOT/ops/deployments/base-sepolia-recovery.json}"
PYTHON_BIN="${DARWIN_PYTHON:-$REPO_ROOT/.venv/bin/python}"
MARKET_CONFIG_PATH="$REPO_ROOT/web/public/market-config.json"
RUNTIME_STATUS_PATH="$REPO_ROOT/web/public/runtime-status.json"
ACTIVITY_SUMMARY_PATH="$REPO_ROOT/web/public/activity-summary.json"
TMP_DIR="$(mktemp -d)"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

restore_files() {
  if [[ -f "$TMP_DIR/market-config.json" ]]; then
    cp "$TMP_DIR/market-config.json" "$MARKET_CONFIG_PATH"
  fi
  if [[ -f "$TMP_DIR/runtime-status.json" ]]; then
    cp "$TMP_DIR/runtime-status.json" "$RUNTIME_STATUS_PATH"
  fi
  if [[ -f "$TMP_DIR/activity-summary.json" ]]; then
    cp "$TMP_DIR/activity-summary.json" "$ACTIVITY_SUMMARY_PATH"
  fi
  rm -rf "$TMP_DIR"
}

trap restore_files EXIT

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required"
  exit 1
fi

cp "$MARKET_CONFIG_PATH" "$TMP_DIR/market-config.json"
cp "$RUNTIME_STATUS_PATH" "$TMP_DIR/runtime-status.json"
cp "$ACTIVITY_SUMMARY_PATH" "$TMP_DIR/activity-summary.json"

pushd "$REPO_ROOT" >/dev/null
if "$PYTHON_BIN" ops/build_project_wallet_allowlist.py >/dev/null && \
  "$PYTHON_BIN" ops/report_external_activity.py \
    --deployment-file "$PORTAL_DEPLOYMENT_FILE" \
    --json-out ops/state/activity/external-activity.json \
    --markdown-out ops/state/activity/external-activity.md \
    --public-json-out web/public/activity-summary.json >/dev/null; then
  echo "[darwin-pi] public activity summary exported"
else
  echo "[darwin-pi] warning: failed to refresh public activity summary; keeping existing file" >&2
fi

"$PYTHON_BIN" ops/export_market_portal_config.py \
  --deployment-file "$PORTAL_DEPLOYMENT_FILE" \
  --out web/public/market-config.json
"$PYTHON_BIN" ops/export_runtime_status.py \
  --hosting-mode cloudflare-tunnel \
  --site-domain "$SITE_DOMAIN" \
  --out web/public/runtime-status.json
DARWIN_SITE_DOMAIN="$SITE_DOMAIN" DARWIN_SITE_BASE_PATH="" npm --prefix web run build
rsync -az --delete web/out/ "${PI_USER}@${PI_HOST}:${DEST_DIR}/"
popd >/dev/null

echo "[darwin-pi] static site published"
echo "  host: ${PI_USER}@${PI_HOST}"
echo "  dest: ${DEST_DIR}"
echo "  site: ${SITE_DOMAIN}"
