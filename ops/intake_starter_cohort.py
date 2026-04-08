#!/usr/bin/env python3
"""Append or upsert starter-cohort intake rows into a local intake CSV."""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from pathlib import Path

from normalize_starter_cohort import normalize_rows


FIELDNAMES = ["account", "amount", "label", "source", "notes", "lane"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in", dest="input_file", default="", help="Optional input file with JSON or CSV rows")
    parser.add_argument("--row", default="", help="Single JSON row or CSV row to ingest")
    parser.add_argument(
        "--format",
        choices=("auto", "json", "csv"),
        default="auto",
        help="Input format for --in or --row (default: infer from content or extension)",
    )
    parser.add_argument(
        "--network",
        default=os.environ.get("DARWIN_NETWORK", "base-sepolia-recovery"),
        help="Target Darwin lane slug",
    )
    parser.add_argument(
        "--out",
        default="",
        help="Output CSV path (default: ops/state/<network>-starter-cohort-intake.csv)",
    )
    parser.add_argument(
        "--default-amount",
        default=os.environ.get("DARWIN_STARTER_COHORT_AMOUNT", "100000000000000000000"),
        help="Raw DRW amount to assign when a row omits amount",
    )
    return parser.parse_args()


def infer_input_format(raw: str, input_file: Path | None, declared_format: str) -> str:
    if declared_format != "auto":
        return declared_format
    if input_file and input_file.suffix.lower() == ".csv":
        return "csv"
    text = raw.lstrip()
    if text.startswith("{") or text.startswith("["):
        return "json"
    return "csv"


def load_rows(raw: str, input_format: str) -> list[dict]:
    if input_format == "json":
        payload = json.loads(raw)
        if isinstance(payload, dict):
            if isinstance(payload.get("entries"), list):
                return payload["entries"]
            return [payload]
        if isinstance(payload, list):
            return payload
        raise ValueError("json intake payload must be an object or a list")

    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        raise ValueError("starter cohort intake payload is empty")
    if len(lines) == 1 and not lines[0].lower().startswith("account,"):
        reader = csv.DictReader(io.StringIO(lines[0]), fieldnames=FIELDNAMES)
    else:
        reader = csv.DictReader(io.StringIO("\n".join(lines)))
    return list(reader)


def load_existing_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    input_path = Path(args.input_file).expanduser().resolve() if args.input_file else None
    out_path = Path(args.out).expanduser().resolve() if args.out else (
        repo_root / "ops" / "state" / f"{args.network}-starter-cohort-intake.csv"
    )

    if args.row:
        raw = args.row
    elif input_path:
        raw = input_path.read_text()
    else:
        raw = sys.stdin.read()

    if not raw.strip():
        raise SystemExit("starter cohort intake is empty")

    input_format = infer_input_format(raw, input_path, args.format)
    incoming_rows = load_rows(raw, input_format)
    normalized_new = normalize_rows(incoming_rows, str(int(args.default_amount)))
    existing_rows = load_existing_rows(out_path)
    normalized_existing = normalize_rows(existing_rows, str(int(args.default_amount))) if existing_rows else []

    by_account = {row["account"]: row for row in normalized_existing}
    for row in normalized_new:
        row["lane"] = row["lane"] or args.network
        by_account[row["account"]] = row

    merged = sorted(by_account.values(), key=lambda item: item["account"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(merged)

    print("[starter-cohort-intake] ready")
    print(f"  network:    {args.network}")
    print(f"  format:     {input_format}")
    print(f"  out:        {out_path}")
    print(f"  recipients: {len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
