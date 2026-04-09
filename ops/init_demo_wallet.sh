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
WALLET_LABEL="${DARWIN_WALLET_LABEL:-darwin-demo-trader}"
WALLET_FILE="${DARWIN_WALLET_FILE:-$WALLET_DIR/${WALLET_LABEL}.wallet.json}"
PUBLIC_FILE="${DARWIN_WALLET_PUBLIC_FILE:-$WALLET_DIR/${WALLET_LABEL}.account.json}"
PASSPHRASE_FILE="${DARWIN_WALLET_PASSPHRASE_FILE:-$WALLET_DIR/${WALLET_LABEL}.passphrase}"
INTENT_FILE="${DARWIN_INTENT_FILE:-$ROOT/sim/intent-base-sepolia.json}"
DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
PAIR="${DARWIN_INTENT_PAIR:-ETH_USDC}"
SIDE="${DARWIN_INTENT_SIDE:-BUY}"
QTY="${DARWIN_INTENT_QTY:-1.0}"
PRICE="${DARWIN_INTENT_PRICE:-3500.0}"
SLIPPAGE="${DARWIN_INTENT_SLIPPAGE:-50}"
PROFILE="${DARWIN_INTENT_PROFILE:-BALANCED}"
INTENT_NONCE="${DARWIN_INTENT_NONCE:-}"
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

nonce_args=()
if [[ -n "$INTENT_NONCE" ]]; then
  nonce_args=(--nonce "$INTENT_NONCE")
fi

if [[ "$FORCE" == "1" || ! -f "$WALLET_FILE" ]]; then
  "$PYTHON_BIN" -m darwin_sim.cli.darwinctl wallet-init \
    --deployment-file "$DEPLOYMENT_FILE" \
    --label "$WALLET_LABEL" \
    --out "$WALLET_FILE" >/dev/null
fi

"$PYTHON_BIN" -m darwin_sim.cli.darwinctl wallet-export-public \
  "$WALLET_FILE" \
  --out "$PUBLIC_FILE" >/dev/null

"$PYTHON_BIN" -m darwin_sim.cli.darwinctl intent-create \
  --wallet-file "$WALLET_FILE" \
  --deployment-file "$DEPLOYMENT_FILE" \
  --pair "$PAIR" \
  --side "$SIDE" \
  --qty "$QTY" \
  --price "$PRICE" \
  --slippage "$SLIPPAGE" \
  --profile "$PROFILE" \
  "${nonce_args[@]}" \
  --out "$INTENT_FILE" >/dev/null

"$PYTHON_BIN" -m darwin_sim.cli.darwinctl intent-verify \
  "$INTENT_FILE" \
  --deployment-file "$DEPLOYMENT_FILE" >/dev/null

echo "[demo-wallet] Ready"
echo "  label:           $WALLET_LABEL"
echo "  wallet_file:     $WALLET_FILE"
echo "  public_account:  $PUBLIC_FILE"
echo "  intent_file:     $INTENT_FILE"
echo "  passphrase_file: $PASSPHRASE_FILE"
echo "  deployment:      $DEPLOYMENT_FILE"
