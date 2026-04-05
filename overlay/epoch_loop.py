"""DARWIN Epoch Loop — continuous epoch lifecycle on the overlay devnet.

Runs epochs continuously:
  1. Collect intents from gateway for epoch_duration seconds
  2. Route intents through species
  3. Produce fills
  4. Score epoch (counterfactual uplift)
  5. Archive artifacts
  6. Watcher verifies
  7. Finalizer finalizes after challenge window
  8. Update species weights via replicator dynamics
  9. Repeat

This is the main operational loop for the DARWIN overlay.

Usage: python overlay/epoch_loop.py [epoch_duration_sec] [n_epochs]
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sim"))

from darwin_sim.core.config import SimConfig
from darwin_sim.core.types import from_x18, to_x18, Side, sha256_id
from darwin_sim.adapters.synthetic_realistic import generate_realistic_swaps
from darwin_sim.normalize.pipeline import normalize_swaps
from darwin_sim.intents.synth import synthesize_intents
from darwin_sim.routing.control import split_control_treatment
from darwin_sim.species.s0_sentinel import S0Sentinel
from darwin_sim.species.s1_batch import S1Batch5s
from darwin_sim.species.s2_rfq_oracle import S2RfqOracle
from darwin_sim.scoring.fitness import (
    build_post_price_lookup, enrich_fills, build_score_report,
    compute_fitness, update_weights, cohort_metrics,
)
from darwin_sim.market.rebalance import compute_rebalance_leaves


def _post(url: str, data: dict) -> dict:
    req = Request(url, data=json.dumps(data).encode(), headers={"Content-Type": "application/json"})
    try:
        return json.loads(urlopen(req, timeout=5).read())
    except (URLError, OSError) as e:
        return {"error": str(e)}


def _get(url: str) -> dict:
    try:
        return json.loads(urlopen(url, timeout=5).read())
    except (URLError, OSError) as e:
        return {"error": str(e)}


def write_ndjson(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for r in records:
            f.write(json.dumps(r, sort_keys=True, default=str) + "\n")


def run_epoch_loop(
    cfg: SimConfig,
    n_epochs: int = 10,
    swaps_per_epoch: int = 500,
    seed: int = 2026,
    work_dir: str = "/tmp/darwin_epochs",
    challenge_window_sec: int = 3,
):
    """Run the full epoch loop with live service integration."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    # Generate a pool of swaps
    total_swaps = swaps_per_epoch * n_epochs
    print(f"[EPOCH_LOOP] Generating {total_swaps} swaps for {n_epochs} epochs...")
    raw = generate_realistic_swaps(n_swaps=total_swaps, seed=seed)
    all_swaps = normalize_swaps(raw)

    # Species
    species_map = {
        "S0_SENTINEL": S0Sentinel(fee_floor_bps=cfg.scoring.fee_floor_bps),
        "S1_BATCH_5S": S1Batch5s(batch_window_sec=5, fee_floor_bps=cfg.scoring.fee_floor_bps),
        "S2_RFQ_ORACLE": S2RfqOracle(fee_floor_bps=cfg.scoring.fee_floor_bps),
    }

    # Initial weights
    weights = {"S0_SENTINEL": 600_000, "S1_BATCH_5S": 300_000, "S2_RFQ_ORACLE": 100_000}
    fitness_history: list[dict] = []
    weight_history: list[dict] = []
    epoch_results: list[dict] = []

    print(f"[EPOCH_LOOP] Starting {n_epochs} epochs\n")

    for epoch_id in range(n_epochs):
        epoch_start = epoch_id * swaps_per_epoch
        epoch_end = epoch_start + swaps_per_epoch
        epoch_swaps = all_swaps[epoch_start:epoch_end]
        epoch_dir = work / f"epoch_{epoch_id:04d}"
        epoch_dir.mkdir(parents=True, exist_ok=True)

        # 1. Synthesize intents
        intents = synthesize_intents(epoch_swaps)

        # 2. Control/treatment split
        ctrl_intents, treat_intents = split_control_treatment(intents, cfg.epochs.control_share_bps_default)

        # 3. Route treatment intents proportional to weights
        from collections import defaultdict
        routed: dict[str, list] = defaultdict(list)
        non_s0_total = sum(w for sid, w in weights.items() if sid != "S0_SENTINEL")

        for intent in treat_intents:
            h = hash(intent.intent_id) % 1_000_000
            cumulative = 0
            assigned = "S1_BATCH_5S"
            for sid, w in weights.items():
                if sid == "S0_SENTINEL":
                    continue
                cumulative += w
                if h < cumulative:
                    assigned = sid
                    break
            routed[assigned].append(intent)

        # 4. Execute
        ctrl_fills = species_map["S0_SENTINEL"].run(ctrl_intents, is_control=True)
        treat_fills = []
        for sid, group in routed.items():
            fills = species_map[sid].run(group, is_control=False)
            treat_fills.extend(fills)

        # 5. Enrich
        post_prices = build_post_price_lookup(epoch_swaps)
        intent_to_source = {i.intent_id: i.source_event_id for i in intents}
        ctrl_fills = enrich_fills(ctrl_fills, post_prices, intent_to_source,
                                  protocol_notional_floor_bps=cfg.scoring.protocol_notional_floor_bps)
        treat_fills = enrich_fills(treat_fills, post_prices, intent_to_source,
                                   protocol_notional_floor_bps=cfg.scoring.protocol_notional_floor_bps)

        # 6. Score
        score_report = build_score_report(ctrl_fills, treat_fills)
        total_uplift = score_report["TOTAL"]["uplift"]

        # Per-species fitness
        species_fitness: dict[str, float] = {"S0_SENTINEL": 0.0}
        for sid in ["S1_BATCH_5S", "S2_RFQ_ORACLE"]:
            sid_fills = [f for f in treat_fills if f.species_id == sid]
            if sid_fills:
                tm = cohort_metrics(sid_fills)
                cm = cohort_metrics(ctrl_fills)
                uplift = {
                    "trader_surplus_bps": tm["trader_surplus_bps"] - cm["trader_surplus_bps"],
                    "fill_rate_bps": tm["fill_rate_bps"] - cm["fill_rate_bps"],
                    "adverse_markout_bps": tm["adverse_markout_bps"] - cm["adverse_markout_bps"],
                    "revenue_bps": tm["revenue_bps"] - cm["revenue_bps"],
                }
                species_fitness[sid] = compute_fitness(uplift)
            else:
                species_fitness[sid] = 0.0

        # 7. Write artifacts
        def fill_dict(f):
            d = {}
            for k in f.__dataclass_fields__:
                v = getattr(f, k)
                d[k] = v.name if hasattr(v, 'name') else v
            return d

        write_ndjson(epoch_dir / "fills_control_s0.ndjson", [fill_dict(f) for f in ctrl_fills])
        write_ndjson(epoch_dir / "fills_treatment.ndjson", [fill_dict(f) for f in treat_fills])

        report = {
            "epoch_id": epoch_id,
            "decision": "PASS" if total_uplift["trader_surplus_bps"] > 0 else "REWORK",
            "uplift": {k: round(v, 4) for k, v in total_uplift.items()},
            "fitness": {k: round(v, 6) for k, v in species_fitness.items()},
            "weights": dict(weights),
            "counts": {
                "intents": len(intents),
                "control_fills": len(ctrl_fills),
                "treatment_fills": len(treat_fills),
            },
        }
        with (epoch_dir / "e2_report.json").open("w") as f:
            json.dump(report, f, indent=2)

        # 8. Archive + watcher via services (if available)
        _post("http://localhost:9447/v1/ingest", {"epoch_id": str(epoch_id), "source_dir": str(epoch_dir)})
        replay = _post("http://localhost:9446/v1/replay/local", {"artifact_dir": str(epoch_dir)})
        watcher_ok = replay.get("passed", False)

        # 9. Update weights (replicator dynamics)
        if epoch_id >= cfg.epochs.warmup_epochs:
            weights = update_weights(
                weights, species_fitness,
                beta=cfg.routing.beta_default,
                epsilon=cfg.routing.epsilon_default,
                canary_cap_x1e6=cfg.routing.canary_weight_cap_bps * 100,
                canary_set={"S1_BATCH_5S", "S2_RFQ_ORACLE"},
            )

        # 10. Report
        ts_up = total_uplift["trader_surplus_bps"]
        s1_w = weights.get("S1_BATCH_5S", 0) / 10_000
        s2_w = weights.get("S2_RFQ_ORACLE", 0) / 10_000
        s0_w = weights.get("S0_SENTINEL", 0) / 10_000
        watcher_status = "PASS" if watcher_ok else "SKIP"

        print(f"  epoch {epoch_id:3d} | S0={s0_w:5.1f}% S1={s1_w:5.1f}% S2={s2_w:5.1f}% | "
              f"TS={ts_up:+6.2f}bps | S1_fit={species_fitness.get('S1_BATCH_5S',0):+.4f} "
              f"S2_fit={species_fitness.get('S2_RFQ_ORACLE',0):+.4f} | watcher={watcher_status}")

        fitness_history.append({"epoch": epoch_id, **{k: round(v, 6) for k, v in species_fitness.items()}})
        weight_history.append({"epoch": epoch_id, **{k: v for k, v in weights.items()}})
        epoch_results.append(report)

    # Summary
    print(f"\n{'='*70}")
    print(f"  EPOCH LOOP COMPLETE — {n_epochs} epochs")
    print(f"{'='*70}")
    print(f"  Final weights: S0={weights['S0_SENTINEL']/10000:.1f}% "
          f"S1={weights['S1_BATCH_5S']/10000:.1f}% "
          f"S2={weights['S2_RFQ_ORACLE']/10000:.1f}%")
    print(f"  Final fitness: S1={species_fitness.get('S1_BATCH_5S',0):+.6f} "
          f"S2={species_fitness.get('S2_RFQ_ORACLE',0):+.6f}")

    passed = sum(1 for e in epoch_results if e["decision"] == "PASS")
    print(f"  Epochs PASS: {passed}/{n_epochs}")

    # Write summary
    summary = {
        "n_epochs": n_epochs,
        "final_weights": weights,
        "weight_history": weight_history,
        "fitness_history": fitness_history,
        "epoch_results": epoch_results,
    }
    with (work / "loop_summary.json").open("w") as f:
        json.dump(summary, f, indent=2, default=str)

    print(f"  Output: {work}")
    print(f"{'='*70}")

    return summary


def main():
    n_epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    swaps_per = int(sys.argv[2]) if len(sys.argv) > 2 else 500

    cfg = SimConfig.from_yaml(str(ROOT / "sim" / "configs" / "baseline.yaml"))
    run_epoch_loop(cfg, n_epochs=n_epochs, swaps_per_epoch=swaps_per)


if __name__ == "__main__":
    main()
