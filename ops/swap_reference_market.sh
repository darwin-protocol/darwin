#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

if [[ -z "${DARWIN_RPC_URL:-}" && -n "${BASE_SEPOLIA_RPC_URL:-}" ]]; then
  DARWIN_RPC_URL="$BASE_SEPOLIA_RPC_URL"
fi
if [[ -z "${DARWIN_RPC_URL:-}" && -n "${ALCHEMY_API_KEY:-}" ]]; then
  DARWIN_RPC_URL="https://base-sepolia.g.alchemy.com/v2/$ALCHEMY_API_KEY"
fi

DARWIN_RPC_URL="${DARWIN_RPC_URL:-https://sepolia.base.org}"
DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia}"
DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.json}"
DARWIN_SWAP_SLIPPAGE_BPS="${DARWIN_SWAP_SLIPPAGE_BPS:-100}"

usage() {
  cat <<'EOF'
Usage:
  ./ops/swap_reference_market.sh --token-in base --amount 1 --dry-run
  ./ops/swap_reference_market.sh --token-in quote --amount 0.0001

Options:
  --token-in base|quote   Select DRW ("base") or WETH ("quote") as the input token
  --amount VALUE          Human-readable token amount using the token's decimals
  --recipient ADDRESS     Output recipient (defaults to deployer address)
  --slippage-bps N        Minimum-out slippage guard in basis points (default: 100)
  --dry-run               Quote only; do not approve or swap

Notes:
  - Uses the seeded market in ops/deployments/base-sepolia.json by default
  - Requires DARWIN_DEPLOYER_PRIVATE_KEY for a live swap
  - DARWIN_DEPLOYER_ADDRESS is enough for --dry-run
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

cast_uint_call() {
  cast call "$@" --rpc-url "$DARWIN_RPC_URL" | awk '{print $1}'
}

uint_lt() {
  python3 - "$1" "$2" <<'PY'
import sys
left = int(sys.argv[1])
right = int(sys.argv[2])
raise SystemExit(0 if left < right else 1)
PY
}

json_field() {
  python3 - "$DARWIN_DEPLOYMENT_FILE" "$1" <<'PY'
import json
import sys

data = json.loads(open(sys.argv[1]).read())
cursor = data
for part in sys.argv[2].split("."):
    cursor = cursor[part]
print(cursor)
PY
}

to_units() {
  python3 - "$1" "$2" <<'PY'
from decimal import Decimal, InvalidOperation, getcontext
import sys

getcontext().prec = 80
value = sys.argv[1]
decimals = int(sys.argv[2])
try:
    amount = Decimal(value)
except InvalidOperation as exc:
    raise SystemExit(f"invalid amount: {value}") from exc
scaled = amount * (Decimal(10) ** decimals)
if scaled != scaled.to_integral_value():
    raise SystemExit("amount exceeds token decimal precision")
print(int(scaled))
PY
}

from_units() {
  python3 - "$1" "$2" <<'PY'
from decimal import Decimal, getcontext
import sys

getcontext().prec = 80
value = Decimal(sys.argv[1])
decimals = int(sys.argv[2])
human = value / (Decimal(10) ** decimals)
print(f"{human:.18f}".rstrip("0").rstrip("."))
PY
}

TOKEN_IN_KIND=""
AMOUNT_RAW=""
RECIPIENT=""
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --token-in)
      TOKEN_IN_KIND="${2:-}"
      shift 2
      ;;
    --amount)
      AMOUNT_RAW="${2:-}"
      shift 2
      ;;
    --recipient)
      RECIPIENT="${2:-}"
      shift 2
      ;;
    --slippage-bps)
      DARWIN_SWAP_SLIPPAGE_BPS="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$TOKEN_IN_KIND" != "base" && "$TOKEN_IN_KIND" != "quote" ]]; then
  echo "--token-in must be 'base' or 'quote'" >&2
  exit 1
fi

if [[ -z "$AMOUNT_RAW" ]]; then
  echo "Missing --amount" >&2
  exit 1
fi

require_cmd cast
require_cmd python3

