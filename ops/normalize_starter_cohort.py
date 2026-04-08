#!/usr/bin/env python3
"""Normalize rough starter-cohort intake rows into a Merkle-ready CSV."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--intake-file", required=True, help="Input CSV/JSON with wallet intake rows")
    parser.add_argument("--out", required=True, help="Output CSV path")
    parser.add_argument(
        "--format",
        choices=("auto", "csv", "json"),
        default="auto",
        help="Input format for the intake file (default: infer from extension)",
    )
    parser.add_argument(
        "--default-amount",
        default="100000000000000000000",
        help="Raw DRW amount to assign when a row omits amount",
    )
    return parser.parse_args()


def infer_input_format(path: Path, declared_format: str) -> str:
    if declared_format != "auto":
        return declared_format
    return "csv" if path.suffix.lower() == ".csv" else "json"


def normalize_address(address: str) -> str:
    if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
        raise ValueError(f"invalid address: {address!r}")
    int(address[2:], 16)
    return "0x" + address[2:].lower()


def normalize_amount(value: object, default_amount: str) -> str:
    raw = str(value or "").strip()
    amount = raw or default_amount
    parsed = int(amount)
    if parsed <= 0:
        raise ValueError("starter cohort amount must be positive")
    return str(parsed)


def row_value(row: dict, *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def load_rows(path: Path, input_format: str) -> list[dict]:
    if input_format == "csv":
        with path.open(newline="") as handle:
            return list(csv.DictReader(handle))
    raw = json.loads(path.read_text())
    if isinstance(raw, dict):
        if isinstance(raw.get("entries"), list):
            return raw["entries"]
        if isinstance(raw.get("claims"), list):
            return raw["claims"]
    if isinstance(raw, list):
        return raw
    raise ValueError("json intake file must be a list or contain an entries array")


def normalize_rows(rows: list[dict], default_amount: str) -> list[dict]:
    if not rows:
        raise ValueError("intake file must contain at least one row")
    normalized_by_account: dict[str, dict] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("starter cohort rows must be objects")
        address_text = row_value(row, "account", "address", "wallet", "recipient")
        if not address_text:
            raise ValueError(f"missing account on row {index + 1}")
        account = normalize_address(address_text)
        if account in normalized_by_account:
            continue
        normalized_by_account[account] = {
            "account": account,
            "amount": normalize_amount(row_value(row, "amount", "drw_amount", "allocation"), default_amount),
            "label": row_value(row, "label", "handle", "nickname", "name"),
            "source": row_value(row, "source", "channel", "campaign"),
            "notes": row_value(row, "notes", "note", "comment"),
            "lane": row_value(row, "lane", "network"),
        }
    return sorted(normalized_by_account.values(), key=lambda item: item["account"])


def main() -> int:
    args = parse_args()
    intake_path = Path(args.intake_file).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    input_format = infer_input_format(intake_path, args.format)
    rows = load_rows(intake_path, input_format)
    normalized = normalize_rows(rows, str(int(args.default_amount)))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["account", "amount", "label", "source", "notes", "lane"])
        writer.writeheader()
        writer.writerows(normalized)

    print("[starter-cohort] ready")
    print(f"  intake_file: {intake_path}")
    print(f"  format:      {input_format}")
    print(f"  out:         {out_path}")
    print(f"  recipients:  {len(normalized)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
