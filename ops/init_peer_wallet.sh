#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

PYTHON_BIN="${DARWIN_PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

if [[ "$PYTHON_BIN" != */* ]]; then
  require_cmd "$PYTHON_BIN"
elif [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python interpreter not executable: $PYTHON_BIN" >&2
  exit 1
fi

WALLET_DIR="${DARWIN_WALLET_DIR:-$ROOT/ops/wallets}"
WALLET_LABEL="${DARWIN_WALLET_LABEL:-darwin-peer-user}"
WALLET_FILE="${DARWIN_WALLET_FILE:-$WALLET_DIR/${WALLET_LABEL}.wallet.json}"
PUBLIC_FILE="${DARWIN_WALLET_PUBLIC_FILE:-$WALLET_DIR/${WALLET_LABEL}.account.json}"
PASSPHRASE_FILE="${DARWIN_WALLET_PASSPHRASE_FILE:-$WALLET_DIR/${WALLET_LABEL}.passphrase}"
REQUEST_FILE="${DARWIN_WALLET_REQUEST_FILE:-$WALLET_DIR/${WALLET_LABEL}.request.txt}"
SHARE_FILE="${DARWIN_WALLET_SHARE_FILE:-$WALLET_DIR/${WALLET_LABEL}.share.md}"
DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia-recovery.json}"
REQUEST_AMOUNT="${DARWIN_WALLET_REQUEST_AMOUNT:-25}"
FORCE="${DARWIN_WALLET_FORCE:-0}"

mkdir -p "$WALLET_DIR"

PASS_ENV="${DARWIN_WALLET_PASSPHRASE:-}"
if [[ -n "$PASS_ENV" ]]; then
  PASS_VALUE="$PASS_ENV"
elif [[ -f "$PASSPHRASE_FILE" ]]; then
  PASS_VALUE="$(cat "$PASSPHRASE_FILE")"
else
  PASS_VALUE="$("$PYTHON_BIN" - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
  umask 077
  printf '%s\n' "$PASS_VALUE" >"$PASSPHRASE_FILE"
fi

export DARWIN_WALLET_PASSPHRASE="$PASS_VALUE"
export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"

if [[ "$FORCE" == "1" || ! -f "$WALLET_FILE" ]]; then
  "$PYTHON_BIN" -m darwin_sim.cli.darwinctl wallet-init \
    --deployment-file "$DEPLOYMENT_FILE" \
    --label "$WALLET_LABEL" \
    --out "$WALLET_FILE" >/dev/null
fi

"$PYTHON_BIN" -m darwin_sim.cli.darwinctl wallet-export-public \
  "$WALLET_FILE" \
  --out "$PUBLIC_FILE" >/dev/null

"$PYTHON_BIN" -m darwin_sim.cli.darwinctl wallet-request \
  "$WALLET_FILE" \
  --deployment-file "$DEPLOYMENT_FILE" \
  --amount "$REQUEST_AMOUNT" \
  --out "$REQUEST_FILE" >/dev/null

EVM_ADDR="$("$PYTHON_BIN" - <<'PY' "$PUBLIC_FILE"
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
print(data["evm_addr"])
PY
)"

cat >"$SHARE_FILE" <<EOF
# DARWIN Peer Wallet

- Label: \`$WALLET_LABEL\`
- Address: \`$EVM_ADDR\`
- Requested amount: \`$REQUEST_AMOUNT DRW\`
- Public site: \`https://usedarwin.xyz/\`
- Market page: \`https://usedarwin.xyz/trade/\`
- Deployment artifact: \`$DEPLOYMENT_FILE\`

## Shareable DRW request URI

\`\`\`
$(cat "$REQUEST_FILE")
\`\`\`

This wallet bundle is for peer-to-peer DRW onboarding on Base Sepolia.
EOF

echo "[peer-wallet] Ready"
echo "  label:           $WALLET_LABEL"
echo "  wallet_file:     $WALLET_FILE"
echo "  public_account:  $PUBLIC_FILE"
echo "  request_file:    $REQUEST_FILE"
echo "  share_file:      $SHARE_FILE"
echo "  passphrase_file: $PASSPHRASE_FILE"
echo "  deployment:      $DEPLOYMENT_FILE"
