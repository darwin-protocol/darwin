#!/usr/bin/env python3
"""Report recent DARWIN activity and separate project-controlled vs outside wallets."""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from Crypto.Hash import keccak


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEPLOYMENT = REPO_ROOT / "ops" / "deployments" / "base-sepolia-recovery.json"
DEFAULT_PROJECT_WALLETS = Path.home() / ".config" / "darwin" / "project-wallets.json"

NETWORK_DEFAULTS = {
    84532: "https://sepolia.base.org",
    8453: "https://mainnet.base.org",
    421614: "https://sepolia-rollup.arbitrum.io/rpc",
    42161: "https://arb1.arbitrum.io/rpc",
}

NETWORK_RPC_ENV_VARS = {
    84532: (
        "DARWIN_BASE_SEPOLIA_LOCAL_RPC_URL",
        "BASE_SEPOLIA_LOCAL_RPC_URL",
        "DARWIN_BASE_SEPOLIA_READ_RPC_URL",
        "DARWIN_BASE_SEPOLIA_RPC_URL",
        "BASE_SEPOLIA_RPC_URL",
    ),
    8453: (
        "DARWIN_BASE_LOCAL_RPC_URL",
        "BASE_LOCAL_RPC_URL",
        "DARWIN_BASE_READ_RPC_URL",
        "DARWIN_BASE_RPC_URL",
        "BASE_RPC_URL",
    ),
    421614: (
        "DARWIN_ARBITRUM_SEPOLIA_LOCAL_RPC_URL",
        "ARBITRUM_SEPOLIA_LOCAL_RPC_URL",
        "DARWIN_ARBITRUM_SEPOLIA_READ_RPC_URL",
        "DARWIN_ARBITRUM_SEPOLIA_RPC_URL",
        "ARBITRUM_SEPOLIA_RPC_URL",
    ),
    42161: (
        "DARWIN_ARBITRUM_LOCAL_RPC_URL",
        "ARBITRUM_LOCAL_RPC_URL",
        "DARWIN_ARBITRUM_READ_RPC_URL",
        "DARWIN_ARBITRUM_RPC_URL",
        "ARBITRUM_RPC_URL",
    ),
}

GENERIC_RPC_ENV_VARS = (
    "DARWIN_LOCAL_RPC_URL",
    "DARWIN_READ_RPC_URL",
    "DARWIN_RPC_URL",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment-file", default=str(DEFAULT_DEPLOYMENT))
    parser.add_argument("--vnext-file", default="")
    parser.add_argument("--epoch-file", default=str(REPO_ROOT / "ops" / "community_epoch.json"))
    parser.add_argument("--project-wallets-file", default=str(DEFAULT_PROJECT_WALLETS))
    parser.add_argument("--rpc-url", default="")
    parser.add_argument("--lookback-blocks", type=int, default=200000)
    parser.add_argument("--max-log-range", type=int, default=10000)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--public-json-out", default="")
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json(path)


def normalize_address(value: str) -> str:
    if not value:
        return ""
    value = value.lower()
    if not value.startswith("0x"):
        value = "0x" + value
    if len(value) != 42:
        raise ValueError(f"invalid address: {value}")
    return value


def topic_hash(signature: str) -> str:
    digest = keccak.new(digest_bits=256)
    digest.update(signature.encode())
    return "0x" + digest.hexdigest()


def address_from_topic(topic: str) -> str:
    return normalize_address("0x" + topic[-40:])


def words_from_data(data: str) -> list[int]:
    payload = data.removeprefix("0x")
    return [int(payload[i : i + 64], 16) for i in range(0, len(payload), 64) if payload[i : i + 64]]


def rpc_json(url: str, method: str, params: list) -> dict:
    request = Request(
        url,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "darwin-activity/1"},
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
    )
    return json.loads(urlopen(request, timeout=20).read().decode())


def rpc_chain_id(url: str) -> int:
    return int(rpc_json(url, "eth_chainId", [])["result"], 16)


