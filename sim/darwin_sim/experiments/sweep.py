"""Parameter sweep and multi-epoch evolution experiment.

Sweeps beta/epsilon for the replicator dynamics and runs a multi-epoch
evolution loop to prove species weights converge.
"""

from __future__ import annotations

import json
import math
import time
from collections import defaultdict
from pathlib import Path

from darwin_sim.core.config import SimConfig
from darwin_sim.core.types import (
    IntentRecord, FillResult, NormalizedSwap, Side,
    from_x18, to_x18, BPS,
)
from darwin_sim.adapters.synthetic_realistic import generate_realistic_swaps
from darwin_sim.normalize.pipeline import normalize_swaps
from darwin_sim.intents.synth import synthesize_intents
from darwin_sim.routing.control import split_control_treatment
from darwin_sim.species.s0_sentinel import S0Sentinel
from darwin_sim.species.s1_batch import S1Batch5s
from darwin_sim.species.s2_rfq_oracle import S2RfqOracle
from darwin_sim.scoring.fitness import (
    build_post_price_lookup, enrich_fills, cohort_metrics,
    compute_fitness, update_weights,
)


def run_multi_epoch_evolution(
    cfg: SimConfig,
    swaps: list[NormalizedSwap],
    n_epochs: int = 12,
    beta: float = 2.0,
    epsilon: float = 0.08,
) -> dict:
    """Run multi-epoch evolution with weight updates — the core DARWIN loop."""
    epoch_sec = cfg.epochs.duration_sec
    t0 = swaps[0].ts if swaps else 0

    # Initialize species
    species_impls = {
        "S0_SENTINEL": S0Sentinel(fee_floor_bps=cfg.scoring.fee_floor_bps),
        "S1_BATCH_5S": S1Batch5s(batch_window_sec=5, fee_floor_bps=cfg.scoring.fee_floor_bps),
        "S2_RFQ_ORACLE": S2RfqOracle(fee_floor_bps=cfg.scoring.fee_floor_bps),
    }

    weights = {"S0_SENTINEL": 600_000, "S1_BATCH_5S": 250_000, "S2_RFQ_ORACLE": 150_000}
    canary_set = {"S1_BATCH_5S", "S2_RFQ_ORACLE"}
    fitness_scores = {sid: 0.0 for sid in species_impls}

    # Split swaps into epochs
    epoch_swaps: dict[int, list[NormalizedSwap]] = defaultdict(list)
    for swap in swaps:
        eid = (swap.ts - t0) // epoch_sec
        if eid < n_epochs:
            epoch_swaps[eid].append(swap)

    epoch_history = []

    for epoch_id in range(min(n_epochs, max(epoch_swaps.keys()) + 1 if epoch_swaps else 0)):
        e_swaps = epoch_swaps.get(epoch_id, [])
        if len(e_swaps) < 10:
            continue

        intents = synthesize_intents(e_swaps)
        control_intents, treatment_intents = split_control_treatment(
            intents, cfg.epochs.control_share_bps_default
        )

        # Execute control
        s0 = species_impls["S0_SENTINEL"]
        control_fills = s0.run(control_intents, is_control=True)

        # Route treatment proportional to weights
        # Simplified: split treatment intents by weight proportion
        treatment_by_species: dict[str, list[IntentRecord]] = defaultdict(list)
        non_s0_weight = sum(w for sid, w in weights.items() if sid != "S0_SENTINEL")

        for intent in treatment_intents:
            # Weighted random assignment based on species weights
            r = hash(intent.intent_id) % 1_000_000
            cumulative = 0
            assigned = "S1_BATCH_5S"  # default
            for sid, w in weights.items():
                if sid == "S0_SENTINEL":
                    continue
                cumulative += w
                if r < cumulative:
                    assigned = sid
                    break
            treatment_by_species[assigned].append(intent)

        # Execute each treatment species
        all_treatment_fills: dict[str, list[FillResult]] = {}
        for sid, intents_for_species in treatment_by_species.items():
            sp = species_impls[sid]
            fills = sp.run(intents_for_species, is_control=False)
            all_treatment_fills[sid] = fills

        # Enrich
        post_prices = build_post_price_lookup(e_swaps)
        intent_to_source = {i.intent_id: i.source_event_id for i in intents}

        control_fills = enrich_fills(control_fills, post_prices, intent_to_source,
                                     protocol_notional_floor_bps=cfg.scoring.protocol_notional_floor_bps)

        for sid, fills in all_treatment_fills.items():
            all_treatment_fills[sid] = enrich_fills(fills, post_prices, intent_to_source,
                                                     protocol_notional_floor_bps=cfg.scoring.protocol_notional_floor_bps)

        # Score each species
        ctrl_metrics = cohort_metrics(control_fills)
        for sid, fills in all_treatment_fills.items():
            tm = cohort_metrics(fills)
            uplift = {
                "trader_surplus_bps": tm["trader_surplus_bps"] - ctrl_metrics["trader_surplus_bps"],
                "fill_rate_bps": tm["fill_rate_bps"] - ctrl_metrics["fill_rate_bps"],
                "adverse_markout_bps": tm["adverse_markout_bps"] - ctrl_metrics["adverse_markout_bps"],
                "revenue_bps": tm["revenue_bps"] - ctrl_metrics["revenue_bps"],
            }
            fitness_scores[sid] = compute_fitness(uplift)

        # Update weights (after warmup)
        if epoch_id >= cfg.epochs.warmup_epochs:
            weights = update_weights(
                weights, fitness_scores,
                beta=beta, epsilon=epsilon,
                canary_cap_x1e6=cfg.routing.canary_weight_cap_bps * 100,
                canary_set=canary_set,
            )

        epoch_history.append({
            "epoch": epoch_id,
            "weights": dict(weights),
            "fitness": {k: round(v, 6) for k, v in fitness_scores.items()},
            "n_intents": len(intents),
        })

    return {
        "n_epochs": len(epoch_history),
        "final_weights": dict(weights),
        "final_fitness": {k: round(v, 6) for k, v in fitness_scores.items()},
        "epochs": epoch_history,
        "params": {"beta": beta, "epsilon": epsilon},
    }


