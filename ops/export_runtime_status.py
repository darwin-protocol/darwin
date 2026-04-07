#!/usr/bin/env python3
"""Export public runtime hosting status for the DARWIN site."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(REPO_ROOT / "web" / "public" / "runtime-status.json"),
        help="Output path for the generated runtime-status JSON",
    )
    parser.add_argument(
        "--site-domain",
        default=os.environ.get("DARWIN_SITE_DOMAIN", "usedarwin.xyz"),
        help="Canonical public site domain",
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", "darwin-protocol/darwin"),
        help="GitHub repository in owner/name form",
    )
    parser.add_argument(
        "--hosting-mode",
        choices=("github-pages", "cloudflare-tunnel"),
        default="github-pages",
        help="Hosting mode for the generated runtime status",
    )
    return parser.parse_args()


def gh_json(path: str) -> dict:
    result = subprocess.run(
        ["gh", "api", path],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def main() -> int:
    args = parse_args()
    site_domain = args.site_domain.strip()
    if args.hosting_mode == "cloudflare-tunnel":
        status = {
            "generated_at": utc_now(),
            "site_domain": site_domain,
            "site_url": f"https://{site_domain}/",
            "available": True,
            "transport": "https",
            "summary": f"{site_domain} is live over HTTPS.",
        }
    else:
        pages = gh_json(f"repos/{args.repo}/pages")
        https_enforced = bool(pages.get("https_enforced"))
        html_url = pages.get("html_url") or f"https://{site_domain}/"

        status = {
            "generated_at": utc_now(),
            "site_domain": site_domain,
            "site_url": html_url,
            "available": True,
            "transport": "https" if https_enforced else "http",
            "summary": f"{site_domain} is live over HTTPS." if https_enforced else f"{site_domain} is live.",
        }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    print(f"[runtime-status] wrote {out_path}")
    print(f"  transport: {status['transport']}")
    print(f"  site_url:  {status['site_url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
