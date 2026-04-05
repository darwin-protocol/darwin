"""Watcher replay verifier — independent score reconstruction from published artifacts.

This is the core challengeability test: can an independent watcher reproduce
the score report from the published fills, intents, and oracle data?

If this fails, the network is not operator-ready.
"""

from __future__ import annotations

import json
from pathlib import Path

from darwin_sim.core.types import FillResult, Side, from_x18, BPS
from darwin_sim.scoring.fitness import cohort_metrics


def load_fills_ndjson(path: Path) -> list[dict]:
    """Load fill records from NDJSON."""
    fills = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                fills.append(json.loads(line))
    return fills


def _dict_to_fill(d: dict) -> FillResult:
    """Reconstruct a FillResult from a serialized dict."""
    return FillResult(
        fill_id=d.get("fill_id", ""),
        species_id=d.get("species_id", ""),
        intent_id=d.get("intent_id", ""),
        batch_id=d.get("batch_id", ""),
        acct_id=d.get("acct_id", ""),
        pair_id=d.get("pair_id", ""),
        ts=d.get("ts", 0),
        side=Side.BUY if d.get("side", "BUY") == "BUY" else Side.SELL,
        qty_filled_x18=d.get("qty_filled_x18", 0),
        exec_price_x18=d.get("exec_price_x18", 0),
        source_price_x18=d.get("source_price_x18", 0),
        notional_x18=d.get("notional_x18", 0),
        fee_paid_x18=d.get("fee_paid_x18", 0),
        profile=d.get("profile", ""),
        is_control=d.get("is_control", False),
        fill_rate_bps=d.get("fill_rate_bps", BPS),
        success=d.get("success", True),
        trader_surplus_x18=d.get("trader_surplus_x18", 0),
        adverse_markout_x18=d.get("adverse_markout_x18", 0),
        revenue_x18=d.get("revenue_x18", 0),
    )


def replay_and_verify(artifact_dir: str | Path, tolerance_bps: float = 0.5) -> dict:
    """Replay score computation from published artifacts and verify against the report.

    This is what an independent watcher does:
    1. Load the published fills (NDJSON)
    2. Recompute cohort metrics independently
    3. Compare against the published report
    4. Flag any mismatches
    """
    artifact_dir = Path(artifact_dir)
    mismatches: list[dict] = []

    # Load published report
    report_path = artifact_dir / "e2_report.json"
    if not report_path.exists():
        return {"passed": False, "error": "e2_report.json not found", "mismatches": []}

    with report_path.open() as f:
        published_report = json.loads(f.read())

    # Load published fills
    control_path = artifact_dir / "fills_control_s0.ndjson"
    treatment_path = artifact_dir / "fills_treatment_s1.ndjson"

    if not control_path.exists() or not treatment_path.exists():
        return {"passed": False, "error": "Fill artifacts missing", "mismatches": []}

    control_dicts = load_fills_ndjson(control_path)
    treatment_dicts = load_fills_ndjson(treatment_path)

    control_fills = [_dict_to_fill(d) for d in control_dicts]
    treatment_fills = [_dict_to_fill(d) for d in treatment_dicts]

    # Recompute metrics independently
    recomputed_ctrl = cohort_metrics(control_fills)
    recomputed_treat = cohort_metrics(treatment_fills)
    recomputed_uplift = {
        "trader_surplus_bps": recomputed_treat["trader_surplus_bps"] - recomputed_ctrl["trader_surplus_bps"],
        "fill_rate_bps": recomputed_treat["fill_rate_bps"] - recomputed_ctrl["fill_rate_bps"],
        "adverse_markout_bps": recomputed_treat["adverse_markout_bps"] - recomputed_ctrl["adverse_markout_bps"],
        "revenue_bps": recomputed_treat["revenue_bps"] - recomputed_ctrl["revenue_bps"],
    }

    # Compare against published report
    published_uplift = published_report.get("uplift", {})

    for metric in ["trader_surplus_bps", "fill_rate_bps", "adverse_markout_bps", "revenue_bps"]:
        published_val = published_uplift.get(metric, 0)
        recomputed_val = recomputed_uplift[metric]
        diff = abs(published_val - recomputed_val)

        if diff > tolerance_bps:
            mismatches.append({
                "metric": metric,
                "published": round(published_val, 4),
                "recomputed": round(recomputed_val, 4),
                "diff_bps": round(diff, 4),
                "tolerance_bps": tolerance_bps,
            })

    # Verify counts
    pub_counts = published_report.get("counts", {})
    if pub_counts.get("control_fills", 0) != len(control_fills):
        mismatches.append({
            "metric": "control_fill_count",
            "published": pub_counts.get("control_fills"),
            "recomputed": len(control_fills),
        })
    if pub_counts.get("treatment_fills", 0) != len(treatment_fills):
        mismatches.append({
            "metric": "treatment_fill_count",
            "published": pub_counts.get("treatment_fills"),
            "recomputed": len(treatment_fills),
        })

    # Verify decision matches
    pub_decision = published_report.get("decision", "")
    recomputed_decision = "PASS" if recomputed_uplift["trader_surplus_bps"] > 0 and recomputed_uplift["revenue_bps"] >= -5 else "REWORK"
    if pub_decision != recomputed_decision:
        mismatches.append({
            "metric": "decision",
            "published": pub_decision,
            "recomputed": recomputed_decision,
        })

    passed = len(mismatches) == 0

    return {
        "passed": passed,
        "artifact_dir": str(artifact_dir),
        "control_fills_loaded": len(control_fills),
        "treatment_fills_loaded": len(treatment_fills),
        "recomputed_uplift": {k: round(v, 4) for k, v in recomputed_uplift.items()},
        "published_uplift": published_uplift,
        "recomputed_decision": recomputed_decision,
        "published_decision": pub_decision,
        "mismatches": mismatches,
        "tolerance_bps": tolerance_bps,
    }


def main():
    import sys
    artifact_dir = sys.argv[1] if len(sys.argv) > 1 else "outputs/e2"
    result = replay_and_verify(artifact_dir)

    if result["passed"]:
        print(f"[WATCHER] REPLAY PASSED — all metrics match within {result['tolerance_bps']} bps")
        print(f"  Control fills:  {result['control_fills_loaded']}")
        print(f"  Treatment fills: {result['treatment_fills_loaded']}")
        print(f"  Recomputed uplift: {result['recomputed_uplift']}")
        print(f"  Decision: {result['recomputed_decision']}")
    else:
        print(f"[WATCHER] REPLAY FAILED — {len(result['mismatches'])} mismatches!")
        for m in result["mismatches"]:
            print(f"  {m['metric']}: published={m.get('published')} recomputed={m.get('recomputed')}")

    # Write verification report
    report_path = Path(artifact_dir) / "watcher_replay.json"
    with report_path.open("w") as f:
        json.dump(result, f, indent=2)
    print(f"  Report: {report_path}")


if __name__ == "__main__":
    main()
