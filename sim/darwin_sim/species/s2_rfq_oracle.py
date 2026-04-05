"""S2 RFQ Oracle — solver-quoted species anchored to oracle price.

Simulates a bonded solver that quotes around oracle price with a spread.
Better for larger orders. Occasionally fails to fill (solver timeout/reject).
"""

from __future__ import annotations

from random import Random

from darwin_sim.core.types import (
    IntentRecord, FillResult, Side, RouteReason,
    from_x18, to_x18, sha256_id, BPS,
)


class S2RfqOracle:
    species_id = "S2_RFQ_ORACLE"

    def __init__(self, fee_floor_bps: float = 2.0, spread_bps: float = 3.0, seed: int = 42):
        self.fee_floor_bps = fee_floor_bps
        self.spread_bps = spread_bps
        self.rng = Random(seed)

    def run(self, intents: list[IntentRecord], is_control: bool = False) -> list[FillResult]:
        fills: list[FillResult] = []
        for intent in intents:
            source_price = from_x18(intent.source_price_x18)
            qty = from_x18(intent.qty_base_x18)
            limit_price = from_x18(intent.limit_price_x18)

            # Solver quotes around source price with a small improvement
            # Larger orders get slightly worse spread (market impact)
            notional = qty * source_price
            size_penalty_bps = min(notional / 50_000 * 2, 5)  # up to 5 bps for $50k+
            spread = (self.spread_bps + size_penalty_bps) / BPS

            # Solver occasionally can't fill (5% reject rate)
            if self.rng.random() < 0.05:
                fills.append(FillResult(
                    fill_id=sha256_id(f"{self.species_id}:{intent.intent_id}"),
                    species_id=self.species_id,
                    intent_id=intent.intent_id,
                    batch_id=f"rfq:{intent.ts}",
                    acct_id=intent.acct_id,
                    pair_id=intent.pair_id,
                    ts=intent.ts,
                    side=intent.side,
                    qty_filled_x18=0,
                    exec_price_x18=intent.source_price_x18,
                    source_price_x18=intent.source_price_x18,
                    notional_x18=0,
                    fee_paid_x18=0,
                    profile=intent.profile,
                    is_control=is_control,
                    fill_rate_bps=0,
                    success=False,
                ))
                continue

            # RFQ quotes: slightly better than source for the user
            if intent.side == Side.BUY:
                exec_price = source_price * (1 - spread * 0.3)  # 30% of spread as improvement
            else:
                exec_price = source_price * (1 + spread * 0.3)

            # Check fillability
            if intent.side == Side.BUY and exec_price > limit_price:
                fills.append(FillResult(
                    fill_id=sha256_id(f"{self.species_id}:{intent.intent_id}"),
                    species_id=self.species_id,
                    intent_id=intent.intent_id,
                    batch_id=f"rfq:{intent.ts}",
                    acct_id=intent.acct_id,
                    pair_id=intent.pair_id,
                    ts=intent.ts,
                    side=intent.side,
                    success=False,
                    fill_rate_bps=0,
                    profile=intent.profile,
                    is_control=is_control,
                ))
                continue
            if intent.side == Side.SELL and exec_price < limit_price:
                fills.append(FillResult(
                    fill_id=sha256_id(f"{self.species_id}:{intent.intent_id}"),
                    species_id=self.species_id,
                    intent_id=intent.intent_id,
                    batch_id=f"rfq:{intent.ts}",
                    acct_id=intent.acct_id,
                    pair_id=intent.pair_id,
                    ts=intent.ts,
                    side=intent.side,
                    success=False,
                    fill_rate_bps=0,
                    profile=intent.profile,
                    is_control=is_control,
                ))
                continue

            filled_notional = qty * exec_price
            fee = max(filled_notional * self.fee_floor_bps / BPS, filled_notional * 0.0002)

            fills.append(FillResult(
                fill_id=sha256_id(f"{self.species_id}:{intent.intent_id}"),
                species_id=self.species_id,
                intent_id=intent.intent_id,
                batch_id=f"rfq:{intent.ts}",
                acct_id=intent.acct_id,
                pair_id=intent.pair_id,
                ts=intent.ts,
                side=intent.side,
                qty_filled_x18=intent.qty_base_x18,
                exec_price_x18=to_x18(exec_price),
                source_price_x18=intent.source_price_x18,
                notional_x18=to_x18(filled_notional),
                fee_paid_x18=to_x18(fee),
                profile=intent.profile,
                is_control=is_control,
                fill_rate_bps=BPS,
                success=True,
            ))
        return fills
