"""DARWIN Scorer Service — computes score, weight, and rebalance roots per epoch.

Reads fills from the archive, computes counterfactual metrics, publishes roots.
This is the off-chain scoring engine that watchers verify.

Port: 9445
"""

from __future__ import annotations

import hashlib
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock
from urllib.request import urlopen, Request
from urllib.error import URLError

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "sim"))

from darwin_sim.core.types import FillResult, Side, from_x18, to_x18, BPS
from darwin_sim.scoring.fitness import (
    cohort_metrics, compute_fitness, update_weights,
)


class ScorerState:
    def __init__(self, archive_url: str = "http://localhost:9447"):
        self.archive_url = archive_url.rstrip("/")
        self.lock = Lock()
        self.score_roots: dict[str, dict] = {}
        self.weight_roots: dict[str, dict] = {}

    def score_epoch(self, epoch_id: str, artifact_dir: str | None = None) -> dict:
        """Score an epoch from local artifacts or archive."""
        if artifact_dir:
            ctrl_path = Path(artifact_dir) / "fills_control_s0.ndjson"
            treat_path = Path(artifact_dir) / "fills_treatment_s1.ndjson"
        else:
            return {"error": "remote archive fetch not yet implemented"}

        if not ctrl_path.exists() or not treat_path.exists():
            return {"error": "fill artifacts not found"}

        control_fills = _load_fills_typed(ctrl_path)
        treatment_fills = _load_fills_typed(treat_path)

        ctrl_m = cohort_metrics(control_fills)
        treat_m = cohort_metrics(treatment_fills)

        uplift = {
            "trader_surplus_bps": treat_m["trader_surplus_bps"] - ctrl_m["trader_surplus_bps"],
            "fill_rate_bps": treat_m["fill_rate_bps"] - ctrl_m["fill_rate_bps"],
            "adverse_markout_bps": treat_m["adverse_markout_bps"] - ctrl_m["adverse_markout_bps"],
            "revenue_bps": treat_m["revenue_bps"] - ctrl_m["revenue_bps"],
        }

        fitness = compute_fitness(uplift)

        # Compute roots (SHA-256 of canonical score data)
        score_data = json.dumps({
            "epoch_id": epoch_id,
            "control": {k: round(v, 6) if isinstance(v, float) else v for k, v in ctrl_m.items()},
            "treatment": {k: round(v, 6) if isinstance(v, float) else v for k, v in treat_m.items()},
            "uplift": {k: round(v, 6) for k, v in uplift.items()},
            "fitness": round(fitness, 6),
        }, sort_keys=True)
        score_root = hashlib.sha256(score_data.encode()).hexdigest()

        # Weight update
        current_weights = {"S0_SENTINEL": 800_000, "S1_BATCH_5S": 200_000}
        new_weights = update_weights(
            current_weights,
            {"S0_SENTINEL": 0.0, "S1_BATCH_5S": fitness},
            beta=2.0, epsilon=0.08,
            canary_cap_x1e6=50_000,
            canary_set={"S1_BATCH_5S"},
        )
        weight_data = json.dumps({"epoch_id": epoch_id, "weights": new_weights}, sort_keys=True)
        weight_root = hashlib.sha256(weight_data.encode()).hexdigest()

        result = {
            "epoch_id": epoch_id,
            "score_root": score_root,
            "weight_root": weight_root,
            "control_metrics": {k: round(v, 4) if isinstance(v, float) else v for k, v in ctrl_m.items()},
            "treatment_metrics": {k: round(v, 4) if isinstance(v, float) else v for k, v in treat_m.items()},
            "uplift": {k: round(v, 4) for k, v in uplift.items()},
            "fitness": round(fitness, 6),
            "next_weights": new_weights,
            "scored_at": time.time(),
        }

        with self.lock:
            self.score_roots[epoch_id] = result
            self.weight_roots[epoch_id] = {"weight_root": weight_root, "weights": new_weights}

        return result


def _load_fills_typed(path: Path) -> list[FillResult]:
    fills = []
    with path.open() as f:
        for line in f:
            d = json.loads(line.strip())
            fills.append(FillResult(
                fill_id=d.get("fill_id", ""),
                species_id=d.get("species_id", ""),
                intent_id=d.get("intent_id", ""),
                acct_id=d.get("acct_id", ""),
                pair_id=d.get("pair_id", ""),
                ts=d.get("ts", 0),
                side=Side.BUY if d.get("side") == "BUY" else Side.SELL,
                qty_filled_x18=d.get("qty_filled_x18", 0),
                exec_price_x18=d.get("exec_price_x18", 0),
                source_price_x18=d.get("source_price_x18", 0),
                notional_x18=d.get("notional_x18", 0),
                fee_paid_x18=d.get("fee_paid_x18", 0),
                profile=d.get("profile", ""),
                is_control=d.get("is_control", False),
                success=d.get("success", True),
                trader_surplus_x18=d.get("trader_surplus_x18", 0),
                adverse_markout_x18=d.get("adverse_markout_x18", 0),
                revenue_x18=d.get("revenue_x18", 0),
            ))
    return fills


STATE: ScorerState | None = None


class ScorerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "scorer"})
        elif self.path == "/v1/scores":
            with STATE.lock:
                self._json(200, {"epochs": {k: {"score_root": v["score_root"], "fitness": v["fitness"]}
                                             for k, v in STATE.score_roots.items()}})
        elif self.path.startswith("/v1/scores/"):
            epoch_id = self.path.split("/")[-1]
            with STATE.lock:
                result = STATE.score_roots.get(epoch_id)
            if result:
                self._json(200, result)
            else:
                self._json(404, {"error": "epoch not scored"})
        elif self.path == "/v1/weights":
            with STATE.lock:
                self._json(200, {"weights": STATE.weight_roots})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path == "/v1/score":
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
            epoch_id = body.get("epoch_id", "")
            artifact_dir = body.get("artifact_dir", "")
            if not epoch_id:
                self._json(400, {"error": "epoch_id required"})
                return
            result = STATE.score_epoch(epoch_id, artifact_dir or None)
            code = 200 if "error" not in result else 400
            self._json(code, result)
        else:
            self._json(404, {"error": "not_found"})

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())

    def log_message(self, fmt, *args):
        pass


def main():
    import sys as _sys
    port = int(_sys.argv[1]) if len(_sys.argv) > 1 else 9445
    archive_url = _sys.argv[2] if len(_sys.argv) > 2 else "http://localhost:9447"

    global STATE
    STATE = ScorerState(archive_url=archive_url)
    print(f"[darwin-scorerd] Listening on :{port}")
    print(f"[darwin-scorerd] Endpoints:")
    print(f"  GET  /healthz           — health")
    print(f"  GET  /v1/scores         — list scored epochs")
    print(f"  GET  /v1/scores/:id     — single epoch score")
    print(f"  GET  /v1/weights        — current weight roots")
    print(f"  POST /v1/score          — score an epoch")

    try:
        HTTPServer(("0.0.0.0", port), ScorerHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-scorerd] Shutting down")


if __name__ == "__main__":
    main()
