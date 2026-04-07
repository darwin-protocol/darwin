#!/usr/bin/env python3
"""Export a public-safe community share bundle for outreach and landing pages."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


REPO_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--market-config",
        default=str(REPO_ROOT / "web" / "public" / "market-config.json"),
        help="Market config generated for the public portal",
    )
    parser.add_argument(
        "--activity-summary",
        default=str(REPO_ROOT / "web" / "public" / "activity-summary.json"),
        help="Public-safe community activity snapshot",
    )
    parser.add_argument(
        "--site-url",
        default="https://usedarwin.xyz",
        help="Public site root",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "web" / "public" / "community-share.json"),
        help="Output path",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def join_url(site_url: str, path: str, lane_slug: str) -> str:
    absolute = f"{site_url.rstrip('/')}/{path.lstrip('/')}"
    if not lane_slug or lane_slug == "base-sepolia-recovery":
        return absolute
    parsed = urlparse(absolute)
    query = dict(parse_qsl(parsed.query))
    query["lane"] = lane_slug
    return urlunparse(parsed._replace(query=urlencode(query)))


def main() -> int:
    args = parse_args()
    market_config = load_json(Path(args.market_config).expanduser().resolve())
    activity_summary = load_json(Path(args.activity_summary).expanduser().resolve())
    epoch = ((market_config.get("community") or {}).get("epoch")) or {}
    summary = activity_summary.get("summary") or {}
    network_name = ((market_config.get("network") or {}).get("name")) or "the current Darwin lane"
    lane_slug = ((market_config.get("network") or {}).get("slug")) or ""

    site_url = args.site_url.rstrip("/")
    tiny_swap_path = (market_config.get("community") or {}).get("tiny_swap_path", "/trade/?preset=tiny-sell")
    activity_path = (market_config.get("community") or {}).get("activity_path", "/activity/")
    epoch_path = (market_config.get("community") or {}).get("epoch_path", "/epoch/")

    tiny_swap_url = join_url(site_url, tiny_swap_path, lane_slug)
    activity_url = join_url(site_url, activity_path, lane_slug)
    epoch_url = join_url(site_url, epoch_path, lane_slug)

    external_wallets = int(summary.get("external_wallets", 0) or 0)
    external_swaps = int(summary.get("external_swaps", 0) or 0)
    total_events = int(summary.get("total_events", 0) or 0)
    wallet_target = int(((epoch.get("milestones") or {}).get("external_wallets_target")) or 0)
    swap_target = int(((epoch.get("milestones") or {}).get("external_swaps_target")) or 0)

    if external_wallets > 0:
        status_line = (
            f"{external_wallets} outside wallets and {external_swaps} outside swaps have appeared in the current Darwin window."
        )
        invite_short = (
            f"Join {external_wallets} outside wallets using Darwin on {network_name}. Start here: {tiny_swap_url}"
        )
    else:
        status_line = "No outside wallets have appeared in the current Darwin window yet."
        invite_short = f"Be one of the first outside wallets to try Darwin on {network_name}: {tiny_swap_url}"

    progress_line = (
        f"Epoch progress: {external_wallets}/{wallet_target or '?'} outside wallets, "
        f"{external_swaps}/{swap_target or '?'} outside swaps, {total_events} total Darwin events."
    )
    invite_long = " ".join(
        [
            epoch.get("summary", "Claim DRW, make one tiny swap, and share the public proof surface."),
            status_line,
            progress_line,
            f"Start at {epoch_url} or jump directly to the tiny swap: {tiny_swap_url}",
            f"Public proof: {activity_url}",
        ]
    )

    payload = {
        "generated_at": utc_now(),
        "site_url": site_url,
        "epoch": epoch,
        "stats": summary,
        "links": {
            "site": site_url,
            "epoch": epoch_url,
            "tiny_swap": tiny_swap_url,
            "activity": activity_url,
        },
        "messages": {
            "status_line": status_line,
            "progress_line": progress_line,
            "invite_short": invite_short,
            "invite_long": invite_long,
        },
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"[community-share] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
