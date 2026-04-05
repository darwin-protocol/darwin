"""Synthesize IntentRecords from normalized swap data."""

from __future__ import annotations

from darwin_sim.core.types import NormalizedSwap, IntentRecord, Side, from_x18, to_x18, sha256_id

# (profile_name, notional_upper_usd, slippage_bps, ttl_sec)
PROFILE_RULES = [
    ("FAST", 3000.0, 100, 60),
    ("BALANCED", 7000.0, 50, 180),
    ("PRIVATE", 12000.0, 30, 240),
    ("PATIENT", float("inf"), 20, 300),
]


def choose_profile(notional_usd: float) -> tuple[str, int, int]:
    for name, upper, slippage, ttl in PROFILE_RULES:
        if notional_usd < upper:
            return name, slippage, ttl
    return "BALANCED", 50, 180


def synthesize_intents(swaps: list[NormalizedSwap]) -> list[IntentRecord]:
    intents: list[IntentRecord] = []
    for swap in swaps:
        notional = from_x18(swap.qty_quote_x18)
        source_price = from_x18(swap.exec_price_x18)
        profile, max_slippage_bps, ttl = choose_profile(notional)

        if swap.side == Side.BUY:
            limit_price = source_price * (1.0 + max_slippage_bps / 10_000)
        else:
            limit_price = source_price * (1.0 - max_slippage_bps / 10_000)

        intent_id = sha256_id(f"{swap.event_id}:{profile}:{swap.acct_id}")
        intents.append(IntentRecord(
            intent_id=intent_id,
            acct_id=swap.acct_id,
            pair_id=swap.pair_id,
            ts=swap.ts,
            side=swap.side,
            qty_base_x18=swap.qty_base_x18,
            notional_quote_x18=swap.qty_quote_x18,
            source_event_id=swap.event_id,
            source_price_x18=swap.exec_price_x18,
            profile=profile,
            max_slippage_bps=max_slippage_bps,
            limit_price_x18=to_x18(limit_price),
            expiry_ts=swap.ts + ttl,
            bucket_id=profile,
        ))
    return intents
