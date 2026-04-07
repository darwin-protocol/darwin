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
MARKET_CONFIG_PATH="$REPO_ROOT/web/public/market-config.json"
RUNTIME_STATUS_PATH="$REPO_ROOT/web/public/runtime-status.json"
TMP_DIR="$(mktemp -d)"

restore_files() {
  if [[ -f "$TMP_DIR/market-config.json" ]]; then
    cp "$TMP_DIR/market-config.json" "$MARKET_CONFIG_PATH"
  fi
  if [[ -f "$TMP_DIR/runtime-status.json" ]]; then
    cp "$TMP_DIR/runtime-status.json" "$RUNTIME_STATUS_PATH"
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

pushd "$REPO_ROOT" >/dev/null
python3 ops/export_market_portal_config.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --out web/public/market-config.json
python3 ops/export_runtime_status.py \
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
