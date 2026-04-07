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
    pages = gh_json(f"repos/{args.repo}/pages")

    https_enforced = bool(pages.get("https_enforced"))
    html_url = pages.get("html_url") or ""
    site_domain = args.site_domain.strip()

    status = {
        "generated_at": utc_now(),
        "repo": args.repo,
        "site_domain": site_domain,
        "html_url": html_url,
        "https_enforced": https_enforced,
        "certificate_ready": https_enforced,
        "transport": "https" if https_enforced else "http",
        "summary": (
            f"{site_domain} is live over HTTPS."
            if https_enforced
            else f"{site_domain} is live over HTTP. GitHub Pages TLS is still pending."
        ),
        "details": {
            "cname": pages.get("cname"),
            "pending_domain_unverified_at": pages.get("pending_domain_unverified_at"),
            "protected_domain_state": pages.get("protected_domain_state"),
        },
    }

    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n")
    print(f"[runtime-status] wrote {out_path}")
    print(f"  https_enforced: {https_enforced}")
    print(f"  html_url:       {html_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
