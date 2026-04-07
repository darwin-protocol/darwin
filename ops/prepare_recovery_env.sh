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

require_cmd "$PYTHON_BIN"

WALLET_DIR="${DARWIN_WALLET_DIR:-$ROOT/ops/wallets}"
GOV_WALLET_FILE="${DARWIN_FUTURE_GOVERNANCE_WALLET_FILE:-$WALLET_DIR/darwin-future-governance.wallet.json}"
DEPLOYER_WALLET_FILE="${DARWIN_FUTURE_DEPLOYER_WALLET_FILE:-$WALLET_DIR/darwin-future-deployer.wallet.json}"
GOV_PASSPHRASE_FILE="${DARWIN_FUTURE_GOVERNANCE_PASSPHRASE_FILE:-$WALLET_DIR/darwin-future-governance.passphrase}"
DEPLOYER_PASSPHRASE_FILE="${DARWIN_FUTURE_DEPLOYER_PASSPHRASE_FILE:-$WALLET_DIR/darwin-future-deployer.passphrase}"
SOURCE_DEPLOYMENT_FILE="${DARWIN_SOURCE_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
OUT_ENV_FILE="${DARWIN_RECOVERY_ENV_FILE:-$CONFIG_DIR/recovery.env}"
RECOVERY_DEPLOYMENT_FILE="${DARWIN_RECOVERY_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia-recovery.json}"

for path in "$GOV_WALLET_FILE" "$DEPLOYER_WALLET_FILE" "$GOV_PASSPHRASE_FILE" "$DEPLOYER_PASSPHRASE_FILE" "$SOURCE_DEPLOYMENT_FILE"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 1
  fi
done

export PYTHONPATH="$ROOT:$ROOT/sim${PYTHONPATH:+:$PYTHONPATH}"

"$PYTHON_BIN" - <<'PY' "$GOV_WALLET_FILE" "$GOV_PASSPHRASE_FILE" "$DEPLOYER_WALLET_FILE" "$DEPLOYER_PASSPHRASE_FILE" "$SOURCE_DEPLOYMENT_FILE" "$OUT_ENV_FILE" "$RECOVERY_DEPLOYMENT_FILE"
import json
import sys
from pathlib import Path

from darwin_sim.sdk.wallets import load_wallet

gov_wallet_file = Path(sys.argv[1])
gov_passphrase_file = Path(sys.argv[2])
deployer_wallet_file = Path(sys.argv[3])
deployer_passphrase_file = Path(sys.argv[4])
source_deployment_file = Path(sys.argv[5])
out_env_file = Path(sys.argv[6])
recovery_deployment_file = Path(sys.argv[7])

gov_passphrase = gov_passphrase_file.read_text().strip()
deployer_passphrase = deployer_passphrase_file.read_text().strip()
gov_wallet = load_wallet(gov_wallet_file, gov_passphrase)
deployer_wallet = load_wallet(deployer_wallet_file, deployer_passphrase)
deployment = json.loads(source_deployment_file.read_text())

bond_asset = deployment["contracts"]["bond_asset"]
network = deployment["network"]
recovery_network = f"{network}-recovery"
if recovery_deployment_file.stem.endswith("-recovery"):
    recovery_network = recovery_deployment_file.stem
chain_id = deployment["chain_id"]

gov_addr = gov_wallet.account.evm_addr
gov_sk = "0x" + gov_wallet.account.evm_sk.hex()
deployer_addr = deployer_wallet.account.evm_addr
deployer_sk = "0x" + deployer_wallet.account.evm_sk.hex()

lines = [
    "# DARWIN recovery env",
    "# Local-only file. Keep this out of git.",
    f'export DARWIN_RPC_URL="https://sepolia.base.org"',
    f'export DARWIN_NETWORK="{recovery_network}"',
    f'export DARWIN_EXPECT_CHAIN_ID="{chain_id}"',
    f'export DARWIN_SOURCE_DEPLOYMENT_FILE="{source_deployment_file}"',
    f'export DARWIN_DEPLOYMENT_FILE="{recovery_deployment_file}"',
    "",
    "# Fresh wallets",
    f'export DARWIN_DEPLOYER_ADDRESS="{deployer_addr}"',
    f'export DARWIN_DEPLOYER_PRIVATE_KEY="{deployer_sk}"',
    f'export DARWIN_GOVERNANCE="{gov_addr}"',
    f'export DARWIN_GOVERNANCE_PRIVATE_KEY="{gov_sk}"',
    f'export DARWIN_EPOCH_OPERATOR="{gov_addr}"',
    f'export DARWIN_SAFE_MODE_AUTHORITY="{gov_addr}"',
    "",
    "# Core DARWIN deploy",
    f'export DARWIN_BOND_ASSET="{bond_asset}"',
    "",
    "# Recovery deployment posture",
    'export DARWIN_RECOVERY_ENABLE_DRW="1"',
    'export DARWIN_RECOVERY_ENABLE_MARKET="1"',
    'export DARWIN_RECOVERY_ENABLE_MARKET_SEED="1"',
    'export DARWIN_RECOVERY_ENABLE_FAUCET="1"',
    "",
    "# DRW genesis defaults",
    'export DARWIN_DRW_TOTAL_SUPPLY="1000000000000000000000000000"',
    f'export DARWIN_DRW_TREASURY_RECIPIENT="{gov_addr}"',
    f'export DARWIN_DRW_INSURANCE_RECIPIENT="{gov_addr}"',
    f'export DARWIN_DRW_SPONSOR_REWARDS_RECIPIENT="{gov_addr}"',
    f'export DARWIN_DRW_COMMUNITY_RECIPIENT="{gov_addr}"',
    'export DARWIN_DRW_STAKING_DURATION="31536000"',
    "",
    "# Market bootstrap",
    f'export DARWIN_REFERENCE_MARKET_OPERATOR="{gov_addr}"',
    f'export DARWIN_REFERENCE_MARKET_SEEDER_PRIVATE_KEY="{gov_sk}"',
    'export DARWIN_REFERENCE_MARKET_BASE_AMOUNT="1000000000000000000000"',
    'export DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT="500000000000000"',
    'export DARWIN_WRAP_WETH_WEI="500000000000000"',
    f'export DARWIN_WRAP_ADDRESS="{gov_addr}"',
    f'export DARWIN_WRAP_PRIVATE_KEY="{gov_sk}"',
    "",
    "# Faucet funding",
    f'export DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY="{gov_sk}"',
    'export DARWIN_DRW_FAUCET_INITIAL_TOKEN_FUNDING="100000000000000000000000"',
    'export DARWIN_DRW_FAUCET_INITIAL_NATIVE_FUNDING="200000000000000"',
    "",
]

out_env_file.parent.mkdir(parents=True, exist_ok=True)
out_env_file.write_text("\n".join(lines) + "\n")
PY

chmod 600 "$OUT_ENV_FILE"

echo "[recovery-env] Ready"
echo "  env_file:         $OUT_ENV_FILE"
echo "  source_artifact:  $SOURCE_DEPLOYMENT_FILE"
echo "  recovery_artifact: $RECOVERY_DEPLOYMENT_FILE"
