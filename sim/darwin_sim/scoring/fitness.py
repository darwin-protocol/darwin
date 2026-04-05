"""Scoring engine — counterfactual uplift, enrichment, and cohort metrics."""

from __future__ import annotations

import math
from collections import defaultdict

from darwin_sim.core.types import (
    FillResult, NormalizedSwap, ScoreLeaf, Side,
    from_x18, to_x18, BPS,
)


def build_post_price_lookup(swaps: list[NormalizedSwap]) -> dict[str, int]:
    """Map event_id → next swap's exec_price_x18 (for markout)."""
    lookup: dict[str, int] = {}
    for idx, swap in enumerate(swaps):
        if idx + 1 < len(swaps):
            lookup[swap.event_id] = swaps[idx + 1].exec_price_x18
        else:
            lookup[swap.event_id] = swap.exec_price_x18
    return lookup


def enrich_fills(
    fills: list[FillResult],
    post_price_lookup: dict[str, int],
    intent_to_source: dict[str, str],
    protocol_take_rate: float = 0.15,
    protocol_notional_floor_bps: float = 0.5,
) -> list[FillResult]:
    """Compute trader surplus, adverse markout, and protocol revenue per fill."""
    for fill in fills:
        if not fill.success:
            continue

        exec_price = from_x18(fill.exec_price_x18)
        source_price = from_x18(fill.source_price_x18)
        filled_qty = from_x18(fill.qty_filled_x18)
        notional = from_x18(fill.notional_x18)
        fee_paid = from_x18(fill.fee_paid_x18)

        # Trader surplus: how much better than source price?
        if fill.side == Side.BUY:
            surplus = max(0.0, (source_price - exec_price) * filled_qty)
        else:
            surplus = max(0.0, (exec_price - source_price) * filled_qty)

        # Adverse markout: price move against fill direction
        source_event = intent_to_source.get(fill.intent_id, "")
        post_price_x18 = post_price_lookup.get(source_event, fill.exec_price_x18)
        post_price = from_x18(post_price_x18)

        if fill.side == Side.BUY:
            adv = max(0.0, (exec_price - post_price) * filled_qty)
        else:
            adv = max(0.0, (post_price - exec_price) * filled_qty)

        # Protocol revenue
        revenue = max(protocol_take_rate * fee_paid, notional * protocol_notional_floor_bps / BPS)

        fill.trader_surplus_x18 = to_x18(surplus)
        fill.adverse_markout_x18 = to_x18(adv)
        fill.revenue_x18 = to_x18(revenue)

    return fills


def cohort_metrics(fills: list[FillResult]) -> dict[str, float]:
    """Compute aggregate metrics for a cohort of fills."""
    if not fills:
        return {"count": 0, "trader_surplus_bps": 0, "fill_rate_bps": 0,
                "adverse_markout_bps": 0, "revenue_bps": 0}

    total_notional = sum(from_x18(f.notional_x18) for f in fills) or 1e-12
    total_requested = sum(from_x18(f.qty_filled_x18) if f.success else from_x18(f.qty_filled_x18) for f in fills) or 1e-12
    # For fill rate, count successful fills vs total
    n_success = sum(1 for f in fills if f.success)

    ts_sum = sum(from_x18(f.trader_surplus_x18) for f in fills)
    adv_sum = sum(from_x18(f.adverse_markout_x18) for f in fills)
    rev_sum = sum(from_x18(f.revenue_x18) for f in fills)

    return {
        "count": len(fills),
        "trader_surplus_bps": ts_sum / total_notional * BPS if total_notional > 0 else 0,
        "fill_rate_bps": n_success / len(fills) * BPS,
        "adverse_markout_bps": adv_sum / total_notional * BPS if total_notional > 0 else 0,
        "revenue_bps": rev_sum / total_notional * BPS if total_notional > 0 else 0,
    }


def build_score_report(
    control_fills: list[FillResult],
    treatment_fills: list[FillResult],
) -> dict:
    """Build a full score report with per-bucket and TOTAL breakdowns."""
    all_profiles = sorted(set(
        [f.profile for f in control_fills + treatment_fills] + ["TOTAL"]
    ))

    report: dict[str, dict] = {}
    for bucket in all_profiles:
        if bucket == "TOTAL":
            c_fills = control_fills
            t_fills = treatment_fills
        else:
            c_fills = [f for f in control_fills if f.profile == bucket]
            t_fills = [f for f in treatment_fills if f.profile == bucket]

        cm = cohort_metrics(c_fills)
        tm = cohort_metrics(t_fills)
        report[bucket] = {
            "control": cm,
            "treatment": tm,
            "uplift": {
                "trader_surplus_bps": tm["trader_surplus_bps"] - cm["trader_surplus_bps"],
                "fill_rate_bps": tm["fill_rate_bps"] - cm["fill_rate_bps"],
                "adverse_markout_bps": tm["adverse_markout_bps"] - cm["adverse_markout_bps"],
                "revenue_bps": tm["revenue_bps"] - cm["revenue_bps"],
            },
        }
    return report


def compute_fitness(uplift: dict[str, float], weights: dict[str, float] | None = None) -> float:
    """Composite fitness from uplift metrics (v0.4 6-weight formula)."""
    w = weights or {
        "trader_surplus": 0.35, "lp_return": 0.20, "fill_rate": 0.15,
        "revenue": 0.10, "adverse_markout": 0.12, "risk_penalty": 0.08,
    }

    def clip(v: float, cap: float = 500) -> float:
        return max(-cap, min(cap, v)) / cap

    return (
        w["trader_surplus"] * clip(uplift.get("trader_surplus_bps", 0))
        + w["fill_rate"] * clip(uplift.get("fill_rate_bps", 0))
        + w["revenue"] * clip(uplift.get("revenue_bps", 0))
        - w["adverse_markout"] * clip(uplift.get("adverse_markout_bps", 0))
    )


def update_weights(
    current: dict[str, int],
    fitness: dict[str, float],
    beta: float = 2.0,
    epsilon: float = 0.08,
    canary_cap_x1e6: int = 50_000,
    canary_set: set[str] | None = None,
) -> dict[str, int]:
    """Replicator dynamics weight update."""
    canary_set = canary_set or set()
    max_f = max(fitness.values()) if fitness else 0.0
    n = len(current)

    exp_w: dict[str, float] = {}
    for sid, w in current.items():
        a = w / 1_000_000 if w > 0 else 1.0 / n
        f = fitness.get(sid, 0.0)
        exp_w[sid] = a * math.exp(beta * (f - max_f))

    total = sum(exp_w.values()) or 1.0
    explore_mass = 1.0 / n if n > 0 else 0.0

    new: dict[str, int] = {}
    for sid in current:
        w_new = (1 - epsilon) * (exp_w[sid] / total) + epsilon * explore_mass
        w_x1e6 = int(w_new * 1_000_000)
        if sid in canary_set:
            w_x1e6 = min(w_x1e6, canary_cap_x1e6)
        new[sid] = max(w_x1e6, 1000)

    # Renormalize
    t = sum(new.values())
    if t > 0:
        for sid in new:
            new[sid] = new[sid] * 1_000_000 // t
    return new
