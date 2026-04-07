#!/usr/bin/env python3
"""Build a local-only allowlist of project-controlled wallets for activity classification."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = Path.home() / ".config" / "darwin" / "project-wallets.json"
DEFAULT_PRIVATE_DEPLOYMENTS = Path.home() / ".config" / "darwin" / "deployments"
DEFAULT_WALLET_DIR = REPO_ROOT / "ops" / "wallets"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet-dir", default=str(DEFAULT_WALLET_DIR))
    parser.add_argument("--private-deployments-dir", default=str(DEFAULT_PRIVATE_DEPLOYMENTS))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    return parser.parse_args()


def normalize_address(value: str) -> str:
    value = value.lower()
    if not value.startswith("0x"):
        value = "0x" + value
    if len(value) != 42:
        raise ValueError(f"invalid address: {value}")
    return value


def collect_addresses(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for value in node.values():
            found.update(collect_addresses(value))
    elif isinstance(node, list):
        for value in node:
            found.update(collect_addresses(value))
    elif isinstance(node, str) and node.startswith("0x") and len(node) == 42:
        found.add(normalize_address(node))
    return found


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def collect_wallet_bundle_addresses(wallet_dir: Path) -> set[str]:
    found: set[str] = set()
    if not wallet_dir.exists():
        return found
    for path in wallet_dir.glob("*.account.json"):
        try:
            data = load_json(path)
        except json.JSONDecodeError:
            continue
        address = data.get("evm_addr")
        if isinstance(address, str) and address.startswith("0x") and len(address) == 42:
            found.add(normalize_address(address))
    return found


def collect_private_overlay_addresses(private_deployments_dir: Path) -> set[str]:
    found: set[str] = set()
    if not private_deployments_dir.exists():
        return found
    for path in private_deployments_dir.glob("*.json"):
        try:
            found.update(collect_addresses(load_json(path)))
        except json.JSONDecodeError:
            continue
    return found


def main() -> int:
    args = parse_args()
    wallet_dir = Path(args.wallet_dir).expanduser().resolve()
    private_dir = Path(args.private_deployments_dir).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    wallets = sorted(collect_wallet_bundle_addresses(wallet_dir) | collect_private_overlay_addresses(private_dir))
    payload = {
        "generated_at": utc_now(),
        "wallets": wallets,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[darwin-activity] wrote {out_path}")
    print(f"  wallets: {len(wallets)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
