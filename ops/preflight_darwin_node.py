#!/usr/bin/env python3
"""Preflight a local DARWIN overlay node before booting services."""

from __future__ import annotations

import argparse
import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]

NETWORK_DEFAULTS: dict[int, dict[str, str]] = {
    84532: {
        "network_name": "Base Sepolia",
        "rpc_url": "https://sepolia.base.org",
        "explorer_base_url": "https://sepolia-explorer.base.org",
    },
    8453: {
        "network_name": "Base",
        "rpc_url": "https://mainnet.base.org",
        "explorer_base_url": "https://basescan.org",
    },
    421614: {
        "network_name": "Arbitrum Sepolia",
        "rpc_url": "https://sepolia-rollup.arbitrum.io/rpc",
        "explorer_base_url": "https://sepolia.arbiscan.io",
    },
    42161: {
        "network_name": "Arbitrum",
        "rpc_url": "https://arb1.arbitrum.io/rpc",
        "explorer_base_url": "https://arbiscan.io",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment-file",
        default=str(ROOT / "ops" / "deployments" / "base-sepolia-recovery.json"),
        help="Deployment artifact to pin the overlay against",
    )
    parser.add_argument("--rpc-url", default="", help="RPC URL for on-chain contract verification")
    parser.add_argument("--state-root", default="", help="State root for logs, reports, and service data")
    parser.add_argument("--gateway-port", type=int, default=9443)
    parser.add_argument("--router-port", type=int, default=9444)
    parser.add_argument("--scorer-port", type=int, default=9445)
    parser.add_argument("--watcher-port", type=int, default=9446)
    parser.add_argument("--archive-port", type=int, default=9447)
    parser.add_argument("--finalizer-port", type=int, default=9448)
    parser.add_argument("--sentinel-port", type=int, default=9449)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--markdown-out", default="")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def rpc_json(url: str, method: str, params: list[Any]) -> dict[str, Any]:
    request = Request(
        url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "darwin-node-preflight/1",
        },
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
    )
    return json.loads(urlopen(request, timeout=10).read().decode())


def rpc_chain_id(url: str) -> int:
    return int(str(rpc_json(url, "eth_chainId", [])["result"]), 16)


def port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# DARWIN Node Preflight",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Network: `{report['deployment'].get('network', '')}`",
        f"- Chain ID: `{report['deployment'].get('chain_id', '')}`",
        f"- RPC: `{report['rpc'].get('url', '')}`",
        f"- Ready to start: `{'yes' if report['ready'] else 'no'}`",
        "",
        "## Checks",
        "",
        "| Check | State | Detail |",
        "|---|---|---|",
    ]
    for name, check in report["checks"].items():
        lines.append(f"| `{name}` | `{check['state']}` | `{check['detail']}` |")
    lines.extend(["", "## Blockers", ""])
    if report["blockers"]:
        lines.extend(f"- {blocker}" for blocker in report["blockers"])
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def write_report(path_value: str, content: str) -> None:
    path = Path(path_value).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def main() -> int:
    args = parse_args()
    deployment_path = Path(args.deployment_file).expanduser().resolve()
    if not deployment_path.exists():
        raise SystemExit(f"deployment file not found: {deployment_path}")

    deployment = load_json(deployment_path)
    network = str(deployment["network"])
    chain_id = int(deployment["chain_id"])
    defaults = NETWORK_DEFAULTS.get(chain_id, {})
    rpc_url = args.rpc_url or defaults.get("rpc_url", "")
    state_root = Path(args.state_root).expanduser().resolve() if args.state_root else ROOT / "ops" / "state" / f"{network}-node"
    report = {
        "generated_at": utc_now(),
        "deployment": {
            "path": str(deployment_path),
            "network": network,
            "chain_id": chain_id,
            "settlement_hub": str((deployment.get("contracts") or {}).get("settlement_hub", "")),
        },
        "rpc": {
            "url": rpc_url,
            "observed_chain_id": None,
            "explorer_base_url": defaults.get("explorer_base_url", ""),
        },
        "state_root": str(state_root),
        "checks": {},
        "blockers": [],
        "ready": False,
    }

    report["checks"]["deployment"] = {
        "state": "OK",
        "detail": f"{network} chain={chain_id} artifact={deployment_path.name}",
    }

    state_dirs = {
        "logs": state_root / "logs",
        "reports": state_root / "reports",
        "gateway": state_root / "gateway",
        "router": state_root / "router",
        "archive": state_root / "archive",
        "watcher": state_root / "watcher",
        "finalizer": state_root / "finalizer",
        "sentinel": state_root / "sentinel",
    }
    report["checks"]["state_root"] = {
        "state": "OK",
        "detail": f"root={state_root} reports={state_dirs['reports']}",
    }

    ports = {
        "gateway": args.gateway_port,
        "router": args.router_port,
        "scorer": args.scorer_port,
        "watcher": args.watcher_port,
        "archive": args.archive_port,
        "finalizer": args.finalizer_port,
        "sentinel": args.sentinel_port,
    }
    occupied = {name: port for name, port in ports.items() if not port_available(port)}
    if occupied:
        report["checks"]["ports"] = {
            "state": "FAIL",
            "detail": ", ".join(f"{name}:{port}" for name, port in occupied.items()),
        }
        report["blockers"].append("ports_in_use")
    else:
        report["checks"]["ports"] = {
            "state": "OK",
            "detail": ", ".join(f"{name}:{port}" for name, port in ports.items()),
        }

    if not rpc_url:
        report["checks"]["rpc"] = {
            "state": "FAIL",
            "detail": "no rpc_url configured and no chain default is known",
        }
        report["blockers"].append("missing_rpc_url")
    else:
        try:
            observed = rpc_chain_id(rpc_url)
            report["rpc"]["observed_chain_id"] = observed
            if observed != chain_id:
                report["checks"]["rpc"] = {
                    "state": "FAIL",
                    "detail": f"url={rpc_url} observed_chain={observed} expected={chain_id}",
                }
                report["blockers"].append("rpc_chain_mismatch")
            else:
                report["checks"]["rpc"] = {
                    "state": "OK",
                    "detail": f"url={rpc_url} chain={observed}",
                }
        except Exception as exc:  # noqa: BLE001
            report["checks"]["rpc"] = {
                "state": "DOWN",
                "detail": f"url={rpc_url} error={exc}",
            }
            report["blockers"].append("rpc_unreachable")

    report["ready"] = not report["blockers"]

    if args.json_out:
        write_report(args.json_out, json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.markdown_out:
        write_report(args.markdown_out, render_markdown(report))

    print("[darwin-node] Preflight")
    print(f"  deployment:      {deployment_path}")
    print(f"  network:         {network}")
    print(f"  chain_id:        {chain_id}")
    print(f"  rpc_url:         {rpc_url or 'missing'}")
    if report["rpc"]["observed_chain_id"] is not None:
        print(f"  rpc_chain_id:    {report['rpc']['observed_chain_id']}")
    print(f"  state_root:      {state_root}")
    print(f"  ports:           {', '.join(f'{name}:{port}' for name, port in ports.items())}")
    print(f"  ready_to_start:  {'yes' if report['ready'] else 'no'}")
    if report["blockers"]:
        print(f"  blockers:        {', '.join(report['blockers'])}")

    return 0 if report["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
