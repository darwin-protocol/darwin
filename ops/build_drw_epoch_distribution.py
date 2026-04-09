#!/usr/bin/env python3
"""Build an epoch-aware DRW reward manifest from the outside-activity snapshot."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--activity-report",
        required=True,
        help="Full activity report JSON from ops/report_external_activity.py",
    )
    parser.add_argument(
        "--epoch-file",
        required=True,
        help="Epoch config JSON that defines reward rules",
    )
    parser.add_argument("--out", required=True, help="Output manifest path")
    parser.add_argument("--epoch-id", type=int, default=0, help="On-chain epoch id override")
    parser.add_argument("--claim-deadline", type=int, default=0, help="Claim deadline timestamp override")
    parser.add_argument(
        "--claim-window-days",
        type=int,
        default=0,
        help="Claim window length in days when --claim-deadline is not provided",
    )
    parser.add_argument("--token", default="", help="Optional token address metadata")
    parser.add_argument("--network", default="", help="Optional network metadata")
    parser.add_argument("--distributor", default="", help="Optional epoch distributor address metadata")
    parser.add_argument("--token-decimals", type=int, default=18, help="Token decimals for on-chain claim amounts")
    parser.add_argument(
        "--include-claim-rule",
        action="store_true",
        help="Also include the claim-only rule in the Merkle allocation instead of leaving it faucet-only",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def normalize_address(address: str) -> str:
    if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
        raise ValueError(f"invalid address: {address!r}")
    int(address[2:], 16)
    return "0x" + address[2:].lower()


def cast(*args: str) -> str:
    result = subprocess.run(["cast", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"cast {' '.join(args)} failed")
    return result.stdout.strip()


def cast_abi_encode(epoch_id: int, index: int, account: str, amount: int) -> str:
    return cast("abi-encode", "f(uint256,uint256,address,uint256)", str(epoch_id), str(index), account, str(amount))


def cast_keccak(hex_data: str) -> str:
    return cast("keccak", hex_data).lower()


def leaf_hash(epoch_id: int, index: int, account: str, amount: int) -> str:
    inner = cast_keccak(cast_abi_encode(epoch_id, index, account, amount))
    return cast_keccak(inner)


def hash_pair(left: str, right: str) -> str:
    ordered = sorted((left.lower(), right.lower()), key=lambda value: int(value, 16))
    return cast_keccak("0x" + ordered[0][2:] + ordered[1][2:])


def build_tree(claims: list[dict], epoch_id: int) -> tuple[list[str], list[list[str]]]:
    leaves = [leaf_hash(epoch_id, entry["index"], entry["account"], entry["amount"]) for entry in claims]
    layers = [leaves]
    current = leaves
    while len(current) > 1:
        nxt: list[str] = []
        for idx in range(0, len(current), 2):
            if idx + 1 >= len(current):
                nxt.append(current[idx])
            else:
                nxt.append(hash_pair(current[idx], current[idx + 1]))
        layers.append(nxt)
        current = nxt
    return leaves, layers


def build_proof(layers: list[list[str]], index: int) -> list[str]:
    proof: list[str] = []
    current_index = index
    for layer in layers[:-1]:
        sibling_index = current_index ^ 1
        if sibling_index < len(layer):
            proof.append(layer[sibling_index])
        current_index //= 2
    return proof


def resolve_epoch_id(epoch: dict, override: int) -> int:
    if override > 0:
        return override
    for key in ("onchain_epoch_id", "epoch_id", "sequence", "number"):
        value = int(epoch.get(key, 0) or 0)
        if value > 0:
            return value
    raise ValueError("epoch config must include onchain_epoch_id/epoch_id or pass --epoch-id")


def resolve_claim_deadline(epoch: dict, override: int, window_days_override: int) -> int:
    if override > 0:
        return override
    reward_policy = epoch.get("reward_policy") or {}
    window_days = window_days_override or int(reward_policy.get("claim_window_days", 0) or 0)
    if window_days <= 0:
        window_days = 7
    return int(time.time()) + window_days * 24 * 3600


def distribution_entries(activity_report: dict) -> list[dict]:
    board = activity_report.get("leaderboard") or {}
    all_entries = board.get("all_entries")
    if isinstance(all_entries, list) and all_entries:
        return list(all_entries)
    entries = board.get("entries")
    if isinstance(entries, list):
        return list(entries)
    return []


def eligible_rules(epoch: dict, *, include_claim_rule: bool, token_decimals: int) -> list[dict]:
    reward_policy = epoch.get("reward_policy") or {}
    result: list[dict] = []
    scale = 10 ** max(int(token_decimals), 0)
    for rule in reward_policy.get("rules") or []:
        amount = int(rule.get("amount", 0) or 0) * scale
        eligibility = str(rule.get("eligibility", "") or rule.get("id", "")).strip()
        if amount <= 0 or not eligibility:
            continue
        if eligibility == "future_unlock":
            continue
        if eligibility == "claim" and not include_claim_rule:
            continue
        result.append(
            {
                "id": str(rule.get("id") or eligibility),
                "label": str(rule.get("label") or eligibility),
                "eligibility": eligibility,
                "amount": amount,
                "detail": str(rule.get("detail") or ""),
            }
        )
    return result


@dataclass
class RewardBreakdown:
    rule_id: str
    label: str
    eligibility: str
    amount: int
    detail: str


def wallet_breakdown(entry: dict, rules: list[dict]) -> list[RewardBreakdown]:
    reward_eligibility = entry.get("reward_eligibility") or {}
    swap_active = bool(entry.get("eligible_for_leaderboard") or entry.get("swaps", 0))
    if not swap_active:
        return []

    items: list[RewardBreakdown] = []
    for rule in rules:
        if rule["eligibility"] == "claim" and not swap_active:
            continue
        if reward_eligibility.get(rule["eligibility"]) or reward_eligibility.get(rule["id"]):
            items.append(
                RewardBreakdown(
                    rule_id=rule["id"],
                    label=rule["label"],
                    eligibility=rule["eligibility"],
                    amount=int(rule["amount"]),
                    detail=rule["detail"],
                )
            )
    return items


def main() -> int:
    args = parse_args()
    activity_path = Path(args.activity_report).expanduser().resolve()
    epoch_path = Path(args.epoch_file).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    activity_report = load_json(activity_path)
    epoch = load_json(epoch_path)
    epoch_id = resolve_epoch_id(epoch, args.epoch_id)
    claim_deadline = resolve_claim_deadline(epoch, args.claim_deadline, args.claim_window_days)
    if claim_deadline <= int(time.time()):
        raise SystemExit("claim deadline must be in the future")

    rules = eligible_rules(epoch, include_claim_rule=args.include_claim_rule, token_decimals=args.token_decimals)
    entries = distribution_entries(activity_report)
    normalized_claims: list[dict] = []
    skipped_wallets = 0
    total_amount = 0

    for entry in entries:
        account = normalize_address(str(entry.get("actor", "")))
        breakdown = wallet_breakdown(entry, rules)
        if not breakdown:
            skipped_wallets += 1
            continue
        amount = sum(item.amount for item in breakdown)
        claim = {
            "account": account,
            "amount": amount,
            "breakdown": [
                {
                    "rule_id": item.rule_id,
                    "label": item.label,
                    "eligibility": item.eligibility,
                    "amount": str(item.amount),
                    "detail": item.detail,
                }
                for item in breakdown
            ],
            "events": int(entry.get("events", 0) or 0),
            "swaps": int(entry.get("swaps", 0) or 0),
            "claims": int(entry.get("claims", 0) or 0),
            "points": int(entry.get("points", 0) or 0),
            "return_swap_qualified": bool(entry.get("return_swap_qualified", False)),
        }
        total_amount += amount
        normalized_claims.append(claim)

    normalized_claims.sort(key=lambda item: (-item["points"], -item["swaps"], item["account"]))
    indexed_claims: list[dict] = []
    for index, claim in enumerate(normalized_claims):
        indexed_claims.append({"index": index, **claim})

    if indexed_claims:
        leaves, layers = build_tree(indexed_claims, epoch_id)
        merkle_root = layers[-1][0]
    else:
        leaves, layers, merkle_root = [], [[]], "0x" + ("00" * 32)

    manifest_claims: list[dict] = []
    claims_by_account: dict[str, dict] = {}
    for claim, leaf in zip(indexed_claims, leaves, strict=True):
        proof = build_proof(layers, claim["index"])
        payload = {
            "index": claim["index"],
            "account": claim["account"],
            "amount": str(claim["amount"]),
            "leaf": leaf,
            "proof": proof,
            "breakdown": claim["breakdown"],
            "events": claim["events"],
            "swaps": claim["swaps"],
            "claims": claim["claims"],
            "points": claim["points"],
            "return_swap_qualified": claim["return_swap_qualified"],
        }
        manifest_claims.append(payload)
        claims_by_account[claim["account"]] = payload

    reward_policy = epoch.get("reward_policy") or {}
    manifest = {
        "generated_at": utc_now(),
        "mode": "epoch_distributor",
        "epoch_id": epoch_id,
        "epoch_key": str(epoch.get("id", "")),
        "epoch_title": str(epoch.get("title", "")),
        "network": args.network or str(activity_report.get("network", "")),
        "token": normalize_address(args.token) if args.token else "",
        "distributor": normalize_address(args.distributor) if args.distributor else "",
        "merkle_root": merkle_root,
        "claims_count": len(manifest_claims),
        "eligible_wallets": len(manifest_claims),
        "skipped_wallets": skipped_wallets,
        "total_amount": str(total_amount),
        "claim_deadline": claim_deadline,
        "currency_symbol": str(reward_policy.get("currency_symbol", "DRW")),
        "eligibility_note": (
            "Only swap-active wallets from the published epoch snapshot receive proof-based bonus claims. "
            "The faucet remains the starter claim path."
        ),
        "rules_applied": [
            {
                "id": rule["id"],
                "label": rule["label"],
                "eligibility": rule["eligibility"],
                "amount": str(rule["amount"]),
                "detail": rule["detail"],
            }
            for rule in rules
        ],
        "claims": manifest_claims,
        "claims_by_account": claims_by_account,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print("[drw-epoch-distribution] ready")
    print(f"  activity_report: {activity_path}")
    print(f"  epoch_file:      {epoch_path}")
    print(f"  out:             {out_path}")
    print(f"  epoch_id:        {epoch_id}")
    print(f"  claim_deadline:  {claim_deadline}")
    print(f"  merkle_root:     {merkle_root}")
    print(f"  claims:          {manifest['claims_count']}")
    print(f"  total_amount:    {manifest['total_amount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
