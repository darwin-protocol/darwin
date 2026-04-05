"""DARWIN E2 batch-lane uplift experiment — end-to-end real-data pipeline.

Merges v0.8 real-data flow with v0.4 scoring engine.
Pipeline: CSV → normalize → synthesize intents → A/B split → S0 + S1 → enrich → score → decide
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

from darwin_sim.core.config import SimConfig
from darwin_sim.core.types import from_x18, RebalanceMode
from darwin_sim.adapters.uniswap_v3_csv import load_raw_swaps
from darwin_sim.normalize.pipeline import normalize_swaps
from darwin_sim.intents.synth import synthesize_intents
from darwin_sim.routing.control import split_control_treatment
from darwin_sim.species.s0_sentinel import S0Sentinel
from darwin_sim.species.s1_batch import S1Batch5s
from darwin_sim.scoring.fitness import (
    build_post_price_lookup, enrich_fills, build_score_report, compute_fitness,
)
from darwin_sim.market.rebalance import compute_rebalance_leaves


def write_ndjson(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")


def run_e2(cfg: SimConfig, data_path: str | Path, out_dir: str | Path) -> dict:
    """Run E2 batch-lane uplift experiment."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pair_id = cfg.pairs[0]

    print(f"[E2] Loading {data_path} pair={pair_id}")

    # 1. Load raw data
    raw = load_raw_swaps(data_path, pair_id)
    print(f"[E2] Raw swaps: {len(raw)}")

    # 2. Normalize
    normalized = normalize_swaps(raw)
    print(f"[E2] Normalized: {len(normalized)}")

    # 3. Synthesize intents
    intents = synthesize_intents(normalized)
    print(f"[E2] Intents: {len(intents)}")

    # 4. A/B split
    control_share = cfg.epochs.control_share_bps_default
    control_intents, treatment_intents = split_control_treatment(intents, control_share)
    print(f"[E2] Control: {len(control_intents)} | Treatment: {len(treatment_intents)} "
          f"({control_share/100:.1f}% control)")

    # 5. Execute species
    s0 = S0Sentinel(fee_floor_bps=cfg.scoring.fee_floor_bps)
    s1 = S1Batch5s(
        batch_window_sec=cfg.species[1].batch_window_sec if len(cfg.species) > 1 else 5,
        fee_floor_bps=cfg.scoring.fee_floor_bps,
    )

    control_fills = s0.run(control_intents, is_control=True)
    treatment_fills = s1.run(treatment_intents, is_control=False)
    print(f"[E2] Control fills: {len(control_fills)} | Treatment fills: {len(treatment_fills)}")

    # 6. Enrich fills with trader surplus, adverse markout, revenue
    post_prices = build_post_price_lookup(normalized)
    intent_to_source = {i.intent_id: i.source_event_id for i in intents}

    control_fills = enrich_fills(
        control_fills, post_prices, intent_to_source,
        protocol_take_rate=0.15,
        protocol_notional_floor_bps=cfg.scoring.protocol_notional_floor_bps,
    )
    treatment_fills = enrich_fills(
        treatment_fills, post_prices, intent_to_source,
        protocol_take_rate=0.15,
        protocol_notional_floor_bps=cfg.scoring.protocol_notional_floor_bps,
    )

    # 7. Rebalance
    rebalance_leaves = compute_rebalance_leaves(
        treatment_fills,
        soft_idle_drift_bps=cfg.rebalance.soft_idle_drift_bps,
        soft_rebalance_bps=cfg.rebalance.soft_rebalance_bps,
        hard_rebalance_bps=cfg.rebalance.hard_rebalance_bps,
        gain_bps=cfg.rebalance.gain_bps,
    )

    hard_resets = sum(1 for rl in rebalance_leaves if rl.mode == RebalanceMode.HARD_RESET)
    print(f"[E2] Rebalance leaves: {len(rebalance_leaves)} (hard resets: {hard_resets})")

    # 8. Score
    score_report = build_score_report(control_fills, treatment_fills)
    total = score_report["TOTAL"]
    uplift = total["uplift"]
    fitness = compute_fitness(uplift)

    # 9. Decision
    ts_uplift = uplift["trader_surplus_bps"]
    rev_uplift = uplift["revenue_bps"]
    fr_uplift = uplift["fill_rate_bps"]
    if ts_uplift > 0 and rev_uplift >= -5:  # allow tiny revenue dip if surplus is positive
        decision = "PASS"
    else:
        decision = "REWORK"

    # 10. Write artifacts
    def fill_to_dict(f):
        d = {}
        for k in f.__dataclass_fields__:
            v = getattr(f, k)
            d[k] = v.name if hasattr(v, 'name') else v
        return d

    def rl_to_dict(rl):
        d = {}
        for k in rl.__dataclass_fields__:
            v = getattr(rl, k)
            d[k] = v.name if hasattr(v, 'name') else v
        return d

    write_ndjson(out_dir / "fills_control_s0.ndjson", [fill_to_dict(f) for f in control_fills])
    write_ndjson(out_dir / "fills_treatment_s1.ndjson", [fill_to_dict(f) for f in treatment_fills])
    write_ndjson(out_dir / "rebalance.ndjson", [rl_to_dict(rl) for rl in rebalance_leaves])

    result = {
        "experiment": "E2_batch_lane_uplift",
        "suite_id": cfg.suite_id,
        "pair": pair_id,
        "data_file": str(data_path),
        "counts": {
            "raw_swaps": len(raw),
            "normalized": len(normalized),
            "intents": len(intents),
            "control_intents": len(control_intents),
            "treatment_intents": len(treatment_intents),
            "control_fills": len(control_fills),
            "treatment_fills": len(treatment_fills),
            "rebalance_leaves": len(rebalance_leaves),
            "hard_resets": hard_resets,
        },
        "decision": decision,
        "fitness": round(fitness, 6),
        "uplift": {k: round(v, 4) for k, v in uplift.items()},
        "score_report": {
            bucket: {
                "control": {k: round(v, 4) if isinstance(v, float) else v for k, v in data["control"].items()},
                "treatment": {k: round(v, 4) if isinstance(v, float) else v for k, v in data["treatment"].items()},
                "uplift": {k: round(v, 4) for k, v in data["uplift"].items()},
            }
            for bucket, data in score_report.items()
        },
    }

    with (out_dir / "e2_report.json").open("w") as f:
        json.dump(result, f, indent=2)

    # Markdown report
    write_markdown_report(out_dir / "e2_report.md", result)

    return result


