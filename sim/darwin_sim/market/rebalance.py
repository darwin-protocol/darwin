"""Rebalance controller — 4-mode drift detection per batch."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from darwin_sim.core.types import FillResult, RebalanceLeaf, RebalanceMode, from_x18, to_x18


def compute_rebalance_leaves(
    fills: list[FillResult],
    soft_idle_drift_bps: float = 15,
    soft_rebalance_bps: float = 50,
    hard_rebalance_bps: float = 200,
    gain_bps: float = 2500,
) -> list[RebalanceLeaf]:
    kappa_reb = gain_bps / 10_000  # MUST decode this way

    grouped: dict[tuple[str, str], list[FillResult]] = defaultdict(list)
    for f in fills:
        if f.success:
            grouped[(f.species_id, f.batch_id)].append(f)

    leaves: list[RebalanceLeaf] = []
    for (species_id, batch_id), batch_fills in sorted(grouped.items()):
        source_prices = [from_x18(f.source_price_x18) for f in batch_fills]
        exec_prices = [from_x18(f.exec_price_x18) for f in batch_fills]
        if not source_prices or not exec_prices:
            continue

        ref = mean(source_prices)
        exec_mean = mean(exec_prices)
        drift_bps = abs(exec_mean - ref) / ref * 10_000 if ref > 0 else 0.0

        if drift_bps <= soft_idle_drift_bps:
            mode = RebalanceMode.NONE
        elif drift_bps <= soft_rebalance_bps:
            mode = RebalanceMode.GRADUAL
        elif drift_bps < hard_rebalance_bps:
            mode = RebalanceMode.FORCED
        else:
            mode = RebalanceMode.HARD_RESET

        correction = exec_mean + (ref - exec_mean) * kappa_reb if mode != RebalanceMode.NONE else exec_mean

        leaves.append(RebalanceLeaf(
            batch_id=batch_id,
            species_id=species_id,
            ref_price_x18=to_x18(ref),
            drift_bps=drift_bps,
            mode=mode,
            kappa_reb=kappa_reb,
            correction_price_x18=to_x18(correction),
        ))
    return leaves
