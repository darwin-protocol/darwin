"""Load Uniswap V3 swap data from CSV into typed RawSwapEvent objects."""

from __future__ import annotations

import csv
from pathlib import Path

from darwin_sim.core.types import RawSwapEvent


def load_raw_swaps(path: str | Path, pair_id: str | None = None) -> list[RawSwapEvent]:
    events: list[RawSwapEvent] = []
    with open(path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if pair_id and row["pair_id"] != pair_id:
                continue
            events.append(RawSwapEvent(
                tx_hash=row["tx_hash"],
                log_index=int(row["log_index"]),
                pair_id=row["pair_id"],
                ts=int(row["ts"]),
                side=row["side"].upper(),
                qty_base=float(row["qty_base"]),
                qty_quote=float(row["qty_quote"]),
                exec_price=float(row["exec_price"]),
                fee_paid=float(row["fee_paid"]),
                acct_id=row.get("acct_id") or f"acct-{row['tx_hash'][:10]}",
            ))
    return sorted(events, key=lambda e: (e.ts, e.log_index))
