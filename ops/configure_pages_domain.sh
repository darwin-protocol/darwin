#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-darwin-protocol/darwin}"
API_VERSION="${GITHUB_API_VERSION:-2026-03-10}"
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage:
  ./ops/configure_pages_domain.sh [--dry-run] example.com

What it does:
  - sets the DARWIN_SITE_DOMAIN repo variable
  - clears the Pages base path variable
  - sets the GitHub repo homepage
  - updates the GitHub Pages custom domain
  - triggers the Pages workflow so the build emits the right CNAME

What it does not do:
  - edit registrar DNS for you
  - verify the domain in GitHub org settings
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      break
      ;;
  esac
done

PRIMARY_DOMAIN="${1:-}"
if [[ -z "$PRIMARY_DOMAIN" ]]; then
  usage >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Missing gh CLI." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing python3." >&2
  exit 1
fi

if ! gh api user >/dev/null 2>&1; then
  echo "gh CLI is not authenticated for API calls." >&2
  exit 1
fi

HTTPS_URL="https://${PRIMARY_DOMAIN}/"

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    printf '[dry-run] %q' "$1"
    shift
    for arg in "$@"; do
      printf ' %q' "$arg"
    done
    printf '\n'
    return 0
  fi

  "$@"
}

PAGES_PAYLOAD="$(
  python3 - "$PRIMARY_DOMAIN" <<'PY'
import json
import sys

domain = sys.argv[1]
print(json.dumps({
    "cname": domain,
    "https_enforced": True,
    "build_type": "workflow",
    "source": {"branch": "main", "path": "/"},
}))
PY
)"

echo "Configuring GitHub-side Pages settings for ${PRIMARY_DOMAIN} on ${REPO}."
run gh variable set DARWIN_SITE_DOMAIN --repo "$REPO" --body "$PRIMARY_DOMAIN"

if gh variable get DARWIN_SITE_BASE_PATH --repo "$REPO" >/dev/null 2>&1; then
  run gh variable delete DARWIN_SITE_BASE_PATH --repo "$REPO"
fi

run gh repo edit "$REPO" --homepage "$HTTPS_URL"
if [[ "$DRY_RUN" -eq 1 ]]; then
  printf '[dry-run] %s\n' "gh api --method PUT repos/${REPO}/pages <payload>"
else
  printf '%s' "$PAGES_PAYLOAD" | gh api \
    --method PUT \
    -H "X-GitHub-Api-Version: ${API_VERSION}" \
    "repos/${REPO}/pages" \
    --input -
fi
run gh workflow run pages.yml --repo "$REPO"

cat <<EOF

GitHub-side configuration is complete.

Registrar DNS still needs to point ${PRIMARY_DOMAIN} at GitHub Pages:

A     @    185.199.108.153
A     @    185.199.109.153
A     @    185.199.110.153
A     @    185.199.111.153
AAAA  @    2606:50c0:8000::153
AAAA  @    2606:50c0:8001::153
AAAA  @    2606:50c0:8002::153
AAAA  @    2606:50c0:8003::153
CNAME www  darwin-protocol.github.io.

Recommended registrar cleanup:
- use ${PRIMARY_DOMAIN} as the canonical host
- forward any spare promo domains with a 301 redirect to ${HTTPS_URL}
- verify the domain in GitHub org settings before or immediately after DNS cutover

After DNS propagates:
  gh api repos/${REPO}/pages/health
EOF
