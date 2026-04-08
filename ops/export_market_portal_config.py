#!/usr/bin/env python3
"""Export a static market-portal config from a pinned deployment artifact."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMMUNITY_EPOCH_FILE = REPO_ROOT / "ops" / "community_epoch.json"
BUILDER_SUFFIX_ENCODER = REPO_ROOT / "web" / "scripts" / "encode_builder_code_suffix.mjs"
NETWORK_ENV_PREFIXES = {
    "base-sepolia-recovery": ("DARWIN_BASE", "DARWIN_BASE_SEPOLIA", "DARWIN_BASE_SEPOLIA_RECOVERY"),
    "base-sepolia": ("DARWIN_BASE", "DARWIN_BASE_SEPOLIA"),
    "base": ("DARWIN_BASE",),
    "arbitrum-sepolia": ("DARWIN_ARBITRUM", "DARWIN_ARBITRUM_SEPOLIA"),
    "arbitrum": ("DARWIN_ARBITRUM",),
}


NETWORK_DEFAULTS = {
    84532: {
        "network_name": "Base Sepolia",
        "chain_hex": "0x14a34",
        "rpc_url": "https://sepolia.base.org",
        "read_rpc_url": "https://sepolia-preconf.base.org",
        "explorer_base_url": "https://sepolia-explorer.base.org",
    },
    8453: {
        "network_name": "Base",
        "chain_hex": "0x2105",
        "rpc_url": "https://mainnet.base.org",
        "read_rpc_url": "https://mainnet-preconf.base.org",
        "explorer_base_url": "https://basescan.org",
    },
    421614: {
        "network_name": "Arbitrum Sepolia",
        "chain_hex": "0x66eee",
        "rpc_url": "https://sepolia-rollup.arbitrum.io/rpc",
        "read_rpc_url": "https://sepolia-rollup.arbitrum.io/rpc",
        "explorer_base_url": "https://sepolia.arbiscan.io",
    },
    42161: {
        "network_name": "Arbitrum",
        "chain_hex": "0xa4b1",
        "rpc_url": "https://arb1.arbitrum.io/rpc",
        "read_rpc_url": "https://arb1.arbitrum.io/rpc",
        "explorer_base_url": "https://arbiscan.io",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment-file",
        default=str(REPO_ROOT / "ops" / "deployments" / "base-sepolia-recovery.json"),
        help="Deployment artifact to read",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "web" / "public" / "market-config.json"),
        help="Static portal config output path",
    )
    parser.add_argument(
        "--repo-url",
        default="https://github.com/darwin-protocol/darwin",
        help="Public repository URL",
    )
    parser.add_argument(
        "--community-epoch-file",
        default=str(DEFAULT_COMMUNITY_EPOCH_FILE),
        help="Public community epoch config",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json(path)


def compute_builder_code_suffix(builder_code: str) -> str:
    if not builder_code:
        return ""
    result = subprocess.run(
        ["node", str(BUILDER_SUFFIX_ENCODER), builder_code],
        cwd=str(REPO_ROOT / "web"),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "failed to encode builder code")
    return result.stdout.strip()


def attribution_env(network_slug: str, suffix: str) -> str:
    candidates = [f"{prefix}_{suffix}" for prefix in NETWORK_ENV_PREFIXES.get(network_slug, ())]
    candidates.append(f"DARWIN_{suffix}")
    for name in candidates:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def repo_relative_or_absolute(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    deployment_path = Path(args.deployment_file).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    community_epoch_path = Path(args.community_epoch_file).expanduser().resolve()

    deployment = load_json(deployment_path)
    market = deployment.get("market") or {}
    contracts = deployment.get("contracts") or {}
    drw = deployment.get("drw") or {}
    faucet = deployment.get("faucet") or {}
    vnext_path = deployment_path.with_suffix(".vnext.json")
    vnext = load_json(vnext_path) if vnext_path.exists() else {}
    community_epoch = load_optional_json(community_epoch_path)

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
    network_slug = str(deployment["network"])
    is_default_lane = network_slug == "base-sepolia-recovery"
    activity_summary_path = (
        "/activity-summary.json"
        if is_default_lane
        else f"/activity-summary-{network_slug}.json"
    )
    community_share_path = (
        "/community-share.json"
        if is_default_lane
        else f"/community-share-{network_slug}.json"
    )
    wrap_enabled = deployment.get("bond_asset_mode", "external") != "mock"
    milestones = community_epoch.get("milestones") or {}
    external_wallets_target = int(milestones.get("external_wallets_target", 25) or 25)
    external_swaps_target = int(milestones.get("external_swaps_target", 40) or 40)
    builder_code = attribution_env(network_slug, "BUILDER_CODE")
    builder_code_suffix = attribution_env(network_slug, "BUILDER_CODE_SUFFIX")
    if builder_code and not builder_code_suffix:
        builder_code_suffix = compute_builder_code_suffix(builder_code)
    if builder_code_suffix and not builder_code_suffix.startswith("0x"):
        raise SystemExit("DARWIN_BUILDER_CODE_SUFFIX must be a 0x-prefixed hex string")
    paymaster_service_url = attribution_env(network_slug, "PAYMASTER_SERVICE_URL")
    starter_cohort_amount = os.environ.get(
        "DARWIN_STARTER_COHORT_AMOUNT",
        str(faucet.get("claim_amount", "") or "100000000000000000000"),
    ).strip()

    config = {
        "generated_at": utc_now(),
        "source": {
            "repo_url": args.repo_url,
            "deployment_file": repo_relative_or_absolute(deployment_path),
        },
        "project": {
            "name": "DARWIN",
            "tagline": f"Trade DRW on the {network_defaults['network_name']} DARWIN reference pool",
        },
        "network": {
            "id": chain_id,
            "chain_id": chain_id,
            "hex": network_defaults["chain_hex"],
            "slug": network_slug,
            "name": network_defaults["network_name"],
            "rpc_url": network_defaults["rpc_url"],
            "read_rpc_url": network_defaults["read_rpc_url"],
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
            "wrap_enabled": wrap_enabled,
        },
        "pool": {
            "address": market["contracts"]["reference_pool"],
            "fee_bps": int(market["fee_bps"]),
            "venue_id": market["venue_id"],
            "venue_type": market["venue_type"],
            "initial_base_amount": str(market["initial_base_amount"]),
            "initial_quote_amount": str(market["initial_quote_amount"]),
        },
        "faucet": {
            "enabled": bool(faucet.get("enabled")),
            "address": str((faucet.get("contracts") or {}).get("drw_faucet", "")),
            "claim_amount": str(faucet.get("claim_amount", "")),
            "native_drip_amount": str(faucet.get("native_drip_amount", "")),
            "claim_cooldown": int(faucet.get("claim_cooldown", 0) or 0),
            "funded": bool(faucet.get("funded", False)),
            "initial_token_funding": str(faucet.get("initial_token_funding", "")),
            "initial_native_funding": str(faucet.get("initial_native_funding", "")),
        },
        "links": {
            "repo": args.repo_url,
            "live_status": f"{args.repo_url}/blob/main/LIVE_STATUS.md",
            "market_bootstrap": f"{args.repo_url}/blob/main/docs/MARKET_BOOTSTRAP.md",
            "community_bootstrap": f"{args.repo_url}/blob/main/docs/COMMUNITY_BOOTSTRAP.md",
        },
        "activity": {
            "lookback_blocks": 50_000,
            "summary_path": activity_summary_path,
        },
        "community": {
            "tiny_swap_path": "/trade/?preset=tiny-sell",
            "activity_path": "/activity/",
            "epoch_path": "/epoch/",
            "starter_cohort_path": "/join/",
            "starter_cohort_amount": starter_cohort_amount,
            "share_bundle_path": community_share_path,
            "share_text": "Claim DRW, make one tiny swap, and share the Darwin activity page.",
        },
        "attribution": {
            "mode": "builder-code" if builder_code_suffix else "direct",
            "builder_code": builder_code,
            "builder_code_suffix": builder_code_suffix,
            "wallet_send_calls_enabled": True,
            "smart_start_enabled": bool(faucet.get("enabled")),
        },
        "market_structure": {
            "strategy": "single_canonical_until_traction",
            "summary": (
                "Keep one canonical pool per Darwin lane until outside usage is real. "
                "Only open experimental or incentivized routes after the canonical pool "
                "proves outside demand."
            ),
            "default_entry": "canonical",
            "progress_targets": {
                "external_wallets_target": external_wallets_target,
                "external_swaps_target": external_swaps_target,
            },
            "pools": [
                {
                    "id": "canonical",
                    "label": "Canonical",
                    "status": "live",
                    "enabled": True,
                    "purpose": (
                        "Default DRW price-discovery and onboarding surface for claimants, "
                        "tiny swaps, and public proof."
                    ),
                    "entry_label": "Open canonical pool",
                    "entry_path": "/trade/?preset=tiny-sell",
                    "pool_address": market["contracts"]["reference_pool"],
                    "reason": (
                        "Live and seeded on the selected lane. This is the only pool "
                        "the public portal should route to by default."
                    ),
                },
                {
                    "id": "experimental",
                    "label": "Experimental",
                    "status": "locked",
                    "enabled": False,
                    "purpose": (
                        "Future alternate quote assets, descendant Darwin experiments, "
                        "or other opt-in market tests."
                    ),
                    "unlock_rule": {
                        "external_wallets_target": external_wallets_target,
                        "external_swaps_target": external_swaps_target,
                    },
                    "reason": (
                        "Locked to avoid fragmenting thin alpha liquidity before the "
                        "canonical route has genuine outside usage."
                    ),
                },
                {
                    "id": "incentivized",
                    "label": "Incentivized",
                    "status": "locked",
                    "enabled": False,
                    "purpose": (
                        "Future liquidity incentives or epoch emissions for traders and LPs "
                        "after real outside demand appears."
                    ),
                    "unlock_rule": {
                        "external_wallets_target": external_wallets_target,
                        "external_swaps_target": external_swaps_target,
                    },
                    "reason": (
                        "Locked until the canonical route has real outside wallets and "
                        "real outside swaps."
                    ),
                },
            ],
        },
        "notes": {
            "alpha_stage": True,
            "bond_asset_mode": deployment.get("bond_asset_mode", "external"),
            "bond_asset": contracts["bond_asset"],
            "market_seeded": True,
            "wrap_supported": wrap_enabled,
            "warning": f"This is a DARWIN-owned {network_defaults['network_name']} reference pool. It is live and tradeable, but it is still alpha infrastructure.",
        },
    }
    if paymaster_service_url:
        config["attribution"]["paymaster_service_url"] = paymaster_service_url

    vnext_contracts = ((vnext.get("vnext") or {}).get("contracts") or {})
    if vnext_contracts.get("drw_merkle_distributor"):
        config["vnext"] = {
            "enabled": bool((vnext.get("vnext") or {}).get("enabled", False)),
            "distributor": vnext_contracts["drw_merkle_distributor"],
            "timelock": vnext_contracts.get("darwin_timelock", ""),
        }

    if community_epoch:
        config["community"]["epoch"] = community_epoch

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
