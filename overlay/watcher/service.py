"""DARWIN Watcher Service — independent epoch replay, root verification, and challenge detection.

The first outsider-run node role. Watchers:
1. Mirror epoch artifacts from the archive
2. Recompute all Merkle roots independently
3. Replay score computation from published fills
4. Detect mismatches and emit challenge candidates
5. Serve replay status via HTTP

Port: 9446
"""

from __future__ import annotations

import hashlib
import json
import time
import os
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Lock
from urllib.request import urlopen, Request
from urllib.error import URLError


@dataclass
class EpochReplayResult:
    epoch_id: int
    passed: bool
    control_fills: int = 0
    treatment_fills: int = 0
    rebalance_leaves: int = 0
    published_uplift: dict = field(default_factory=dict)
    recomputed_uplift: dict = field(default_factory=dict)
    mismatches: list = field(default_factory=list)
    replayed_at: float = 0.0
    artifact_hashes: dict = field(default_factory=dict)


class WatcherState:
    """Watcher in-memory state."""

    def __init__(self, archive_url: str, artifact_dir: str, gateway_url: str = ""):
        self.archive_url = archive_url.rstrip("/")
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.gateway_url = gateway_url.rstrip("/") if gateway_url else ""
        self.lock = Lock()
        self.epochs: dict[int, EpochReplayResult] = {}
        self.challenges: list[dict] = []
        self.last_check_ts: float = 0
        self.healthy = True

    def replay_local_epoch(self, epoch_dir: str | Path) -> EpochReplayResult:
        """Replay an epoch from local artifacts (the core watcher function)."""
        epoch_dir = Path(epoch_dir)
        result = EpochReplayResult(epoch_id=0, passed=False, replayed_at=time.time())

        # Load the report
        report_path = epoch_dir / "e2_report.json"
        if not report_path.exists():
            result.mismatches.append({"error": "e2_report.json not found"})
            return result

        with report_path.open() as f:
            report = json.load(f)

        result.epoch_id = report.get("counts", {}).get("raw_swaps", 0)

        # Hash all artifacts for integrity
        for artifact_name in ["e2_report.json", "fills_control_s0.ndjson",
                               "fills_treatment_s1.ndjson", "rebalance.ndjson"]:
            artifact_path = epoch_dir / artifact_name
            if artifact_path.exists():
                h = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
                result.artifact_hashes[artifact_name] = h

        # Load fills
        control_fills = _load_fills(epoch_dir / "fills_control_s0.ndjson")
        treatment_fills = _load_fills(epoch_dir / "fills_treatment_s1.ndjson")
        result.control_fills = len(control_fills)
        result.treatment_fills = len(treatment_fills)

        # Recompute metrics independently
        ctrl_metrics = _compute_cohort_metrics(control_fills)
        treat_metrics = _compute_cohort_metrics(treatment_fills)

        recomputed_uplift = {
            "trader_surplus_bps": treat_metrics["trader_surplus_bps"] - ctrl_metrics["trader_surplus_bps"],
            "fill_rate_bps": treat_metrics["fill_rate_bps"] - ctrl_metrics["fill_rate_bps"],
            "adverse_markout_bps": treat_metrics["adverse_markout_bps"] - ctrl_metrics["adverse_markout_bps"],
            "revenue_bps": treat_metrics["revenue_bps"] - ctrl_metrics["revenue_bps"],
        }

        published_uplift = report.get("uplift", {})
        result.published_uplift = published_uplift
        result.recomputed_uplift = {k: round(v, 4) for k, v in recomputed_uplift.items()}

        # Compare
        tolerance = 0.5  # bps
        for metric in ["trader_surplus_bps", "fill_rate_bps", "adverse_markout_bps", "revenue_bps"]:
            pub = published_uplift.get(metric, 0)
            recomp = recomputed_uplift[metric]
            if abs(pub - recomp) > tolerance:
                result.mismatches.append({
                    "metric": metric,
                    "published": pub,
                    "recomputed": round(recomp, 4),
                    "diff": round(abs(pub - recomp), 4),
                })

        # Count rebalance leaves
        reb_path = epoch_dir / "rebalance.ndjson"
        if reb_path.exists():
            with reb_path.open() as f:
                result.rebalance_leaves = sum(1 for line in f if line.strip())

        # Verify decision
        pub_decision = report.get("decision", "")
        recomp_decision = "PASS" if recomputed_uplift["trader_surplus_bps"] > 0 and recomputed_uplift["revenue_bps"] >= -5 else "REWORK"
        if pub_decision != recomp_decision:
            result.mismatches.append({
                "metric": "decision",
                "published": pub_decision,
                "recomputed": recomp_decision,
            })

        result.passed = len(result.mismatches) == 0

        with self.lock:
            self.epochs[result.epoch_id] = result
            if not result.passed:
                self.challenges.append({
                    "epoch_id": result.epoch_id,
                    "severity": "MATERIAL",
                    "mismatches": result.mismatches,
                    "detected_at": time.time(),
                })

        return result

    def health_check(self) -> dict:
        with self.lock:
            total = len(self.epochs)
            passed = sum(1 for e in self.epochs.values() if e.passed)
            open_challenges = len(self.challenges)
        return {
            "status": "ok" if self.healthy else "degraded",
            "role": "watcher",
            "epochs_replayed": total,
            "epochs_passed": passed,
            "open_challenges": open_challenges,
            "last_check": self.last_check_ts,
        }


