#!/usr/bin/env bash
set -euo pipefail

REPO="${GITHUB_REPOSITORY:-darwin-protocol/darwin}"
DOMAIN="${1:-usedarwin.xyz}"
WAIT_SECONDS="${WAIT_SECONDS:-0}"

usage() {
  cat <<'EOF'
Usage:
  ./ops/enforce_pages_https.sh [domain]

What it does:
  - verifies the GitHub Pages site is configured for the given custom domain
  - checks whether the HTTPS certificate is actually ready
  - enables HTTPS enforcement in GitHub Pages once the certificate exists

Environment:
  WAIT_SECONDS=300   Poll for up to 300 seconds before giving up
EOF
}

if [[ "${DOMAIN}" == "-h" || "${DOMAIN}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "Missing gh CLI." >&2
  exit 1
fi

if ! gh api user >/dev/null 2>&1; then
  echo "gh CLI is not authenticated for API calls." >&2
  exit 1
fi

deadline=0
if [[ "${WAIT_SECONDS}" =~ ^[0-9]+$ ]] && [[ "${WAIT_SECONDS}" -gt 0 ]]; then
  deadline=$(( $(date +%s) + WAIT_SECONDS ))
fi

while true; do
  pages_json="$(gh api "repos/${REPO}/pages")"
  current_cname="$(python3 - <<'PY' "$pages_json"
import json, sys
data = json.loads(sys.argv[1])
print(data.get("cname") or "")
PY
)"

  if [[ "${current_cname}" != "${DOMAIN}" ]]; then
    echo "Pages cname is '${current_cname}', not '${DOMAIN}'." >&2
    exit 1
  fi

  if gh api --method PUT "repos/${REPO}/pages" -f "cname=${DOMAIN}" -F https_enforced=true >/dev/null 2>&1; then
    echo "HTTPS enforced for ${DOMAIN}."
    gh api "repos/${REPO}/pages"
    exit 0
  fi

  if [[ "${deadline}" -eq 0 || "$(date +%s)" -ge "${deadline}" ]]; then
    echo "Certificate for ${DOMAIN} is not ready yet." >&2
    exit 1
  fi

  echo "Certificate for ${DOMAIN} not ready yet. Waiting..."
  sleep 15
done
