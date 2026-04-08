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
ARBITRUM_MARKET_CONFIG_PATH="$REPO_ROOT/web/public/market-config-arbitrum-sepolia.json"
MARKET_LANES_PATH="$REPO_ROOT/web/public/market-lanes.json"
RUNTIME_STATUS_PATH="$REPO_ROOT/web/public/runtime-status.json"
ACTIVITY_SUMMARY_PATH="$REPO_ROOT/web/public/activity-summary.json"
ARBITRUM_ACTIVITY_SUMMARY_PATH="$REPO_ROOT/web/public/activity-summary-arbitrum-sepolia.json"
COMMUNITY_SHARE_PATH="$REPO_ROOT/web/public/community-share.json"
ARBITRUM_COMMUNITY_SHARE_PATH="$REPO_ROOT/web/public/community-share-arbitrum-sepolia.json"
TMP_DIR="$(mktemp -d)"
ARBITRUM_DEPLOYMENT_FILE="$REPO_ROOT/ops/deployments/arbitrum-sepolia.json"
source "$REPO_ROOT/ops/load_env_defaults.sh"
load_site_publish_env "$REPO_ROOT"

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
  if [[ -f "$TMP_DIR/market-config-arbitrum-sepolia.json" ]]; then
    cp "$TMP_DIR/market-config-arbitrum-sepolia.json" "$ARBITRUM_MARKET_CONFIG_PATH"
  fi
  if [[ -f "$TMP_DIR/market-lanes.json" ]]; then
    cp "$TMP_DIR/market-lanes.json" "$MARKET_LANES_PATH"
  fi
  if [[ -f "$TMP_DIR/activity-summary.json" ]]; then
    cp "$TMP_DIR/activity-summary.json" "$ACTIVITY_SUMMARY_PATH"
  fi
  if [[ -f "$TMP_DIR/activity-summary-arbitrum-sepolia.json" ]]; then
    cp "$TMP_DIR/activity-summary-arbitrum-sepolia.json" "$ARBITRUM_ACTIVITY_SUMMARY_PATH"
  fi
  if [[ -f "$TMP_DIR/community-share.json" ]]; then
    cp "$TMP_DIR/community-share.json" "$COMMUNITY_SHARE_PATH"
  fi
  if [[ -f "$TMP_DIR/community-share-arbitrum-sepolia.json" ]]; then
    cp "$TMP_DIR/community-share-arbitrum-sepolia.json" "$ARBITRUM_COMMUNITY_SHARE_PATH"
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
if [[ -f "$ARBITRUM_MARKET_CONFIG_PATH" ]]; then
  cp "$ARBITRUM_MARKET_CONFIG_PATH" "$TMP_DIR/market-config-arbitrum-sepolia.json"
fi
if [[ -f "$MARKET_LANES_PATH" ]]; then
  cp "$MARKET_LANES_PATH" "$TMP_DIR/market-lanes.json"
fi
cp "$ACTIVITY_SUMMARY_PATH" "$TMP_DIR/activity-summary.json"
if [[ -f "$ARBITRUM_ACTIVITY_SUMMARY_PATH" ]]; then
  cp "$ARBITRUM_ACTIVITY_SUMMARY_PATH" "$TMP_DIR/activity-summary-arbitrum-sepolia.json"
fi
cp "$COMMUNITY_SHARE_PATH" "$TMP_DIR/community-share.json"
if [[ -f "$ARBITRUM_COMMUNITY_SHARE_PATH" ]]; then
  cp "$ARBITRUM_COMMUNITY_SHARE_PATH" "$TMP_DIR/community-share-arbitrum-sepolia.json"
fi

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
market_lane_args=(
  --config "/market-config.json=web/public/market-config.json"
)
if [[ -f "$ARBITRUM_DEPLOYMENT_FILE" ]]; then
  if "$PYTHON_BIN" ops/export_market_portal_config.py \
    --deployment-file "$ARBITRUM_DEPLOYMENT_FILE" \
    --out web/public/market-config-arbitrum-sepolia.json >/dev/null 2>&1; then
    echo "[darwin-pi] Arbitrum market config exported"
    market_lane_args+=(--config "/market-config-arbitrum-sepolia.json=web/public/market-config-arbitrum-sepolia.json")
    if "$PYTHON_BIN" ops/report_external_activity.py \
      --deployment-file "$ARBITRUM_DEPLOYMENT_FILE" \
      --json-out ops/state/activity/external-activity-arbitrum-sepolia.json \
      --markdown-out ops/state/activity/external-activity-arbitrum-sepolia.md \
      --public-json-out web/public/activity-summary-arbitrum-sepolia.json >/dev/null 2>&1; then
      echo "[darwin-pi] Arbitrum public activity summary exported"
    else
      echo "[darwin-pi] warning: failed to refresh Arbitrum activity summary; keeping existing file" >&2
    fi
  else
    echo "[darwin-pi] warning: failed to refresh Arbitrum market config; keeping existing file" >&2
  fi
fi
"$PYTHON_BIN" ops/export_market_lane_index.py \
  --out web/public/market-lanes.json \
  "${market_lane_args[@]}"
"$PYTHON_BIN" ops/export_runtime_status.py \
  --hosting-mode cloudflare-tunnel \
  --site-domain "$SITE_DOMAIN" \
  --out web/public/runtime-status.json
if "$PYTHON_BIN" ops/export_community_share_bundle.py \
  --market-config web/public/market-config.json \
  --activity-summary web/public/activity-summary.json \
  --site-url "https://${SITE_DOMAIN}" \
  --out web/public/community-share.json >/dev/null; then
  echo "[darwin-pi] community share bundle exported"
else
  echo "[darwin-pi] warning: failed to refresh community share bundle; keeping existing file" >&2
fi
if [[ -f "$ARBITRUM_MARKET_CONFIG_PATH" ]] && [[ -f "$ARBITRUM_ACTIVITY_SUMMARY_PATH" ]]; then
  if "$PYTHON_BIN" ops/export_community_share_bundle.py \
    --market-config web/public/market-config-arbitrum-sepolia.json \
    --activity-summary web/public/activity-summary-arbitrum-sepolia.json \
    --site-url "https://${SITE_DOMAIN}" \
    --out web/public/community-share-arbitrum-sepolia.json >/dev/null; then
    echo "[darwin-pi] Arbitrum community share bundle exported"
  else
    echo "[darwin-pi] warning: failed to refresh Arbitrum community share bundle; keeping existing file" >&2
  fi
fi
DARWIN_SITE_DOMAIN="$SITE_DOMAIN" DARWIN_SITE_BASE_PATH="" npm --prefix web run build
rsync -az --delete web/out/ "${PI_USER}@${PI_HOST}:${DEST_DIR}/"
popd >/dev/null

echo "[darwin-pi] static site published"
echo "  host: ${PI_USER}@${PI_HOST}"
echo "  dest: ${DEST_DIR}"
echo "  site: ${SITE_DOMAIN}"