def write_markdown_report(path: Path, result: dict) -> None:
    total = result["score_report"]["TOTAL"]
    lines = [
        "# DARWIN E2: Batch-Lane Uplift Report",
        "",
        f"**Decision: {result['decision']}**",
        f"**Fitness: {result['fitness']}**",
        "",
        "## Pipeline Counts",
        "",
    ]
    for k, v in result["counts"].items():
        lines.append(f"- {k}: {v}")

    lines += [
        "",
        "## TOTAL Uplift (S1_BATCH_5S vs S0_SENTINEL control)",
        "",
        "| Metric | Control | Treatment | Uplift |",
        "|---|---:|---:|---:|",
    ]
    for metric in ["trader_surplus_bps", "fill_rate_bps", "adverse_markout_bps", "revenue_bps"]:
        c = total["control"][metric]
        t = total["treatment"][metric]
        u = total["uplift"][metric]
        lines.append(f"| {metric} | {c:.2f} | {t:.2f} | {u:+.2f} |")

    lines += ["", "## By Bucket", ""]
    for bucket, data in result["score_report"].items():
        if bucket == "TOTAL":
            continue
        lines.append(f"### {bucket} (n={data['control']['count']}c / {data['treatment']['count']}t)")
        lines.append("")
        lines.append("| Metric | Control | Treatment | Uplift |")
        lines.append("|---|---:|---:|---:|")
        for metric in ["trader_surplus_bps", "fill_rate_bps", "adverse_markout_bps", "revenue_bps"]:
            c = data["control"][metric]
            t = data["treatment"][metric]
            u = data["uplift"][metric]
            lines.append(f"| {metric} | {c:.2f} | {t:.2f} | {u:+.2f} |")
        lines.append("")

    path.write_text("\n".join(lines))


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/baseline.yaml"
    data_path = sys.argv[2] if len(sys.argv) > 2 else "data/raw/raw_swaps.csv"
    out_dir = sys.argv[3] if len(sys.argv) > 3 else "outputs/e2"

    cfg = SimConfig.from_yaml(config_path)
    t0 = time.time()
    result = run_e2(cfg, data_path, out_dir)
    elapsed = time.time() - t0

    print(f"\n{'='*60}")
    print(f"[E2] Decision: {result['decision']}")
    print(f"[E2] Fitness:  {result['fitness']}")
    print(f"[E2] Uplift:   TS={result['uplift']['trader_surplus_bps']:+.2f}bps  "
          f"FR={result['uplift']['fill_rate_bps']:+.2f}bps  "
          f"ADV={result['uplift']['adverse_markout_bps']:+.2f}bps  "
          f"REV={result['uplift']['revenue_bps']:+.2f}bps")
    print(f"[E2] Done in {elapsed:.2f}s → {out_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
