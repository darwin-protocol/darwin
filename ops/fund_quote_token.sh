#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_darwin_network_env "$ROOT"

DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia}"
DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.json}"
DARWIN_RPC_URL="${DARWIN_RPC_URL:-}"

if [[ -z "$DARWIN_RPC_URL" ]]; then
  case "$DARWIN_NETWORK" in
    arbitrum-sepolia)
      DARWIN_RPC_URL="${ARBITRUM_SEPOLIA_RPC_URL:-https://sepolia-rollup.arbitrum.io/rpc}"
      ;;
    *)
      DARWIN_RPC_URL="${BASE_SEPOLIA_RPC_URL:-https://sepolia.base.org}"
      ;;
  esac
fi

usage() {
  cat <<'EOF'
Usage:
  ./ops/fund_quote_token.sh --amount-eth 0.0005
  ./ops/fund_quote_token.sh --amount-wei 500000000000000

Notes:
  - Uses the deployment artifact bond asset as the quote token
  - If bond_asset_mode=mock, calls mint(address,uint256)
  - Otherwise, calls deposit() with native ETH value
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

to_wei() {
  python3 - "$1" <<'PY'
from decimal import Decimal, getcontext, InvalidOperation
import sys
getcontext().prec = 60
try:
    value = Decimal(sys.argv[1])
except InvalidOperation as exc:
    raise SystemExit(f"invalid decimal amount: {sys.argv[1]}") from exc
wei = value * Decimal(10**18)
if wei != wei.to_integral_value():
    raise SystemExit("amount has more than 18 decimal places")
print(int(wei))
PY
}

read_field() {
  python3 "$ROOT/ops/read_deployment_field.py" --deployment-file "$DARWIN_DEPLOYMENT_FILE" "$1"
}

AMOUNT_WEI="${DARWIN_QUOTE_TOKEN_AMOUNT_WEI:-}"
AMOUNT_ETH=""
RECIPIENT="${DARWIN_QUOTE_TOKEN_RECIPIENT:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --amount-wei)
      AMOUNT_WEI="${2:-}"
      shift 2
      ;;
    --amount-eth)
      AMOUNT_ETH="${2:-}"
      shift 2
      ;;
    --recipient)
      RECIPIENT="${2:-}"
      shift 2
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

if [[ -n "$AMOUNT_WEI" && -n "$AMOUNT_ETH" ]]; then
  echo "Specify either --amount-wei or --amount-eth, not both." >&2
  exit 1
fi
if [[ -n "$AMOUNT_ETH" ]]; then
  AMOUNT_WEI="$(to_wei "$AMOUNT_ETH")"
fi
if [[ -z "$AMOUNT_WEI" ]]; then
  echo "Missing quote token amount." >&2
  exit 1
fi

require_cmd cast
require_cmd python3

FUNDER_PRIVATE_KEY="${DARWIN_QUOTE_TOKEN_FUNDER_PRIVATE_KEY:-${DARWIN_DEPLOYER_PRIVATE_KEY:-}}"
if [[ -z "$FUNDER_PRIVATE_KEY" ]]; then
  echo "Missing funder private key. Set DARWIN_QUOTE_TOKEN_FUNDER_PRIVATE_KEY or DARWIN_DEPLOYER_PRIVATE_KEY." >&2
  exit 1
fi

FUNDER_ADDRESS="$(cast wallet address --private-key "$FUNDER_PRIVATE_KEY")"
RECIPIENT="${RECIPIENT:-$FUNDER_ADDRESS}"
QUOTE_TOKEN="$(read_field contracts.bond_asset)"
BOND_ASSET_MODE="$(read_field bond_asset_mode)"

if [[ "$BOND_ASSET_MODE" == "mock" ]]; then
  cast send "$QUOTE_TOKEN" "mint(address,uint256)" "$RECIPIENT" "$AMOUNT_WEI" \
    --private-key "$FUNDER_PRIVATE_KEY" \
    --rpc-url "$DARWIN_RPC_URL" >/dev/null
  ACTION="mint"
else
  cast send "$QUOTE_TOKEN" "deposit()" \
    --value "$AMOUNT_WEI" \
    --private-key "$FUNDER_PRIVATE_KEY" \
    --rpc-url "$DARWIN_RPC_URL" >/dev/null
  ACTION="deposit"
fi

echo "DARWIN quote token funded."
echo "  deployment: $DARWIN_DEPLOYMENT_FILE"
echo "  token:      $QUOTE_TOKEN"
echo "  mode:       $BOND_ASSET_MODE"
echo "  action:     $ACTION"
echo "  recipient:  $RECIPIENT"
echo "  amount_wei: $AMOUNT_WEI"
