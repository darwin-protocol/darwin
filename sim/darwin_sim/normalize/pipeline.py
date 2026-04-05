"""Normalize raw swap events into typed NormalizedSwap objects."""

from __future__ import annotations

from darwin_sim.core.types import RawSwapEvent, NormalizedSwap, Side, to_x18, sha256_id


def normalize_swaps(events: list[RawSwapEvent]) -> list[NormalizedSwap]:
    normalized: list[NormalizedSwap] = []
    for e in sorted(events, key=lambda x: (x.ts, x.log_index)):
        event_id = sha256_id(f"{e.tx_hash}:{e.log_index}:{e.pair_id}")
        normalized.append(NormalizedSwap(
            event_id=event_id,
            pair_id=e.pair_id,
            ts=e.ts,
            side=Side.from_str(e.side),
            qty_base_x18=to_x18(abs(e.qty_base)),
            qty_quote_x18=to_x18(abs(e.qty_quote)),
            exec_price_x18=to_x18(e.exec_price),
            fee_paid_x18=to_x18(e.fee_paid),
            acct_id=e.acct_id,
            source_tx_hash=e.tx_hash,
        ))
    return normalized
