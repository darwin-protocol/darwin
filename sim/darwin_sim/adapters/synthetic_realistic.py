"""Generate realistic synthetic Uniswap V3-like swap data with regime changes.

Produces 10,000+ swaps across multiple volatility regimes for E1-E7 experiments.
"""

from __future__ import annotations

import csv
import hashlib
import math
from pathlib import Path
from random import Random

from darwin_sim.core.types import RawSwapEvent


def _regime_vol(regime: str) -> float:
    """Annualized vol → per-step (4-second) vol."""
    annual = {"low": 0.30, "medium": 0.60, "high": 1.20, "crash": 2.50}
    v = annual.get(regime, 0.60)
    steps_per_year = 365.25 * 24 * 3600 / 4
    return v / math.sqrt(steps_per_year)


def generate_realistic_swaps(
    n_swaps: int = 10_000,
    seed: int = 2026,
    pair_id: str = "ETH_USDC",
    base_price: float = 3500.0,
    start_ts: int = 1711929600,  # 2024-04-01
) -> list[RawSwapEvent]:
    """Generate realistic swap data with volatility regime changes."""
    rng = Random(seed)
    events: list[RawSwapEvent] = []
    price = base_price
    acct_pool = [f"acct-{i:03d}" for i in range(1, 201)]
    ts = start_ts

    # Define regime schedule (fraction of total swaps)
    regimes = [
        (0.00, 0.25, "low"),       # first 25%: calm market
        (0.25, 0.45, "medium"),    # next 20%: normal
        (0.45, 0.55, "high"),      # 10%: volatile spike
        (0.55, 0.65, "crash"),     # 10%: crash/recovery
        (0.65, 0.80, "medium"),    # 15%: back to normal
        (0.80, 1.00, "low"),       # last 20%: calm again
    ]

    for i in range(n_swaps):
        frac = i / n_swaps
        regime = "medium"
        for start_f, end_f, r in regimes:
            if start_f <= frac < end_f:
                regime = r
                break

        step_vol = _regime_vol(regime)

        # Crash regime has a downward drift
        drift = -0.0003 if regime == "crash" else 0.0
        ret = rng.gauss(drift, step_vol)
        price *= (1 + ret)
        price = max(price, 100.0)  # floor

        # Random interval 2-8 seconds
        ts += rng.randint(2, 8)

        # Side: slight buy bias in low vol, sell bias in crash
        if regime == "crash":
            side = "SELL" if rng.random() < 0.65 else "BUY"
        elif regime == "low":
            side = "BUY" if rng.random() < 0.55 else "SELL"
        else:
            side = "BUY" if rng.random() < 0.50 else "SELL"

        # Order size: log-normal, regime-dependent
        if regime in ("high", "crash"):
            qty_base = rng.lognormvariate(0.5, 1.2)  # bigger trades in vol
        else:
            qty_base = rng.lognormvariate(-0.3, 1.0)

        qty_base = max(0.001, min(qty_base, 50.0))
        qty_quote = qty_base * price

        # Fee: 5 bps base, higher in volatile regimes
        fee_bps = {"low": 5, "medium": 5, "high": 10, "crash": 15}[regime]
        fee_paid = qty_quote * fee_bps / 10_000

        tx_hash = hashlib.md5(f"tx_{seed}_{i}".encode()).hexdigest()
        acct_id = rng.choice(acct_pool)

        events.append(RawSwapEvent(
            tx_hash=tx_hash,
            log_index=i % 10,
            pair_id=pair_id,
            ts=ts,
            side=side,
            qty_base=round(qty_base, 6),
            qty_quote=round(qty_quote, 6),
            exec_price=round(price, 6),
            fee_paid=round(fee_paid, 6),
            acct_id=acct_id,
        ))

    return events


def write_swaps_csv(events: list[RawSwapEvent], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["tx_hash", "log_index", "pair_id", "ts", "side",
                     "qty_base", "qty_quote", "exec_price", "fee_paid", "acct_id"])
        for e in events:
            w.writerow([e.tx_hash, e.log_index, e.pair_id, e.ts, e.side,
                         e.qty_base, e.qty_quote, e.exec_price, e.fee_paid, e.acct_id])


if __name__ == "__main__":
    events = generate_realistic_swaps(10_000)
    write_swaps_csv(events, "data/raw/realistic_10k.csv")
    prices = [e.exec_price for e in events]
    print(f"Generated {len(events)} swaps")
    print(f"Price range: ${min(prices):.2f} - ${max(prices):.2f}")
    print(f"Time span: {events[-1].ts - events[0].ts} seconds ({(events[-1].ts - events[0].ts)/3600:.1f} hours)")
