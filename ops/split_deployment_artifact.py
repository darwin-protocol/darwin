#!/usr/bin/env python3
"""Split a merged deployment artifact into public and local-private files."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "sim"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM))

from darwin_sim.sdk.deployments import default_private_overlay_path, load_deployment_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment-file",
        default=str(ROOT / "ops" / "deployments" / "base-sepolia.json"),
        help="Source deployment artifact",
    )
    parser.add_argument(
        "--public-out",
        default="",
        help="Public output path (defaults to the source artifact path)",
    )
    parser.add_argument(
        "--private-out",
        default="",
        help="Local private overlay output path (defaults to ~/.config/darwin/deployments/<network>.private.json)",
    )
    return parser.parse_args()


def _drop_keys(mapping: dict, keys: tuple[str, ...]) -> dict:
    return {key: value for key, value in mapping.items() if key in keys and value not in ("", None)}


def _write_json(path: Path, payload: dict, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    if mode is not None:
        os.chmod(path, mode)


def _build_private_overlay(data: dict) -> dict:
    overlay: dict = {}
    if data.get("deployer"):
        overlay["deployer"] = data["deployer"]

    roles = data.get("roles") or {}
    if roles:
        overlay["roles"] = roles

    drw = data.get("drw") or {}
    allocations = drw.get("allocations") or {}
    recipient_fields = _drop_keys(
        allocations,
        (
            "treasury_recipient",
            "insurance_recipient",
            "sponsor_rewards_recipient",
            "staking_recipient",
            "community_recipient",
        ),
    )
    if recipient_fields:
        overlay.setdefault("drw", {})["allocations"] = recipient_fields

    faucet = data.get("faucet") or {}
    if faucet.get("governance"):
        overlay.setdefault("faucet", {})["governance"] = faucet["governance"]

    market = data.get("market") or {}
    market_private = _drop_keys(market, ("governance", "market_operator"))
    if market_private:
        overlay.setdefault("market", {}).update(market_private)

    return overlay


def _build_public_artifact(data: dict) -> dict:
    public = deepcopy(data)
    public.pop("deployer", None)
    public.pop("roles", None)

    drw = public.get("drw") or {}
    allocations = drw.get("allocations") or {}
    for key in (
        "treasury_recipient",
        "insurance_recipient",
        "sponsor_rewards_recipient",
        "staking_recipient",
        "community_recipient",
    ):
        allocations.pop(key, None)

    faucet = public.get("faucet") or {}
    faucet.pop("governance", None)

    market = public.get("market") or {}
    market.pop("governance", None)
    market.pop("market_operator", None)
    return public


def main() -> int:
    args = parse_args()
    deployment_path = Path(args.deployment_file).expanduser().resolve()
    public_out = Path(args.public_out).expanduser().resolve() if args.public_out else deployment_path
    private_out = (
        Path(args.private_out).expanduser().resolve()
        if args.private_out
        else default_private_overlay_path(deployment_path).resolve()
    )

    _, data, *_ = load_deployment_data(deployment_file=deployment_path)
    public_artifact = _build_public_artifact(data)
    private_overlay = _build_private_overlay(data)

    _write_json(public_out, public_artifact)
    if private_overlay:
        _write_json(private_out, private_overlay, mode=stat.S_IRUSR | stat.S_IWUSR)

    print("[deployment-split] ready")
    print(f"  source:      {deployment_path}")
    print(f"  public_out:  {public_out}")
    print(f"  private_out: {private_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
