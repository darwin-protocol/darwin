"""S1 Batch 5s — sealed batch auction species.

Groups intents into 5-second windows. Clears at median price.
Lower fee than S0 (batch crossing reduces MEV).
"""

from __future__ import annotations

from collections import defaultdict
from statistics import median

from darwin_sim.core.types import (
    IntentRecord, FillResult, Side, RouteReason,
    from_x18, to_x18, sha256_id, BPS,
)


class S1Batch5s:
    species_id = "S1_BATCH_5S"

    def __init__(self, batch_window_sec: int = 5, fee_floor_bps: float = 2.0):
        self.batch_window_sec = batch_window_sec
        self.fee_floor_bps = fee_floor_bps

    def run(self, intents: list[IntentRecord], is_control: bool = False) -> list[FillResult]:
        # Group by batch window
        batches: dict[int, list[IntentRecord]] = defaultdict(list)
        for intent in intents:
            window = intent.ts - (intent.ts % self.batch_window_sec)
            batches[window].append(intent)

        fills: list[FillResult] = []
        for window_start, batch in sorted(batches.items()):
            # Clearing price = median of source prices in the batch
            prices = [from_x18(i.source_price_x18) for i in batch]
            clearing_price = median(prices)
            batch_id = f"batch:{window_start}"

            for intent in batch:
                source_price = from_x18(intent.source_price_x18)
                limit_price = from_x18(intent.limit_price_x18)
                qty = from_x18(intent.qty_base_x18)

                # Check fillability against limit price
                if intent.side == Side.BUY:
                    fillable = clearing_price <= limit_price
                else:
                    fillable = clearing_price >= limit_price

                filled_qty = qty if fillable else 0.0
                notional = filled_qty * clearing_price
                # Lower fee than S0 — batch crossing reduces MEV
                fee = max(notional * self.fee_floor_bps / BPS, notional * 0.00035)

                fills.append(FillResult(
                    fill_id=sha256_id(f"{self.species_id}:{intent.intent_id}:{window_start}"),
                    species_id=self.species_id,
                    intent_id=intent.intent_id,
                    batch_id=batch_id,
                    acct_id=intent.acct_id,
                    pair_id=intent.pair_id,
                    ts=window_start + self.batch_window_sec,
                    side=intent.side,
                    qty_filled_x18=to_x18(filled_qty),
                    exec_price_x18=to_x18(clearing_price),
                    source_price_x18=intent.source_price_x18,
                    notional_x18=to_x18(notional),
                    fee_paid_x18=to_x18(fee),
                    profile=intent.profile,
                    is_control=is_control,
                    fill_rate_bps=BPS if fillable else 0,
                    success=fillable,
                ))
        return fills
