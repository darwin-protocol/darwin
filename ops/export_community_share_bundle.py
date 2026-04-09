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


def reward_line(epoch: dict) -> str:
    reward_policy = epoch.get("reward_policy") or {}
    currency = reward_policy.get("currency_symbol", "DRW")
    snippets = []
    for rule in reward_policy.get("rules") or []:
        amount = rule.get("amount", 0)
        if not amount:
            continue
        snippets.append(f"{rule.get('label', 'reward')} {amount} {currency}")
    if not snippets:
        return ""
    return "Pilot rewards: " + ", ".join(snippets) + "."


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
    anti_abuse = activity_summary.get("anti_abuse") or {}
    network_name = ((market_config.get("network") or {}).get("name")) or "the current Darwin lane"
    lane_slug = ((market_config.get("network") or {}).get("slug")) or ""

    site_url = args.site_url.rstrip("/")
    tiny_swap_path = (market_config.get("community") or {}).get("tiny_swap_path", "/trade/?preset=tiny-sell")
    activity_path = (market_config.get("community") or {}).get("activity_path", "/activity/")
    epoch_path = (market_config.get("community") or {}).get("epoch_path", "/epoch/")
    starter_cohort_path = (market_config.get("community") or {}).get("starter_cohort_path", "/join/")

    tiny_swap_url = join_url(site_url, tiny_swap_path, lane_slug)
    activity_url = join_url(site_url, activity_path, lane_slug)
    epoch_url = join_url(site_url, epoch_path, lane_slug)
    starter_cohort_url = join_url(site_url, starter_cohort_path, lane_slug)

    external_wallets = int(summary.get("external_wallets", 0) or 0)
    external_swaps = int(summary.get("external_swaps", 0) or 0)
    eligible_wallets = int(summary.get("eligible_wallets", external_wallets) or 0)
    eligible_swaps = int(summary.get("eligible_swaps", external_swaps) or 0)
    claim_only_wallets = int(summary.get("claim_only_wallets", max(external_wallets - eligible_wallets, 0)) or 0)
    total_events = int(summary.get("total_events", 0) or 0)
    wallet_target = int(((epoch.get("milestones") or {}).get("external_wallets_target")) or 0)
    swap_target = int(((epoch.get("milestones") or {}).get("external_swaps_target")) or 0)
    reward_policy_line = reward_line(epoch)
    leaderboard = activity_summary.get("leaderboard") or {}
    leader = ((leaderboard.get("entries") or [])[:1] or [None])[0]
    eligibility_note = str(
        anti_abuse.get("note")
        or leaderboard.get("eligibility_note")
        or "Claim-only wallets stay visible in the raw outside-activity summary but do not unlock traction until they swap."
    )

    if eligible_wallets > 0:
        status_line = (
            f"{eligible_wallets} swap-active outside wallets and {eligible_swaps} outside swaps have appeared in the current Darwin window."
        )
        invite_short = (
            f"Join {eligible_wallets} swap-active outside wallets using Darwin on {network_name}. Start here: {tiny_swap_url}"
        )
    elif external_wallets > 0:
        status_line = "Outside wallets have claimed DRW, but no swap-active wallets have appeared in the current Darwin window yet."
        invite_short = f"Be the first swap-active wallet to try Darwin on {network_name}: {tiny_swap_url}"
    else:
        status_line = "No outside wallets have appeared in the current Darwin window yet."
        invite_short = f"Be one of the first outside wallets to try Darwin on {network_name}: {tiny_swap_url}"

    progress_line = (
        f"Epoch progress: {eligible_wallets}/{wallet_target or '?'} swap-active wallets, "
        f"{eligible_swaps}/{swap_target or '?'} outside swaps, {total_events} total Darwin events."
    )
    raw_visibility_line = (
        f"Raw outside activity still shows {external_wallets} wallets, including {claim_only_wallets} claim-only wallets."
        if claim_only_wallets > 0
        else ""
    )
    message_parts = [
        epoch.get("summary", "Claim DRW, make one tiny swap, and share the public proof surface."),
        reward_policy_line,
        status_line,
        progress_line,
        eligibility_note,
        raw_visibility_line,
    ]
    if leader:
        message_parts.append(
            f"Top outside wallet this window: {leader.get('actor', '')} with score {leader.get('points', 0)}."
        )
    message_parts.extend(
        [
            f"Starter cohort intake: {starter_cohort_url}",
            f"Start at {epoch_url} or jump directly to the tiny swap: {tiny_swap_url}",
            f"Public proof: {activity_url}",
        ]
    )
    invite_long = " ".join(part for part in message_parts if part)

    payload = {
        "generated_at": utc_now(),
        "site_url": site_url,
        "epoch": epoch,
        "stats": summary,
        "progress": activity_summary.get("progress") or {},
        "anti_abuse": anti_abuse,
        "leaderboard": leaderboard,
        "links": {
            "site": site_url,
            "epoch": epoch_url,
            "tiny_swap": tiny_swap_url,
            "activity": activity_url,
            "starter_cohort": starter_cohort_url,
        },
        "messages": {
            "status_line": status_line,
            "progress_line": progress_line,
            "reward_line": reward_policy_line,
            "eligibility_note": eligibility_note,
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
