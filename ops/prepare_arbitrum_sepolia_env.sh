#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_DIR="${DARWIN_CONFIG_DIR:-$HOME/.config/darwin}"

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
GOV_WALLET_FILE="${DARWIN_FUTURE_GOVERNANCE_WALLET_FILE:-$WALLET_DIR/darwin-future-governance.wallet.json}"
DEPLOYER_WALLET_FILE="${DARWIN_FUTURE_DEPLOYER_WALLET_FILE:-$WALLET_DIR/darwin-future-deployer.wallet.json}"
GOV_PASSPHRASE_FILE="${DARWIN_FUTURE_GOVERNANCE_PASSPHRASE_FILE:-$WALLET_DIR/darwin-future-governance.passphrase}"
DEPLOYER_PASSPHRASE_FILE="${DARWIN_FUTURE_DEPLOYER_PASSPHRASE_FILE:-$WALLET_DIR/darwin-future-deployer.passphrase}"
OUT_ENV_FILE="${DARWIN_ARBITRUM_ENV_FILE:-$CONFIG_DIR/arbitrum-sepolia.env}"
DEPLOYMENT_FILE="${DARWIN_ARBITRUM_DEPLOYMENT_FILE:-$ROOT/ops/deployments/arbitrum-sepolia.json}"

for path in "$GOV_WALLET_FILE" "$DEPLOYER_WALLET_FILE" "$GOV_PASSPHRASE_FILE" "$DEPLOYER_PASSPHRASE_FILE"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
done

export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" - <<'PY' "$GOV_WALLET_FILE" "$GOV_PASSPHRASE_FILE" "$DEPLOYER_WALLET_FILE" "$DEPLOYER_PASSPHRASE_FILE" "$OUT_ENV_FILE" "$DEPLOYMENT_FILE"
import sys
from pathlib import Path

from darwin_sim.sdk.wallets import load_wallet

gov_wallet_file = Path(sys.argv[1])
gov_passphrase_file = Path(sys.argv[2])
deployer_wallet_file = Path(sys.argv[3])
deployer_passphrase_file = Path(sys.argv[4])
out_env_file = Path(sys.argv[5])
deployment_file = Path(sys.argv[6])

gov_wallet = load_wallet(gov_wallet_file, gov_passphrase_file.read_text().strip())
deployer_wallet = load_wallet(deployer_wallet_file, deployer_passphrase_file.read_text().strip())

gov_addr = gov_wallet.account.evm_addr
gov_sk = "0x" + gov_wallet.account.evm_sk.hex()
deployer_addr = deployer_wallet.account.evm_addr
deployer_sk = "0x" + deployer_wallet.account.evm_sk.hex()

lines = [
    "# DARWIN Arbitrum Sepolia env",
    "# Local-only file. Keep this out of git.",
    'export ARBITRUM_SEPOLIA_RPC_URL="https://sepolia-rollup.arbitrum.io/rpc"',
    'export SEPOLIA_RPC_URL="https://ethereum-sepolia-rpc.publicnode.com"',
    'export DARWIN_RPC_URL="https://sepolia-rollup.arbitrum.io/rpc"',
    'export DARWIN_NETWORK="arbitrum-sepolia"',
    'export DARWIN_EXPECT_CHAIN_ID="421614"',
    f'export DARWIN_DEPLOYMENT_FILE="{deployment_file}"',
    "",
    "# Fresh wallets",
    f'export DARWIN_DEPLOYER_ADDRESS="{deployer_addr}"',
    f'export DARWIN_DEPLOYER_PRIVATE_KEY="{deployer_sk}"',
    f'export DARWIN_GOVERNANCE="{gov_addr}"',
    f'export DARWIN_GOVERNANCE_PRIVATE_KEY="{gov_sk}"',
    f'export DARWIN_EPOCH_OPERATOR="{gov_addr}"',
    f'export DARWIN_SAFE_MODE_AUTHORITY="{gov_addr}"',
    "",
    "# Use a mock bond asset for the first Arbitrum Sepolia DARWIN core deployment.",
    'export DARWIN_DEPLOY_BOND_ASSET_MOCK="1"',
]

out_env_file.parent.mkdir(parents=True, exist_ok=True)
out_env_file.write_text("\n".join(lines) + "\n")
PY

chmod 600 "$OUT_ENV_FILE"

echo "[arbitrum-env] Ready"
echo "  env_file:          $OUT_ENV_FILE"
echo "  deployment_file:   $DEPLOYMENT_FILE"
echo "  network:           arbitrum-sepolia"
echo "  rpc_url:           https://sepolia-rollup.arbitrum.io/rpc"