if [[ ! -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
  echo "Missing deployment artifact: $DARWIN_DEPLOYMENT_FILE" >&2
  exit 1
fi

if ! python3 - "$DARWIN_DEPLOYMENT_FILE" <<'PY' >/dev/null 2>&1
import json, sys
data = json.loads(open(sys.argv[1]).read())
market = data.get("market") or {}
raise SystemExit(0 if market.get("seeded") and (market.get("contracts") or {}).get("reference_pool") else 1)
PY
then
  echo "Deployment artifact does not contain a seeded reference market." >&2
  exit 1
fi

POOL_ADDRESS="$(json_field market.contracts.reference_pool)"
BASE_TOKEN="$(json_field market.base_token)"
QUOTE_TOKEN="$(json_field market.quote_token)"

if [[ -n "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" ]]; then
  DEPLOYER_ADDRESS="$(cast wallet address --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY")"
elif [[ -n "${DARWIN_DEPLOYER_ADDRESS:-}" ]]; then
  DEPLOYER_ADDRESS="$DARWIN_DEPLOYER_ADDRESS"
else
  echo "Missing deployer identity. Set DARWIN_DEPLOYER_PRIVATE_KEY or DARWIN_DEPLOYER_ADDRESS." >&2
  exit 1
fi

if [[ -z "$RECIPIENT" ]]; then
  RECIPIENT="$DEPLOYER_ADDRESS"
fi

if [[ "$TOKEN_IN_KIND" == "base" ]]; then
  TOKEN_IN="$BASE_TOKEN"
  TOKEN_OUT="$QUOTE_TOKEN"
else
  TOKEN_IN="$QUOTE_TOKEN"
  TOKEN_OUT="$BASE_TOKEN"
fi

CHAIN_ID="$(cast chain-id --rpc-url "$DARWIN_RPC_URL")"
if [[ "$CHAIN_ID" != "84532" ]]; then
  echo "Unexpected chain id: $CHAIN_ID (expected 84532 Base Sepolia)" >&2
  exit 1
fi

IN_DECIMALS="$(cast_uint_call "$TOKEN_IN" 'decimals()(uint8)')"
OUT_DECIMALS="$(cast_uint_call "$TOKEN_OUT" 'decimals()(uint8)')"
IN_SYMBOL="$(cast call "$TOKEN_IN" 'symbol()(string)' --rpc-url "$DARWIN_RPC_URL" | tr -d '"')"
OUT_SYMBOL="$(cast call "$TOKEN_OUT" 'symbol()(string)' --rpc-url "$DARWIN_RPC_URL" | tr -d '"')"

AMOUNT_IN="$(to_units "$AMOUNT_RAW" "$IN_DECIMALS")"
if [[ "$AMOUNT_IN" -le 0 ]]; then
  echo "Swap amount must be positive." >&2
  exit 1
fi

BALANCE_IN="$(cast_uint_call "$TOKEN_IN" 'balanceOf(address)(uint256)' "$DEPLOYER_ADDRESS")"
if uint_lt "$BALANCE_IN" "$AMOUNT_IN"; then
  echo "Insufficient token balance for swap." >&2
  echo "  token_in:   $IN_SYMBOL" >&2
  echo "  balance:    $(from_units "$BALANCE_IN" "$IN_DECIMALS")" >&2
  echo "  requested:  $(from_units "$AMOUNT_IN" "$IN_DECIMALS")" >&2
  exit 1
fi

ALLOWANCE="$(cast_uint_call "$TOKEN_IN" 'allowance(address,address)(uint256)' "$DEPLOYER_ADDRESS" "$POOL_ADDRESS")"
QUOTE_OUT="$(cast_uint_call "$POOL_ADDRESS" 'quoteExactInput(address,uint256)(uint256)' "$TOKEN_IN" "$AMOUNT_IN")"
MIN_OUT="$(python3 - "$QUOTE_OUT" "$DARWIN_SWAP_SLIPPAGE_BPS" <<'PY'
import sys

quoted = int(sys.argv[1])
slippage = int(sys.argv[2])
if slippage < 0 or slippage >= 10_000:
    raise SystemExit("slippage-bps must be between 0 and 9999")
print((quoted * (10_000 - slippage)) // 10_000)
PY
)"

echo "DARWIN reference market swap"
echo "  network:            $DARWIN_NETWORK"
echo "  pool:               $POOL_ADDRESS"
echo "  token_in_kind:      $TOKEN_IN_KIND"
echo "  token_in_symbol:    $IN_SYMBOL"
echo "  token_out_symbol:   $OUT_SYMBOL"
echo "  amount_in:          $(from_units "$AMOUNT_IN" "$IN_DECIMALS")"
echo "  quoted_out:         $(from_units "$QUOTE_OUT" "$OUT_DECIMALS")"
echo "  min_out:            $(from_units "$MIN_OUT" "$OUT_DECIMALS")"
echo "  current_allowance:  $(from_units "$ALLOWANCE" "$IN_DECIMALS")"
echo "  recipient:          $RECIPIENT"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "  dry_run:            yes"
  exit 0
fi

if [[ -z "${DARWIN_DEPLOYER_PRIVATE_KEY:-}" ]]; then
  echo "DARWIN_DEPLOYER_PRIVATE_KEY is required for a live swap." >&2
  exit 1
fi

if uint_lt "$ALLOWANCE" "$AMOUNT_IN"; then
  cast send "$TOKEN_IN" 'approve(address,uint256)' "$POOL_ADDRESS" "$AMOUNT_IN" \
    --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY" \
    --rpc-url "$DARWIN_RPC_URL" >/dev/null
fi

cast send "$POOL_ADDRESS" 'swapExactInput(address,uint256,uint256,address)' "$TOKEN_IN" "$AMOUNT_IN" "$MIN_OUT" "$RECIPIENT" \
  --private-key "$DARWIN_DEPLOYER_PRIVATE_KEY" \
  --rpc-url "$DARWIN_RPC_URL"
