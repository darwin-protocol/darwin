#!/usr/bin/env python3
"""Export a public-safe Base.dev registration summary for the Darwin portal."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site-url", default="https://usedarwin.xyz", help="Public site root")
    parser.add_argument(
        "--repo-url",
        default="https://github.com/darwin-protocol/darwin",
        help="Public repository URL",
    )
    parser.add_argument(
        "--lane-index",
        default=str(REPO_ROOT / "web" / "public" / "market-lanes.json"),
        help="Public lane index JSON path",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "ops" / "state" / "base-app-registration.json"),
        help="Output JSON path",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def join_url(site_url: str, path: str) -> str:
    return f"{site_url.rstrip('/')}/{path.lstrip('/')}"


def main() -> int:
    args = parse_args()
    site_url = args.site_url.rstrip("/")
    lane_index = load_json(Path(args.lane_index).expanduser().resolve())
    lanes = lane_index.get("lanes") or []

    payload = {
        "generated_at": utc_now(),
        "app": {
            "name": "Use Darwin",
            "description": "Claim testnet DRW and start with a tiny first swap on the live DARWIN reference pools.",
            "site_url": site_url,
            "manifest_url": join_url(site_url, "/manifest.webmanifest"),
            "icon_url": join_url(site_url, "/icon.svg"),
            "social_image_url": join_url(site_url, "/og-card.png"),
            "primary_routes": {
                "home": join_url(site_url, "/"),
                "join": join_url(site_url, "/join/"),
                "trade": join_url(site_url, "/trade/?preset=tiny-sell"),
                "activity": join_url(site_url, "/activity/"),
                "epoch": join_url(site_url, "/epoch/"),
            },
            "categories": ["finance", "utilities"],
        },
        "repo": {
            "url": args.repo_url,
            "community_bootstrap": f"{args.repo_url}/blob/main/docs/COMMUNITY_BOOTSTRAP.md",
            "starter_cohort": f"{args.repo_url}/blob/main/docs/STARTER_COHORT.md",
        },
        "lanes": [
            {
                "slug": lane.get("slug", ""),
                "name": lane.get("name", ""),
                "token": (lane.get("token") or {}).get("symbol", "DRW"),
                "default": bool(lane.get("default", False)),
            }
            for lane in lanes
        ],
        "builder_code_env": {
            "base_app_id": "DARWIN_BASE_APP_ID",
            "base": "DARWIN_BASE_BUILDER_CODE",
            "arbitrum": "DARWIN_ARBITRUM_BUILDER_CODE",
            "base_paymaster": "DARWIN_BASE_PAYMASTER_SERVICE_URL",
            "arbitrum_paymaster": "DARWIN_ARBITRUM_PAYMASTER_SERVICE_URL",
            "site_env_file": "~/.config/darwin/site.env",
        },
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("[base-app-registration] ready")
    print(f"  out:   {out_path}")
    print(f"  lanes: {len(payload['lanes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