def unique_values(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered


def build_rpc_candidates(chain_id: int, explicit_url: str = "") -> list[tuple[str, str]]:
    if explicit_url:
        return [("explicit", explicit_url)]

    candidates: list[tuple[str, str]] = []
    for env_name in NETWORK_RPC_ENV_VARS.get(chain_id, ()):
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append((env_name, value))
    for env_name in GENERIC_RPC_ENV_VARS:
        value = os.environ.get(env_name, "").strip()
        if value:
            candidates.append((env_name, value))
    default_value = NETWORK_DEFAULTS.get(chain_id, "")
    if default_value:
        candidates.append((f"default:{chain_id}", default_value))
    return [(source, url) for source, url in candidates if url]


def resolve_rpc_endpoints(chain_id: int, explicit_url: str = "") -> list[dict]:
    candidates = build_rpc_candidates(chain_id, explicit_url)
    validated: list[dict] = []
    failures: list[str] = []
    seen_urls: set[str] = set()

    for source, url in candidates:
        normalized = url.strip()
        if not normalized or normalized in seen_urls:
            continue
        seen_urls.add(normalized)
        try:
            observed = rpc_chain_id(normalized)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{source}={normalized} ({exc})")
            continue
        if observed != chain_id:
            failures.append(f"{source}={normalized} (observed_chain={observed} expected={chain_id})")
            continue
        validated.append(
            {
                "source": source,
                "url": normalized,
                "chain_id": observed,
            }
        )

    if validated:
        return validated

    if explicit_url:
        raise RuntimeError(
            "explicit rpc_url did not resolve to the deployment chain: "
            + ("; ".join(failures) if failures else "no candidates were available")
        )

    raise RuntimeError(
        f"no matching RPC endpoints found for chain {chain_id}: "
        + ("; ".join(failures) if failures else "no candidates were configured")
    )


def rpc_json_any(urls: list[str], method: str, params: list) -> dict:
    failures: list[str] = []
    for url in unique_values(urls):
        try:
            payload = rpc_json(url, method, params)
            if payload.get("error"):
                failures.append(f"{url} ({payload['error']})")
                continue
            return payload
        except (HTTPError, URLError, TimeoutError) as exc:
            failures.append(f"{url} ({exc})")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{url} ({exc})")
    raise RuntimeError(
        f"all RPC endpoints failed for {method}: " + ("; ".join(failures) if failures else "no urls configured")
    )


def rpc_block_number(urls: list[str]) -> int:
    return int(rpc_json_any(urls, "eth_blockNumber", [])["result"], 16)


def rpc_block_timestamp(urls: list[str], block_number: int, cache: dict[int, int]) -> int:
    if block_number not in cache:
        result = rpc_json_any(urls, "eth_getBlockByNumber", [hex(block_number), False]).get("result") or {}
        cache[block_number] = int(result.get("timestamp", "0x0"), 16)
    return cache[block_number]


def rpc_get_logs(
    urls: list[str],
    *,
    address: str,
    from_block: int,
    to_block: int,
    topic0: str,
    max_log_range: int,
) -> list[dict]:
    if max_log_range <= 0:
        raise ValueError("max_log_range must be positive")

    logs: list[dict] = []
    chunk_start = from_block
    while chunk_start <= to_block:
        chunk_end = min(to_block, chunk_start + max_log_range - 1)
        payload = {
            "address": address,
            "fromBlock": hex(chunk_start),
            "toBlock": hex(chunk_end),
            "topics": [topic0],
        }
        logs.extend(rpc_json_any(urls, "eth_getLogs", [payload]).get("result", []))
        chunk_start = chunk_end + 1
    return logs


def collect_addresses(node: object) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        for value in node.values():
            found.update(collect_addresses(value))
    elif isinstance(node, list):
        for value in node:
            found.update(collect_addresses(value))
    elif isinstance(node, str) and node.startswith("0x") and len(node) == 42:
        found.add(normalize_address(node))
    return found


def parse_project_wallets(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return collect_addresses(load_json(path))


def format_units(value: int, decimals: int = 18, precision: int = 6) -> str:
    scaled = value / (10**decimals)
    text = f"{scaled:.{precision}f}"
    return text.rstrip("0").rstrip(".")


def format_iso_timestamp(value: int) -> str:
    if value <= 0:
        return ""
    return datetime.fromtimestamp(value, timezone.utc).isoformat().replace("+00:00", "Z")


def parse_swap(log: dict, token_address: str, quote_address: str) -> dict:
    words = words_from_data(log["data"])
    amount_in, amount_out, recipient_word = words
    trader = address_from_topic(log["topics"][1])
    token_in = address_from_topic(log["topics"][2])
    token_out = address_from_topic(log["topics"][3])
    recipient = normalize_address("0x" + hex(recipient_word)[2:].rjust(40, "0")[-40:])
    sold_token = token_in == normalize_address(token_address)
    title = "swap_sell" if sold_token else "swap_buy"
    detail = f"{format_units(amount_in)} {'DRW' if token_in == normalize_address(token_address) else 'WETH'} -> {format_units(amount_out, 18, 12)} {'DRW' if token_out == normalize_address(token_address) else 'WETH'}"
    return {
        "type": "swap",
        "title": title,
        "actor": trader,
        "counterparty": recipient,
        "detail": detail,
        "tx_hash": log["transactionHash"],
        "block_number": int(log["blockNumber"], 16),
    }


def parse_faucet_claim(log: dict) -> dict:
    words = words_from_data(log["data"])
    token_amount, native_amount, _next_eligible = words
    claimer = address_from_topic(log["topics"][1])
    recipient = address_from_topic(log["topics"][2])
    return {
        "type": "faucet",
        "title": "faucet_claim",
        "actor": claimer,
        "counterparty": recipient,
        "detail": f"{format_units(token_amount)} DRW + {format_units(native_amount, 18, 6)} ETH",
        "tx_hash": log["transactionHash"],
        "block_number": int(log["blockNumber"], 16),
    }


def parse_distributor_claim(log: dict) -> dict:
    words = words_from_data(log["data"])
    amount = words[0]
    account = address_from_topic(log["topics"][2])
    return {
        "type": "distributor",
        "title": "distribution_claim",
        "actor": account,
        "counterparty": account,
        "detail": f"{format_units(amount)} DRW",
        "tx_hash": log["transactionHash"],
        "block_number": int(log["blockNumber"], 16),
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# DARWIN External Activity",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Network: `{report['network']}`",
        f"- Lookback blocks: `{report['lookback_blocks']}`",
        f"- Total events: `{report['summary']['total_events']}`",
        f"- External events: `{report['summary']['external_events']}`",
        f"- External wallets: `{report['summary']['external_wallets']}`",
        "",
        "## Recent External Activity",
        "",
    ]

    if not report["recent_external"]:
        lines.append("- none in current lookback window")
    else:
        for event in report["recent_external"][:25]:
            lines.append(
                f"- `{event['type']}` `{event['actor']}` {event['detail']} tx `{event['tx_hash']}`"
            )
    return "\n".join(lines) + "\n"


def write_report(path_value: str, content: str) -> None:
    path = Path(path_value).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def progress_snapshot(current: int, target: int) -> dict:
    if target <= 0:
        return {
            "current": current,
            "target": target,
            "remaining": None,
            "pct_complete": 0.0,
        }
    remaining = max(target - current, 0)
    pct_complete = round(min(current / target, 1) * 100, 2)
    return {
        "current": current,
        "target": target,
        "remaining": remaining,
        "pct_complete": pct_complete,
    }


def build_progress(summary: dict, epoch: dict) -> dict:
    milestones = epoch.get("milestones") or {}
    wallets = progress_snapshot(int(summary.get("external_wallets", 0) or 0), int(milestones.get("external_wallets_target", 0) or 0))
    swaps = progress_snapshot(int(summary.get("external_swaps", 0) or 0), int(milestones.get("external_swaps_target", 0) or 0))
    traction_ready = bool(
        wallets["target"]
        and swaps["target"]
        and wallets["current"] >= wallets["target"]
        and swaps["current"] >= swaps["target"]
    )
    return {
        "wallets": wallets,
        "swaps": swaps,
        "traction_ready": traction_ready,
        "unlocks": {
            "experimental": traction_ready,
            "incentivized": traction_ready,
        },
    }


def reward_scoring(epoch: dict) -> dict:
    scoring = ((epoch.get("reward_policy") or {}).get("scoring") or {})
    return {
        "claim_points": int(scoring.get("claim_points", 1) or 1),
        "swap_points": int(scoring.get("swap_points", 3) or 3),
        "return_after_hours": int(scoring.get("return_after_hours", 24) or 24),
        "return_swap_bonus_points": int(scoring.get("return_swap_bonus_points", 2) or 2),
    }


def qualifies_return_swap(swap_timestamps: list[int], hours: int) -> bool:
    if len(swap_timestamps) < 2:
        return False
    threshold = max(hours, 0) * 3600
    ordered = sorted(swap_timestamps)
    return ordered[-1] - ordered[0] >= threshold


def build_leaderboard(events: list[dict], epoch: dict) -> dict:
    scoring = reward_scoring(epoch)
    rows: dict[str, dict] = defaultdict(dict)
    for event in events:
        actor = normalize_address(event["actor"])
        row = rows.setdefault(
            actor,
            {
                "actor": actor,
                "events": 0,
                "swaps": 0,
                "claims": 0,
                "first_block": event["block_number"],
                "latest_block": event["block_number"],
                "first_seen_at": event.get("timestamp", 0),
                "latest_seen_at": event.get("timestamp", 0),
                "swap_timestamps": [],
            },
        )
        row["events"] += 1
        row["first_block"] = min(row["first_block"], event["block_number"])
        row["latest_block"] = max(row["latest_block"], event["block_number"])
        event_timestamp = int(event.get("timestamp", 0) or 0)
        if event_timestamp:
            if not row["first_seen_at"]:
                row["first_seen_at"] = event_timestamp
            else:
                row["first_seen_at"] = min(row["first_seen_at"], event_timestamp)
            row["latest_seen_at"] = max(row["latest_seen_at"], event_timestamp)
        if event["type"] == "swap":
            row["swaps"] += 1
            if event_timestamp:
                row["swap_timestamps"].append(event_timestamp)
        if event["type"] in {"faucet", "distributor"}:
            row["claims"] += 1

    leaderboard_rows = []
    for row in rows.values():
        return_swap_qualified = qualifies_return_swap(row["swap_timestamps"], scoring["return_after_hours"])
        points = row["claims"] * scoring["claim_points"] + row["swaps"] * scoring["swap_points"]
        if return_swap_qualified:
            points += scoring["return_swap_bonus_points"]
        leaderboard_rows.append(
            {
                "actor": row["actor"],
                "points": points,
                "events": row["events"],
                "swaps": row["swaps"],
                "claims": row["claims"],
                "return_swap_qualified": return_swap_qualified,
                "first_block": row["first_block"],
                "latest_block": row["latest_block"],
                "first_seen_at": format_iso_timestamp(int(row["first_seen_at"] or 0)),
                "latest_seen_at": format_iso_timestamp(int(row["latest_seen_at"] or 0)),
            }
        )

    leaderboard_rows.sort(
        key=lambda item: (
            -item["points"],
            -item["swaps"],
            -item["claims"],
            -item["latest_block"],
            item["actor"],
        )
    )

    for index, row in enumerate(leaderboard_rows, start=1):
        row["rank"] = index

    return {
        "scoring_label": ((epoch.get("reward_policy") or {}).get("scoring_label")) or "Outside activity score",
        "return_after_hours": scoring["return_after_hours"],
        "entries": leaderboard_rows[:10],
    }


def main() -> int:
    args = parse_args()
    deployment_path = Path(args.deployment_file).expanduser().resolve()
    deployment = load_json(deployment_path)
    vnext_path = Path(args.vnext_file).expanduser().resolve() if args.vnext_file else deployment_path.with_suffix(".vnext.json")
    vnext = load_json(vnext_path) if vnext_path.exists() else {}
    epoch = load_optional_json(Path(args.epoch_file).expanduser().resolve())

    rpc_endpoints = resolve_rpc_endpoints(int(deployment["chain_id"]), explicit_url=args.rpc_url)
    rpc_url = rpc_endpoints[0]["url"]
    rpc_urls = [entry["url"] for entry in rpc_endpoints]
    latest_block = rpc_block_number(rpc_urls)
    from_block = max(0, latest_block - args.lookback_blocks)

    pool_address = deployment["market"]["contracts"]["reference_pool"]
    token_address = deployment["contracts"]["drw_token"]
    quote_address = deployment["market"]["quote_token"]
    faucet_address = ((deployment.get("faucet") or {}).get("contracts") or {}).get("drw_faucet", "")
    distributor_address = ((vnext.get("vnext") or {}).get("contracts") or {}).get("drw_merkle_distributor", "")

    events = [
        *(
            parse_swap(log, token_address, quote_address)
            for log in rpc_get_logs(
                rpc_urls,
                address=pool_address,
                from_block=from_block,
                to_block=latest_block,
                topic0=topic_hash("SwapExecuted(address,address,uint256,address,uint256,address)"),
                max_log_range=args.max_log_range,
            )
        ),
    ]

    if faucet_address:
        events.extend(
            parse_faucet_claim(log)
            for log in rpc_get_logs(
                rpc_urls,
                address=faucet_address,
                from_block=from_block,
                to_block=latest_block,
                topic0=topic_hash("Claimed(address,address,uint256,uint256,uint256)"),
                max_log_range=args.max_log_range,
            )
        )

    if distributor_address:
        events.extend(
            parse_distributor_claim(log)
            for log in rpc_get_logs(
                rpc_urls,
                address=distributor_address,
                from_block=from_block,
                to_block=latest_block,
                topic0=topic_hash("Claimed(uint256,address,uint256)"),
                max_log_range=args.max_log_range,
            )
        )

    events.sort(key=lambda item: (item["block_number"], item["tx_hash"]), reverse=True)
    timestamp_cache: dict[int, int] = {}
    for event in events:
        event["timestamp"] = rpc_block_timestamp(rpc_urls, event["block_number"], timestamp_cache)
        event["seen_at"] = format_iso_timestamp(event["timestamp"])

    project_wallets = collect_addresses(deployment) | collect_addresses(vnext) | parse_project_wallets(Path(args.project_wallets_file))
    total_wallets = sorted({normalize_address(event["actor"]) for event in events})
    external_events = [event for event in events if normalize_address(event["actor"]) not in project_wallets]
    external_wallets = sorted({normalize_address(event["actor"]) for event in external_events})
    project_events = [event for event in events if normalize_address(event["actor"]) in project_wallets]
    project_wallets_seen = sorted({normalize_address(event["actor"]) for event in project_events})
    external_swaps = [event for event in external_events if event["type"] == "swap"]
    external_claims = [event for event in external_events if event["type"] in {"faucet", "distributor"}]
    summary = {
        "total_events": len(events),
        "total_wallets": len(total_wallets),
        "external_events": len(external_events),
        "external_wallets": len(external_wallets),
        "external_swaps": len(external_swaps),
        "external_claims": len(external_claims),
        "project_events": len(project_events),
        "project_wallets": len(project_wallets_seen),
    }
    progress = build_progress(summary, epoch)
    leaderboard = build_leaderboard(external_events, epoch)

    report = {
        "generated_at": utc_now(),
        "network": deployment["network"],
        "rpc_url": rpc_url,
        "rpc_source": rpc_endpoints[0]["source"],
        "rpc_candidates": rpc_endpoints,
        "lookback_blocks": args.lookback_blocks,
        "epoch": {
            "id": epoch.get("id", ""),
            "status": epoch.get("status", ""),
            "title": epoch.get("title", ""),
        },
        "summary": summary,
        "progress": progress,
        "leaderboard": leaderboard,
        "recent_events": events[:50],
        "recent_external": external_events[:50],
    }

    rendered = json.dumps(report, indent=2) + "\n"
    print(rendered)

    if args.json_out:
        write_report(args.json_out, rendered)
    if args.markdown_out:
        write_report(args.markdown_out, render_markdown(report))
    if args.public_json_out:
        public_report = {
            "generated_at": report["generated_at"],
            "network": report["network"],
            "lookback_blocks": report["lookback_blocks"],
            "epoch": report["epoch"],
            "summary": report["summary"],
            "progress": report["progress"],
            "leaderboard": report["leaderboard"],
            "recent_external": [
                {
                    "type": event["type"],
                    "title": event["title"],
                    "actor": event["actor"],
                    "detail": event["detail"],
                    "tx_hash": event["tx_hash"],
                    "block_number": event["block_number"],
                    "seen_at": event.get("seen_at", ""),
                }
                for event in report["recent_external"][:10]
            ],
        }
        write_report(args.public_json_out, json.dumps(public_report, indent=2) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
