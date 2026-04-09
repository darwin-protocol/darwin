#!/usr/bin/env python3
"""Export a lightweight public index of available DARWIN market lanes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--default-path", default="/market-config.json", help="Default market config path")
    parser.add_argument(
        "--config",
        action="append",
        default=[],
        help="Market config input as path=local/file.json. Repeat for multiple lanes.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def main() -> int:
    args = parse_args()
    lanes: list[dict] = []
    for item in args.config:
        if "=" not in item:
            raise SystemExit(f"invalid --config value: {item}")
        public_path, local_path = item.split("=", 1)
        config = load_json(Path(local_path).expanduser().resolve())
        lanes.append(
            {
                "path": public_path,
                "default": public_path == args.default_path,
                "slug": config["network"]["slug"],
                "name": config["network"]["name"],
                "network": config["network"],
                "token": {
                    "address": config["token"]["address"],
                    "symbol": config["token"]["symbol"],
                },
                "pool": {
                    "address": config["pool"]["address"],
                    "venue_id": config["pool"]["venue_id"],
                },
                "faucet": {
                    "enabled": bool(config.get("faucet", {}).get("enabled")),
                    "address": config.get("faucet", {}).get("address", ""),
                },
                "activity_summary_path": config.get("activity", {}).get("summary_path", "/activity-summary.json"),
                "community_share_path": config.get("community", {}).get("share_bundle_path", "/community-share.json"),
                "starter_cohort_path": config.get("community", {}).get("starter_cohort_path", "/join/"),
                "vnext": config.get("vnext", {"enabled": False}),
                "reward_claims": config.get("reward_claims", {"enabled": False}),
                "notes": config.get("notes", {}),
            }
        )

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"lanes": lanes}, indent=2, sort_keys=True) + "\n")
    print("[market-lanes] ready")
    print(f"  out:   {out_path}")
    print(f"  lanes: {len(lanes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
