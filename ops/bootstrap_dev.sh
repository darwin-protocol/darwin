#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e './sim[dev]'

if command -v forge >/dev/null 2>&1; then
  if [[ ! -f contracts/lib/forge-std/src/Test.sol ]]; then
    (
      cd contracts
      forge install --no-git --shallow foundry-rs/forge-std
    )
  fi
fi

cat <<'EOF'
Bootstrap complete.

Next steps:
  source .venv/bin/activate
  cd sim && python -m pytest tests/test_end_to_end.py -v
  cd ../contracts && forge test -vv
  cd .. && python overlay/devnet.py
EOF
