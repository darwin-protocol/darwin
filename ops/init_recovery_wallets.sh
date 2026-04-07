#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WALLET_DIR="${DARWIN_WALLET_DIR:-$ROOT/ops/wallets}"
DEPLOYMENT_FILE="${DARWIN_DEPLOYMENT_FILE:-$ROOT/ops/deployments/base-sepolia.json}"
SUMMARY_FILE="${DARWIN_RECOVERY_SUMMARY_FILE:-$WALLET_DIR/recovery-wallets-summary.md}"
PYTHON_BIN="${DARWIN_PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x "$ROOT/.venv/bin/python" ]]; then
    PYTHON_BIN="$ROOT/.venv/bin/python"
  else
    PYTHON_BIN="python3"
  fi
fi

mkdir -p "$WALLET_DIR"

DARWIN_OPERATOR_ROLE="future-governance" \
DARWIN_WALLET_LABEL="${DARWIN_FUTURE_GOVERNANCE_LABEL:-darwin-future-governance}" \
DARWIN_WALLET_DIR="$WALLET_DIR" \
DARWIN_DEPLOYMENT_FILE="$DEPLOYMENT_FILE" \
DARWIN_PYTHON_BIN="$PYTHON_BIN" \
bash "$ROOT/ops/init_operator_wallet.sh" >/dev/null

DARWIN_OPERATOR_ROLE="future-deployer" \
DARWIN_WALLET_LABEL="${DARWIN_FUTURE_DEPLOYER_LABEL:-darwin-future-deployer}" \
DARWIN_WALLET_DIR="$WALLET_DIR" \
DARWIN_DEPLOYMENT_FILE="$DEPLOYMENT_FILE" \
DARWIN_PYTHON_BIN="$PYTHON_BIN" \
bash "$ROOT/ops/init_operator_wallet.sh" >/dev/null

"$PYTHON_BIN" - <<'PY' "$WALLET_DIR" "$SUMMARY_FILE"
import json
import sys
from pathlib import Path

wallet_dir = Path(sys.argv[1])
summary_file = Path(sys.argv[2])

roles = [
    ("future-governance", wallet_dir / "darwin-future-governance.account.json"),
    ("future-deployer", wallet_dir / "darwin-future-deployer.account.json"),
]

lines = [
    "# DARWIN Recovery Wallets",
    "",
    "Fresh local wallets for future governance or deployment work.",
    "",
]

for role, path in roles:
    data = json.loads(path.read_text())
    share_path = Path(str(path).replace(".account.json", ".share.md"))
    lines.extend(
        [
            f"## {role}",
            "",
            f"- Address: `{data['evm_addr']}`",
            f"- Account ID: `{data['acct_id']}`",
            f"- Public file: `{path}`",
            f"- Share file: `{share_path}`",
            "",
        ]
    )

lines.extend(
    [
        "## Notes",
        "",
        "- Fund the future-deployer wallet with Base Sepolia ETH before any new deployment.",
        "- Keep the future-governance wallet offline until it is needed for a redeploy or migration.",
        "- These files are local-only and gitignored.",
        "",
    ]
)

summary_file.write_text("\n".join(lines))
PY

echo "[recovery-wallets] Ready"
echo "  wallet_dir:      $WALLET_DIR"
echo "  summary_file:    $SUMMARY_FILE"
echo "  governance:      $WALLET_DIR/darwin-future-governance.account.json"
echo "  deployer:        $WALLET_DIR/darwin-future-deployer.account.json"
