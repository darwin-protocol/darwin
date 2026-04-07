#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$ROOT/ops/load_env_defaults.sh"
load_base_sepolia_env "$ROOT"

if [[ -z "${BASE_SEPOLIA_RPC_URL:-}" && -n "${ALCHEMY_API_KEY:-}" ]]; then
  BASE_SEPOLIA_RPC_URL="https://base-sepolia.g.alchemy.com/v2/$ALCHEMY_API_KEY"
fi

DARWIN_RPC_URL="${DARWIN_RPC_URL:-${BASE_SEPOLIA_RPC_URL:-https://sepolia.base.org}}"
DARWIN_NETWORK="${DARWIN_NETWORK:-base-sepolia}"
DARWIN_DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/${DARWIN_NETWORK}.json}"
DARWIN_WRAP_GAS_RESERVE_WEI="${DARWIN_WRAP_GAS_RESERVE_WEI:-1000000000000000}" # 0.001 ETH

usage() {
  cat <<'EOF'
Usage:
  ./ops/wrap_base_sepolia_weth.sh --amount-eth 0.0005
  ./ops/wrap_base_sepolia_weth.sh --amount-wei 500000000000000
  ./ops/wrap_base_sepolia_weth.sh --dry-run --amount-eth 0.0005

Notes:
  - Loads .env.base-sepolia automatically unless DARWIN_ENV_FILE is set
  - Uses the deployment artifact bond asset as the WETH address by default
  - Accepts DARWIN_WRAP_PRIVATE_KEY / DARWIN_WRAP_ADDRESS for a dedicated wrapper wallet
  - Falls back to DARWIN_DEPLOYER_PRIVATE_KEY / DARWIN_DEPLOYER_ADDRESS if unset
EOF
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

to_eth() {
  python3 - "$1" <<'PY'
from decimal import Decimal, getcontext
import sys
getcontext().prec = 40
wei = Decimal(sys.argv[1])
eth = wei / Decimal(10**18)
print(f"{eth:.18f}".rstrip("0").rstrip("."))
PY
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

normalize_uint() {
  python3 - "$1" <<'PY'
import sys

value = sys.argv[1].strip()
if not value:
    raise SystemExit("missing uint value")

value = value.split()[0]
if value.startswith("0x"):
    print(int(value, 16))
else:
    print(int(value))
PY
}

read_artifact_field() {
  python3 - "$DARWIN_DEPLOYMENT_FILE" "$1" <<'PY'
import json
import sys

path = sys.argv[1]
field = sys.argv[2]
data = json.loads(open(path).read())
cursor = data
for part in field.split("."):
    cursor = cursor[part]
print(cursor)
PY
}

AMOUNT_WEI="${DARWIN_WRAP_WETH_WEI:-}"
AMOUNT_ETH=""
DRY_RUN=0

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

if [[ -n "$AMOUNT_WEI" && -n "$AMOUNT_ETH" ]]; then
  echo "Specify either --amount-wei or --amount-eth, not both." >&2
  exit 1
fi

if [[ -n "$AMOUNT_ETH" ]]; then
  AMOUNT_WEI="$(to_wei "$AMOUNT_ETH")"
fi

if [[ -z "$AMOUNT_WEI" ]]; then
  echo "Missing wrap amount. Use --amount-eth, --amount-wei, or DARWIN_WRAP_WETH_WEI." >&2
  usage >&2
  exit 1
fi

require_cmd cast
require_cmd python3

WRAP_PRIVATE_KEY="${DARWIN_WRAP_PRIVATE_KEY:-${DARWIN_DEPLOYER_PRIVATE_KEY:-}}"
WRAP_ADDRESS="${DARWIN_WRAP_ADDRESS:-}"

if [[ -n "$WRAP_PRIVATE_KEY" ]]; then
  DEPLOYER_ADDRESS="$(cast wallet address --private-key "$WRAP_PRIVATE_KEY")"
elif [[ -n "$WRAP_ADDRESS" ]]; then
  DEPLOYER_ADDRESS="$WRAP_ADDRESS"
elif [[ -n "${DARWIN_DEPLOYER_ADDRESS:-}" ]]; then
  DEPLOYER_ADDRESS="$DARWIN_DEPLOYER_ADDRESS"
else
  echo "Missing wrapper address. Set DARWIN_WRAP_PRIVATE_KEY, DARWIN_WRAP_ADDRESS, or DARWIN_DEPLOYER_ADDRESS." >&2
  exit 1
fi

if [[ -n "${DARWIN_WRAP_WETH_ADDRESS:-}" ]]; then
  WETH_ADDRESS="$DARWIN_WRAP_WETH_ADDRESS"
else
  if [[ ! -f "$DARWIN_DEPLOYMENT_FILE" ]]; then
    echo "Missing deployment artifact: $DARWIN_DEPLOYMENT_FILE" >&2
    exit 1
  fi
  WETH_ADDRESS="$(read_artifact_field contracts.bond_asset)"
fi

CHAIN_ID="$(cast chain-id --rpc-url "$DARWIN_RPC_URL")"
if [[ "$CHAIN_ID" != "84532" ]]; then
  echo "Unexpected chain id: $CHAIN_ID (expected 84532 Base Sepolia)" >&2
  exit 1
fi

BASE_BALANCE_WEI="$(normalize_uint "$(cast balance "$DEPLOYER_ADDRESS" --rpc-url "$DARWIN_RPC_URL")")"
WETH_BALANCE_BEFORE="$(normalize_uint "$(cast call "$WETH_ADDRESS" "balanceOf(address)(uint256)" "$DEPLOYER_ADDRESS" --rpc-url "$DARWIN_RPC_URL")")"

if [[ "$AMOUNT_WEI" -le 0 ]]; then
  echo "Wrap amount must be positive." >&2
  exit 1
fi

if [[ "$BASE_BALANCE_WEI" -lt $((AMOUNT_WEI + DARWIN_WRAP_GAS_RESERVE_WEI)) ]]; then
  echo "Insufficient Base Sepolia ETH for wrap amount plus gas reserve." >&2
  echo "  base_balance_eth: $(to_eth "$BASE_BALANCE_WEI")" >&2
  echo "  wrap_amount_eth:  $(to_eth "$AMOUNT_WEI")" >&2
  echo "  gas_reserve_eth:  $(to_eth "$DARWIN_WRAP_GAS_RESERVE_WEI")" >&2
  exit 1
fi

echo "DARWIN WETH wrap"
echo "  network:           $DARWIN_NETWORK"
echo "  rpc_url:           $DARWIN_RPC_URL"
echo "  chain_id:          $CHAIN_ID"
echo "  deployer_address:  $DEPLOYER_ADDRESS"
echo "  weth_address:      $WETH_ADDRESS"
echo "  wrap_amount_eth:   $(to_eth "$AMOUNT_WEI")"
echo "  gas_reserve_eth:   $(to_eth "$DARWIN_WRAP_GAS_RESERVE_WEI")"
echo "  base_balance_eth:  $(to_eth "$BASE_BALANCE_WEI")"
echo "  weth_before:       $(to_eth "$WETH_BALANCE_BEFORE")"

if [[ "$DRY_RUN" == "1" ]]; then
  echo "  dry_run:           yes"
  echo "  calldata:          0xd0e30db0"
  exit 0
fi

if [[ -z "$WRAP_PRIVATE_KEY" ]]; then
  echo "DARWIN_WRAP_PRIVATE_KEY or DARWIN_DEPLOYER_PRIVATE_KEY is required for a live wrap." >&2
  exit 1
fi

TX_OUTPUT="$(cast send "$WETH_ADDRESS" "deposit()" --value "$AMOUNT_WEI" --private-key "$WRAP_PRIVATE_KEY" --rpc-url "$DARWIN_RPC_URL")"
WETH_BALANCE_AFTER="$(normalize_uint "$(cast call "$WETH_ADDRESS" "balanceOf(address)(uint256)" "$DEPLOYER_ADDRESS" --rpc-url "$DARWIN_RPC_URL")")"
BASE_BALANCE_AFTER="$(normalize_uint "$(cast balance "$DEPLOYER_ADDRESS" --rpc-url "$DARWIN_RPC_URL")")"

echo "$TX_OUTPUT"
echo "  weth_after:        $(to_eth "$WETH_BALANCE_AFTER")"
echo "  base_after_eth:    $(to_eth "$BASE_BALANCE_AFTER")"
