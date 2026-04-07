#!/usr/bin/env python3
"""Build a public claim manifest for DRW Merkle distribution."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims-file", required=True, help="JSON file with claims or {claims:[...]}")
    parser.add_argument("--out", required=True, help="Output manifest path")
    parser.add_argument(
        "--format",
        choices=("auto", "json", "csv"),
        default="auto",
        help="Input format for the claims file (default: infer from extension)",
    )
    parser.add_argument("--token", default="", help="Optional token address metadata")
    parser.add_argument("--network", default="", help="Optional network metadata")
    parser.add_argument("--claim-deadline", default="", help="Optional claim deadline metadata")
    return parser.parse_args()


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


def cast_abi_encode(index: int, account: str, amount: int) -> str:
    return cast("abi-encode", "f(uint256,address,uint256)", str(index), account, str(amount))


def cast_keccak(hex_data: str) -> str:
    return cast("keccak", hex_data).lower()


def leaf_hash(index: int, account: str, amount: int) -> str:
    inner = cast_keccak(cast_abi_encode(index, account, amount))
    return cast_keccak(inner)


def hash_pair(left: str, right: str) -> str:
    ordered = sorted((left.lower(), right.lower()), key=lambda value: int(value, 16))
    return cast_keccak("0x" + ordered[0][2:] + ordered[1][2:])


def load_claims(path: Path) -> list[dict]:
    raw = json.loads(path.read_text())
    claims = raw["claims"] if isinstance(raw, dict) else raw
    return normalize_claims(claims)


def load_claims_csv(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        if "account" not in (reader.fieldnames or []) or "amount" not in (reader.fieldnames or []):
            raise ValueError("csv claims file must contain account and amount columns")
        return normalize_claims(list(reader))


def normalize_claims(claims: list[dict]) -> list[dict]:
    if not isinstance(claims, list) or not claims:
        raise ValueError("claims file must contain a non-empty list")
    normalized: list[dict] = []
    seen_accounts: set[str] = set()
    for idx, entry in enumerate(claims):
        if not isinstance(entry, dict):
            raise ValueError("claim entries must be objects")
        account = normalize_address(str(entry["account"]))
        amount = int(str(entry["amount"]))
        if amount <= 0:
            raise ValueError("claim amount must be positive")
        if account in seen_accounts:
            raise ValueError(f"duplicate account in claims file: {account}")
        seen_accounts.add(account)
        normalized.append({"index": idx, "account": account, "amount": amount})
    return normalized


def infer_input_format(path: Path, declared_format: str) -> str:
    if declared_format != "auto":
        return declared_format
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    return "json"


def build_tree(claims: list[dict]) -> tuple[list[str], list[list[str]]]:
    leaves = [leaf_hash(entry["index"], entry["account"], entry["amount"]) for entry in claims]
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


def main() -> int:
    args = parse_args()
    claims_file = Path(args.claims_file).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    input_format = infer_input_format(claims_file, args.format)
    if input_format == "csv":
        claims = load_claims_csv(claims_file)
    else:
        claims = load_claims(claims_file)
    leaves, layers = build_tree(claims)
    manifest_claims: list[dict] = []
    total_amount = 0
    for entry, leaf in zip(claims, leaves, strict=True):
        proof = build_proof(layers, entry["index"])
        total_amount += entry["amount"]
        manifest_claims.append(
            {
                "index": entry["index"],
                "account": entry["account"],
                "amount": str(entry["amount"]),
                "leaf": leaf,
                "proof": proof,
            }
        )

    manifest = {
        "merkle_root": layers[-1][0],
        "claims_count": len(manifest_claims),
        "total_amount": str(total_amount),
        "claims": manifest_claims,
    }
    if args.token:
        manifest["token"] = normalize_address(args.token)
    if args.network:
        manifest["network"] = args.network
    if args.claim_deadline:
        manifest["claim_deadline"] = int(args.claim_deadline)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    print("[drw-merkle] ready")
    print(f"  claims_file: {claims_file}")
    print(f"  format:      {input_format}")
    print(f"  out:         {out_path}")
    print(f"  merkle_root: {manifest['merkle_root']}")
    print(f"  claims:      {manifest['claims_count']}")
    print(f"  total:       {manifest['total_amount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
