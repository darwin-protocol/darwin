"""S0 Sentinel — baseline CLAMM control species.

Fills every intent at source price with a fee floor.
100% fill rate by design — this is the conservative benchmark.
"""

from __future__ import annotations

from darwin_sim.core.types import IntentRecord, FillResult, Side, from_x18, to_x18, sha256_id, BPS


class S0Sentinel:
    species_id = "S0_SENTINEL"

    def __init__(self, fee_floor_bps: float = 2.0):
        self.fee_floor_bps = fee_floor_bps

    def run(self, intents: list[IntentRecord], is_control: bool = False) -> list[FillResult]:
        fills: list[FillResult] = []
        for intent in intents:
            qty = from_x18(intent.qty_base_x18)
            price = from_x18(intent.source_price_x18)
            notional = qty * price
            fee = max(notional * self.fee_floor_bps / BPS, notional * 0.0005)

            fills.append(FillResult(
                fill_id=sha256_id(f"{self.species_id}:{intent.intent_id}"),
                species_id=self.species_id,
                intent_id=intent.intent_id,
                batch_id=f"immediate:{intent.ts}",
                acct_id=intent.acct_id,
                pair_id=intent.pair_id,
                ts=intent.ts,
                side=intent.side,
                qty_filled_x18=intent.qty_base_x18,
                exec_price_x18=intent.source_price_x18,
                source_price_x18=intent.source_price_x18,
                notional_x18=to_x18(notional),
                fee_paid_x18=to_x18(fee),
                profile=intent.profile,
                is_control=is_control,
                fill_rate_bps=BPS,
                success=True,
            ))
        return fills
