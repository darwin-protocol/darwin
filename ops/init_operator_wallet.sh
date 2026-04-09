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

ROLE_RAW="${DARWIN_OPERATOR_ROLE:-future-deployer}"
ROLE_SLUG="${ROLE_RAW// /-}"
ROLE_SLUG="${ROLE_SLUG//_/-}"

WALLET_DIR="${DARWIN_WALLET_DIR:-$ROOT/ops/wallets}"
WALLET_LABEL="${DARWIN_WALLET_LABEL:-darwin-${ROLE_SLUG}}"
WALLET_FILE="${DARWIN_WALLET_FILE:-$WALLET_DIR/${WALLET_LABEL}.wallet.json}"
PUBLIC_FILE="${DARWIN_WALLET_PUBLIC_FILE:-$WALLET_DIR/${WALLET_LABEL}.account.json}"
PASSPHRASE_FILE="${DARWIN_WALLET_PASSPHRASE_FILE:-$WALLET_DIR/${WALLET_LABEL}.passphrase}"
SHARE_FILE="${DARWIN_WALLET_SHARE_FILE:-$WALLET_DIR/${WALLET_LABEL}.share.md}"
DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
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

WALLET_LINES=()
while IFS= read -r line; do
  WALLET_LINES+=("$line")
done < <("$PYTHON_BIN" - <<'PY' "$PUBLIC_FILE"
import json, sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text())
print(data["acct_id"])
print(data["evm_addr"])
PY
)
ACCT_ID="${WALLET_LINES[0]}"
EVM_ADDR="${WALLET_LINES[1]}"

ROLE_SUMMARY="fresh DARWIN operator wallet"
ROLE_NOTES="- Fund this wallet with Base Sepolia ETH before using it for on-chain operations."
if [[ "$ROLE_SLUG" == *"governance"* ]]; then
  ROLE_SUMMARY="fresh governance root for future redeploy or migration work"
  ROLE_NOTES=$'- Keep this wallet offline until needed.\n- A governance compromise still requires a full core redeploy because several live contracts hard-wire governance.'
elif [[ "$ROLE_SLUG" == *"deployer"* ]]; then
  ROLE_SUMMARY="fresh deployment signer for future DRW or DARWIN testnet deployments"
  ROLE_NOTES=$'- Fund this wallet with Base Sepolia ETH before any deployment.\n- This wallet does not inherit any current live contract authority automatically.'
fi

cat >"$SHARE_FILE" <<EOF
# DARWIN Operator Wallet

- Role: \`$ROLE_RAW\`
- Label: \`$WALLET_LABEL\`
- Address: \`$EVM_ADDR\`
- Account ID: \`$ACCT_ID\`
- Deployment reference: \`$DEPLOYMENT_FILE\`

## Intended Use

$ROLE_SUMMARY.

## Notes

$ROLE_NOTES

## Files

- Wallet: \`$WALLET_FILE\`
- Public account: \`$PUBLIC_FILE\`
- Passphrase: \`$PASSPHRASE_FILE\`

These files are local-only and gitignored.
EOF

echo "[operator-wallet] Ready"
echo "  role:            $ROLE_RAW"
echo "  label:           $WALLET_LABEL"
echo "  address:         $EVM_ADDR"
echo "  wallet_file:     $WALLET_FILE"
echo "  public_account:  $PUBLIC_FILE"
echo "  share_file:      $SHARE_FILE"
echo "  passphrase_file: $PASSPHRASE_FILE"
echo "  deployment:      $DEPLOYMENT_FILE"
