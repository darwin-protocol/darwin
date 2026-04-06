#!/usr/bin/env python3
"""Export a static market-portal config from a pinned deployment artifact."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


NETWORK_DEFAULTS = {
    84532: {
        "network_name": "Base Sepolia",
        "chain_hex": "0x14a34",
        "rpc_url": "https://sepolia.base.org",
        "explorer_base_url": "https://sepolia-explorer.base.org",
    },
    8453: {
        "network_name": "Base",
        "chain_hex": "0x2105",
        "rpc_url": "https://mainnet.base.org",
        "explorer_base_url": "https://basescan.org",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment-file",
        default=str(REPO_ROOT / "ops" / "deployments" / "base-sepolia.json"),
        help="Deployment artifact to read",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "site" / "market-config.json"),
        help="Static portal config output path",
    )
    parser.add_argument(
        "--repo-url",
        default="https://github.com/darwin-protocol/darwin",
        help="Public repository URL",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    args = parse_args()
    deployment_path = Path(args.deployment_file).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    deployment = load_json(deployment_path)
    market = deployment.get("market") or {}
    contracts = deployment.get("contracts") or {}
    roles = deployment.get("roles") or {}
    drw = deployment.get("drw") or {}

    if not market.get("enabled"):
        raise SystemExit("deployment artifact does not enable market mode")
    if not market.get("seeded"):
        raise SystemExit("deployment artifact market is not seeded")
    if not (market.get("contracts") or {}).get("reference_pool"):
        raise SystemExit("deployment artifact does not include a reference pool")

    chain_id = int(deployment["chain_id"])
    network_defaults = NETWORK_DEFAULTS.get(chain_id)
    if network_defaults is None:
        raise SystemExit(f"unsupported chain id for portal export: {chain_id}")

    config = {
        "generated_at": utc_now(),
        "source": {
            "repo_url": args.repo_url,
            "deployment_file": str(deployment_path.relative_to(REPO_ROOT)),
        },
        "project": {
            "name": "DARWIN",
            "tagline": "Trade DRW on the Base Sepolia reference pool",
        },
        "network": {
            "id": chain_id,
            "hex": network_defaults["chain_hex"],
            "slug": deployment["network"],
            "name": network_defaults["network_name"],
            "rpc_url": network_defaults["rpc_url"],
            "explorer_base_url": network_defaults["explorer_base_url"],
            "native_symbol": "ETH",
        },
        "token": {
            "address": contracts["drw_token"],
            "symbol": "DRW",
            "decimals": 18,
            "total_supply": str(drw.get("total_supply", "")),
        },
        "quote_token": {
            "address": market["quote_token"],
            "symbol": "WETH",
            "decimals": 18,
        },
        "pool": {
            "address": market["contracts"]["reference_pool"],
            "fee_bps": int(market["fee_bps"]),
            "venue_id": market["venue_id"],
            "venue_type": market["venue_type"],
            "initial_base_amount": str(market["initial_base_amount"]),
            "initial_quote_amount": str(market["initial_quote_amount"]),
        },
        "roles": {
            "governance": roles["governance"],
            "market_operator": market["market_operator"],
        },
        "links": {
            "repo": args.repo_url,
            "live_status": f"{args.repo_url}/blob/main/LIVE_STATUS.md",
            "market_bootstrap": f"{args.repo_url}/blob/main/docs/MARKET_BOOTSTRAP.md",
            "deployment_artifact": f"{args.repo_url}/blob/main/ops/deployments/{deployment_path.name}",
        },
        "notes": {
            "alpha_stage": True,
            "bond_asset_mode": deployment.get("bond_asset_mode", "external"),
            "bond_asset": contracts["bond_asset"],
            "market_seeded": True,
            "warning": "This is a DARWIN-owned Base Sepolia reference pool. It is live and tradeable, but it is still testnet alpha infrastructure.",
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    print(f"[market-portal] config exported")
    print(f"  deployment: {deployment_path}")
    print(f"  output:     {out_path}")
    print(f"  pool:       {config['pool']['address']}")
    print(f"  token:      {config['token']['address']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