def run_parameter_sweep(cfg: SimConfig, out_dir: str | Path, n_swaps: int = 10_000, seed: int = 2026) -> dict:
    """Sweep beta and epsilon to find optimal replicator dynamics parameters."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print(f"[SWEEP] Generating {n_swaps} swaps...")
    raw = generate_realistic_swaps(n_swaps=n_swaps, seed=seed)
    swaps = normalize_swaps(raw)

    betas = [0.5, 1.0, 2.0, 3.0, 5.0]
    epsilons = [0.02, 0.05, 0.08, 0.12, 0.20]

    results = []
    for beta in betas:
        for eps in epsilons:
            r = run_multi_epoch_evolution(cfg, swaps, n_epochs=12, beta=beta, epsilon=eps)
            # Measure convergence quality
            if r["epochs"]:
                final_w = r["final_weights"]
                s1_share = final_w.get("S1_BATCH_5S", 0) / 10_000
                s2_share = final_w.get("S2_RFQ_ORACLE", 0) / 10_000
                # Herfindahl index (lower = more diverse)
                shares = [v / 1_000_000 for v in final_w.values()]
                hhi = sum(s ** 2 for s in shares)
                s1_fitness = r["final_fitness"].get("S1_BATCH_5S", 0)
                s2_fitness = r["final_fitness"].get("S2_RFQ_ORACLE", 0)
            else:
                s1_share = s2_share = hhi = s1_fitness = s2_fitness = 0

            entry = {
                "beta": beta, "epsilon": eps,
                "s1_share_pct": round(s1_share, 1),
                "s2_share_pct": round(s2_share, 1),
                "hhi": round(hhi, 4),
                "s1_fitness": s1_fitness,
                "s2_fitness": s2_fitness,
            }
            results.append(entry)
            print(f"  beta={beta:.1f} eps={eps:.2f} → S0={100-s1_share-s2_share:.1f}% "
                  f"S1={s1_share:.1f}% S2={s2_share:.1f}% HHI={hhi:.4f}")

    elapsed = time.time() - t0

    # Find best config (highest experimental species share with positive fitness)
    valid = [r for r in results if r["s1_fitness"] > 0 or r["s2_fitness"] > 0]
    if valid:
        best = max(valid, key=lambda r: r["s1_share_pct"] + r["s2_share_pct"])
    else:
        best = results[0]

    report = {
        "sweep": "beta_epsilon",
        "n_configs": len(results),
        "elapsed_sec": round(elapsed, 2),
        "best": best,
        "all_results": results,
    }

    with (out_dir / "sweep_report.json").open("w") as f:
        json.dump(report, f, indent=2)

    # Markdown
    lines = [
        "# DARWIN Parameter Sweep: Beta x Epsilon",
        "",
        f"**Configs tested:** {len(results)}",
        f"**Best:** beta={best['beta']}, epsilon={best['epsilon']}",
        f"**Runtime:** {elapsed:.1f}s",
        "",
        "| Beta | Epsilon | S0% | S1% | S2% | HHI | S1 Fitness |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        s0 = 100 - r["s1_share_pct"] - r["s2_share_pct"]
        lines.append(
            f"| {r['beta']:.1f} | {r['epsilon']:.2f} | {s0:.1f} | "
            f"{r['s1_share_pct']:.1f} | {r['s2_share_pct']:.1f} | "
            f"{r['hhi']:.4f} | {r['s1_fitness']} |"
        )
    (out_dir / "sweep_report.md").write_text("\n".join(lines))

    print(f"\n[SWEEP] Best config: beta={best['beta']}, epsilon={best['epsilon']}")
    print(f"[SWEEP] Done in {elapsed:.1f}s → {out_dir}")

    return report


def main():
    import sys
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/baseline.yaml"
    cfg = SimConfig.from_yaml(config_path)
    run_parameter_sweep(cfg, "outputs/sweep")


if __name__ == "__main__":
    main()
