#!/usr/bin/env bash
set -euo pipefail

STACK_DIR="${DARWIN_PI_STACK_DIR:-/opt/darwin-public-site}"
SITE_DIR="${DARWIN_PI_SITE_DIR:-/srv/usedarwin/site/current}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required on the Raspberry Pi"
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "docker compose is required on the Raspberry Pi"
  exit 1
fi

sudo mkdir -p "$STACK_DIR"
sudo mkdir -p "$SITE_DIR"
sudo cp "$REPO_ROOT/ops/pi/Caddyfile" "$STACK_DIR/Caddyfile"
sudo cp "$REPO_ROOT/ops/pi/docker-compose.public-site.yml" "$STACK_DIR/docker-compose.yml"
if [[ ! -f "$STACK_DIR/cloudflared-config.yml" ]]; then
  sudo cp "$REPO_ROOT/ops/pi/cloudflared-config.yml.example" "$STACK_DIR/cloudflared-config.yml"
fi

if [[ ! -f "$STACK_DIR/.env" ]]; then
  sudo cp "$REPO_ROOT/ops/pi/.env.public-site.example" "$STACK_DIR/.env"
fi

cat <<EOF
[darwin-pi] stack files installed
  stack: $STACK_DIR
  site:  $SITE_DIR

Next:
1. Copy the tunnel credentials JSON into $STACK_DIR
2. Edit $STACK_DIR/cloudflared-config.yml and set the tunnel id + hostnames
3. Edit $STACK_DIR/.env if you want a different credentials filename
4. Sync the static site into $SITE_DIR
5. Start the stack:
     cd $STACK_DIR
     sudo docker compose up -d
EOF
