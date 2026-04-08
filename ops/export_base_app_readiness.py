#!/usr/bin/env python3
"""Export a public-safe Base App readiness report for the Darwin portal."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--market-config",
        default=str(REPO_ROOT / "web" / "public" / "market-config.json"),
        help="Local market config JSON path",
    )
    parser.add_argument(
        "--farcaster-manifest",
        default=str(REPO_ROOT / "web" / "public" / ".well-known" / "farcaster.json"),
        help="Local Farcaster/Base app manifest path",
    )
    parser.add_argument(
        "--layout-source",
        default=str(REPO_ROOT / "web" / "app" / "layout.js"),
        help="Root layout source path",
    )
    parser.add_argument(
        "--trade-source",
        default=str(REPO_ROOT / "web" / "public" / "trade.js"),
        help="Trade client source path",
    )
    parser.add_argument(
        "--join-source",
        default=str(REPO_ROOT / "web" / "public" / "join.js"),
        help="Join client source path",
    )
    parser.add_argument(
        "--site-url",
        default="https://usedarwin.xyz",
        help="Public site root",
    )
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "web" / "public" / "base-app-readiness.json"),
        help="Output JSON path",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def has_signed_account_association(manifest: dict) -> bool:
    association = manifest.get("accountAssociation") or {}
    return all(bool(str(association.get(field, "")).strip()) for field in ("header", "payload", "signature"))


def has_required_manifest_fields(manifest: dict) -> bool:
    miniapp = manifest.get("miniapp") or {}
    required = (
        "version",
        "name",
        "iconUrl",
        "homeUrl",
        "splashImageUrl",
        "splashBackgroundColor",
        "primaryCategory",
        "tags",
    )
    return all(bool(miniapp.get(field)) for field in required)


def provider_prefers_base(source: str) -> bool:
    normalized = source.lower()
    return any(
        needle in normalized
        for needle in (
            "isbaseaccount",
            "iscoinbasewallet",
            "coinbase",
            'rdns.includes("base")',
            "name.includes(\"base\")",
        )
    )


def main() -> int:
    args = parse_args()
    market_config = load_json(Path(args.market_config).expanduser().resolve())
    manifest = load_json(Path(args.farcaster_manifest).expanduser().resolve())
    layout_source = Path(args.layout_source).expanduser().resolve().read_text()
    trade_source = Path(args.trade_source).expanduser().resolve().read_text()
    join_source = Path(args.join_source).expanduser().resolve().read_text()

    checks = {
        "builder_code_mode": market_config.get("attribution", {}).get("mode") == "builder-code",
        "builder_code_present": bool(market_config.get("attribution", {}).get("builder_code")),
        "base_app_id_support": '"base:app_id"' in layout_source or "base:app_id" in layout_source,
        "base_app_id_configured": bool(os.environ.get("DARWIN_BASE_APP_ID", "").strip()),
        "manifest_required_fields": has_required_manifest_fields(manifest),
        "account_association_signed": has_signed_account_association(manifest),
        "provider_priority_trade": provider_prefers_base(trade_source),
        "provider_priority_join": provider_prefers_base(join_source),
        "screenshot_count": len((manifest.get("miniapp") or {}).get("screenshotUrls") or []),
    }

    blockers = []
    if not checks["builder_code_mode"]:
        blockers.append("market_config_not_in_builder_code_mode")
    if not checks["builder_code_present"]:
        blockers.append("builder_code_missing")
    if not checks["base_app_id_support"]:
        blockers.append("base_app_id_meta_not_supported_in_layout")
    if not checks["base_app_id_configured"]:
        blockers.append("base_app_id_not_configured")
    if not checks["manifest_required_fields"]:
        blockers.append("farcaster_manifest_missing_required_fields")
    if not checks["account_association_signed"]:
        blockers.append("account_association_unsigned")
    if not checks["provider_priority_trade"]:
        blockers.append("trade_provider_discovery_not_base_first")
    if not checks["provider_priority_join"]:
        blockers.append("join_provider_discovery_not_base_first")
    if checks["screenshot_count"] < 3:
        blockers.append("fewer_than_three_base_app_screenshots")

    payload = {
        "generated_at": utc_now(),
        "site_url": args.site_url.rstrip("/"),
        "status": {
            "standard_web_ready": not blockers,
            "preview_validation_ready": checks["manifest_required_fields"] and checks["account_association_signed"],
        },
        "checks": checks,
        "blockers": blockers,
        "attribution": market_config.get("attribution", {}),
        "recommended_next_steps": [
            "Keep using the live Builder Code path for Base attribution.",
            "Use the preview tool to confirm metadata and account-association validity after each publish.",
            "Treat any remaining Base.dev mini-app import failure as an upstream or account-linking issue once these checks are green.",
        ],
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("[base-app-readiness] ready")
    print(f"  out: {out_path}")
    print(f"  ready: {payload['status']['standard_web_ready']}")
    print(f"  blockers: {len(blockers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
