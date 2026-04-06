#!/usr/bin/env python3
"""Check whether a tracked venue supports the deployment network for DRW market bootstrap."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def render_markdown(report: dict) -> str:
    lines = [
        "# DARWIN Market Venue Preflight",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Venue: `{report['venue']['id']}`",
        f"- Network: `{report['deployment']['network']}` chain `{report['deployment']['chain_id']}`",
        f"- Artifact: `{report['deployment']['artifact']}`",
        f"- Ready: `{'yes' if report['ready'] else 'no'}`",
        "",
        "## Checks",
        "",
    ]

    for name, check in report["checks"].items():
        lines.append(f"- `{name}`: `{check['state']}` {check['detail']}")

    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- `{blocker}`" for blocker in report["blockers"])
    else:
        lines.append("- none")

    lines.extend(["", "## Notes", ""])
    if report["notes"]:
        lines.extend(f"- {note}" for note in report["notes"])
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check venue support for a DRW market bootstrap")
    parser.add_argument("--deployment-file", default=str(ROOT / "ops" / "deployments" / "base-sepolia.json"))
    parser.add_argument("--venue", default="uniswap_v4")
    parser.add_argument("--registry-file", default=str(ROOT / "ops" / "market_venues.json"))
    parser.add_argument("--json-out", default="")
    parser.add_argument("--markdown-out", default="")
    args = parser.parse_args()

    deployment_path = Path(args.deployment_file).expanduser().resolve()
    registry_path = Path(args.registry_file).expanduser().resolve()
    deployment = json.loads(deployment_path.read_text())
    registry = json.loads(registry_path.read_text())

    chain_id = int(deployment["chain_id"])
    venue_id = args.venue
    venue = (registry.get("venues") or {}).get(venue_id)

    blockers: list[str] = []
    notes: list[str] = []
    checks: dict[str, dict] = {}

    if not venue:
        blockers.append("unknown_venue")
        checks["venue_registry"] = {
            "state": "FAIL",
            "detail": f"venue={venue_id} not found in {registry_path}",
        }
        tracked_network = None
    else:
        checks["venue_registry"] = {
            "state": "OK",
            "detail": f"venue={venue_id} source={venue.get('source', '')}",
        }
        tracked_network = (venue.get("tracked_networks") or {}).get(str(chain_id))

    if venue and venue.get("artifact_backed"):
        market = deployment.get("market") or {}
        market_contracts = market.get("contracts") or {}
        market_enabled = bool(market.get("enabled"))
        market_seeded = bool(market.get("seeded"))
        market_matches = market.get("venue_id") == venue_id and bool(market_contracts.get("reference_pool"))
        if market_enabled and market_matches and market_seeded:
            checks["venue_support"] = {
                "state": "OK",
                "detail": f"artifact has seeded {venue_id} pool={market_contracts.get('reference_pool', '')}",
            }
            notes.append(f"artifact-backed pool: {market_contracts.get('reference_pool', '')}")
        else:
            blockers.append("venue_not_supported_or_unconfirmed")
            checks["venue_support"] = {
                "state": "FAIL",
                "detail": (
                    f"artifact-backed venue={venue_id} enabled={market_enabled} "
                    f"seeded={market_seeded} pool={market_contracts.get('reference_pool', '')}"
                ),
            }
            notes.extend(venue.get("notes") or [])
            if venue.get("source"):
                notes.append(f"source: {venue['source']}")
    elif tracked_network:
        checks["venue_support"] = {
            "state": "OK",
            "detail": f"venue={venue_id} supports chain={chain_id} network={tracked_network.get('network', '')}",
        }
        notes.append(f"tracked contracts: {', '.join(sorted((tracked_network.get('contracts') or {}).keys()))}")
    else:
        blockers.append("venue_not_supported_or_unconfirmed")
        if venue:
            tracked = ", ".join(sorted((venue.get("tracked_networks") or {}).keys())) or "none"
            checks["venue_support"] = {
                "state": "FAIL",
                "detail": f"venue={venue_id} has no tracked support for chain={chain_id}; tracked_chains={tracked}",
            }
            notes.extend(venue.get("notes") or [])
            if venue.get("source"):
                notes.append(f"source: {venue['source']}")
        else:
            checks["venue_support"] = {
                "state": "FAIL",
                "detail": f"venue={venue_id} is unavailable",
            }

    report = {
        "generated_at": utc_now(),
        "ready": not blockers,
        "deployment": {
            "network": deployment["network"],
            "chain_id": chain_id,
            "artifact": str(deployment_path),
        },
        "venue": {
            "id": venue_id,
            "label": (venue or {}).get("label", venue_id),
            "source": (venue or {}).get("source", ""),
            "tracked_network": tracked_network or {},
        },
        "checks": checks,
        "blockers": blockers,
        "notes": notes,
    }

    if args.json_out:
        Path(args.json_out).expanduser().resolve().write_text(json.dumps(report, indent=2) + "\n")
    if args.markdown_out:
        Path(args.markdown_out).expanduser().resolve().write_text(render_markdown(report))

    print("[market-venue] DARWIN")
    print(f"  Ready:         {'yes' if report['ready'] else 'no'}")
    print(f"  Venue:         {venue_id}")
    print(f"  Network:       {deployment['network']} chain={chain_id}")
    if venue and venue.get("source"):
        print(f"  Source:        {venue['source']}")
    print(f"  Blockers:      {'none' if not blockers else ' '.join(blockers)}")

    if blockers:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