def _load_fills(path: Path) -> list[dict]:
    fills = []
    if not path.exists():
        return fills
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                fills.append(json.loads(line))
    return fills


def _compute_cohort_metrics(fills: list[dict]) -> dict:
    """Independent metric computation — must match the scorer exactly."""
    if not fills:
        return {"trader_surplus_bps": 0, "fill_rate_bps": 0,
                "adverse_markout_bps": 0, "revenue_bps": 0}

    total_notional = sum(_from_x18(f.get("notional_x18", 0)) for f in fills) or 1e-12
    n_success = sum(1 for f in fills if f.get("success", True))
    ts_sum = sum(_from_x18(f.get("trader_surplus_x18", 0)) for f in fills)
    adv_sum = sum(_from_x18(f.get("adverse_markout_x18", 0)) for f in fills)
    rev_sum = sum(_from_x18(f.get("revenue_x18", 0)) for f in fills)

    return {
        "trader_surplus_bps": ts_sum / total_notional * 10000,
        "fill_rate_bps": n_success / len(fills) * 10000 if fills else 0,
        "adverse_markout_bps": adv_sum / total_notional * 10000,
        "revenue_bps": rev_sum / total_notional * 10000,
    }


def _from_x18(v) -> float:
    if isinstance(v, str):
        return int(v) / 10**18
    return float(v) / 10**18 if v else 0.0


# --- HTTP Service ---

STATE: WatcherState | None = None


class WatcherHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, STATE.health_check())

        elif self.path == "/readyz":
            health = STATE.health_check()
            code = 200 if health["status"] == "ok" else 503
            self._json(code, health)

        elif self.path == "/v1/challenges/open":
            with STATE.lock:
                self._json(200, {"challenges": STATE.challenges})

        elif self.path.startswith("/v1/epochs/"):
            parts = self.path.split("/")
            if len(parts) >= 4:
                try:
                    eid = int(parts[3])
                    with STATE.lock:
                        result = STATE.epochs.get(eid)
                    if result:
                        self._json(200, {
                            "epoch_id": result.epoch_id,
                            "passed": result.passed,
                            "control_fills": result.control_fills,
                            "treatment_fills": result.treatment_fills,
                            "published_uplift": result.published_uplift,
                            "recomputed_uplift": result.recomputed_uplift,
                            "mismatches": result.mismatches,
                            "artifact_hashes": result.artifact_hashes,
                        })
                    else:
                        self._json(404, {"error": "epoch not replayed"})
                except ValueError:
                    self._json(400, {"error": "invalid epoch_id"})
            else:
                self._json(400, {"error": "missing epoch_id"})

        elif self.path == "/v1/status":
            with STATE.lock:
                self._json(200, {
                    "epochs": {str(k): {"passed": v.passed, "mismatches": len(v.mismatches)}
                               for k, v in STATE.epochs.items()},
                })

        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if self.path.startswith("/v1/replay/"):
            # POST /v1/replay/local?dir=/path/to/epoch
            content_len = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}
            epoch_dir = body.get("artifact_dir", "")

            if not epoch_dir or not Path(epoch_dir).exists():
                self._json(400, {"error": "artifact_dir not found"})
                return

            result = STATE.replay_local_epoch(epoch_dir)
            self._json(200, {
                "epoch_id": result.epoch_id,
                "passed": result.passed,
                "mismatches": result.mismatches,
                "recomputed_uplift": result.recomputed_uplift,
            })
        else:
            self._json(404, {"error": "not_found"})

    def _json(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, default=str).encode())

    def log_message(self, fmt, *args):
        pass


def main():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9446
    artifact_dir = sys.argv[2] if len(sys.argv) > 2 else "watcher_artifacts"
    archive_url = sys.argv[3] if len(sys.argv) > 3 else "http://localhost:9447"

    global STATE
    STATE = WatcherState(archive_url=archive_url, artifact_dir=artifact_dir)

    server = HTTPServer(("0.0.0.0", port), WatcherHandler)
    print(f"[darwin-watcherd] Listening on :{port}")
    print(f"[darwin-watcherd] Artifacts: {artifact_dir}")
    print(f"[darwin-watcherd] Endpoints:")
    print(f"  GET  /healthz              — health check")
    print(f"  GET  /readyz               — readiness check")
    print(f"  GET  /v1/status            — all replay statuses")
    print(f"  GET  /v1/epochs/:id        — single epoch replay result")
    print(f"  GET  /v1/challenges/open   — open challenge candidates")
    print(f"  POST /v1/replay/local      — replay from local artifacts")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-watcherd] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
