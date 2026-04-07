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

if ! command -v rsync >/dev/null 2>&1; then
  echo "rsync is required"
  exit 1
fi

pushd "$REPO_ROOT" >/dev/null
npm --prefix web run build
rsync -az --delete web/out/ "${PI_USER}@${PI_HOST}:${DEST_DIR}/"
popd >/dev/null

echo "[darwin-pi] static site published"
echo "  host: ${PI_USER}@${PI_HOST}"
echo "  dest: ${DEST_DIR}"
