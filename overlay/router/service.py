"""DARWIN Router Service — control reservation + softmax species routing.

Receives admitted intents from the gateway, applies control/treatment split,
routes to species, collects fills, and forwards to the batch builder.

Port: 9444
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "sim"))

from darwin_sim.core.types import Side, to_x18, from_x18, BPS
from overlay.http_utils import (
    enforce_secure_bind,
    load_json_body,
    require_admin_token,
    resolve_bind_host,
)


class RouterState:
    def __init__(
        self,
        control_share_bps: int = 1500,
        beta: float = 2.0,
        epsilon: float = 0.08,
        state_file: str = "",
    ):
        self.control_share_bps = control_share_bps
        self.beta = beta
        self.epsilon = epsilon
        self.lock = Lock()
        self.started_at = time.time()
        self.last_route_ts = 0.0
        self.state_file = Path(state_file) if state_file else None
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.recovered_from_disk = False

        # Species weights (x1e6)
        self.weights = {
            "S0_SENTINEL": 800_000,
            "S1_BATCH_5S": 150_000,
            "S2_RFQ_ORACLE": 50_000,
        }
        self.fitness = {k: 0.0 for k in self.weights}
        self.canary_set = {"S1_BATCH_5S", "S2_RFQ_ORACLE"}
        self.canary_cap_x1e6 = 50_000

        # Stats
        self.routes: dict[str, int] = defaultdict(int)
        self.total_routed = 0
        self._load_state()

    def _snapshot_unlocked(self) -> dict:
        return {
            "control_share_bps": self.control_share_bps,
            "beta": self.beta,
            "epsilon": self.epsilon,
            "weights": self.weights,
            "fitness": self.fitness,
            "canary_set": sorted(self.canary_set),
            "canary_cap_x1e6": self.canary_cap_x1e6,
            "routes": dict(self.routes),
            "total_routed": self.total_routed,
            "started_at": self.started_at,
            "last_route_ts": self.last_route_ts,
        }

    def _persist_snapshot(self, snapshot: dict) -> None:
        if not self.state_file:
            return
        tmp_path = self.state_file.with_name(self.state_file.name + ".tmp")
        tmp_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
        tmp_path.replace(self.state_file)

    def _load_state(self) -> None:
        if not self.state_file or not self.state_file.exists():
            return
        try:
            snapshot = json.loads(self.state_file.read_text())
        except (OSError, json.JSONDecodeError):
            return

        with self.lock:
            self.weights = {str(k): int(v) for k, v in snapshot.get("weights", self.weights).items()}
            self.fitness = {str(k): float(v) for k, v in snapshot.get("fitness", self.fitness).items()}
            self.canary_set = set(snapshot.get("canary_set", list(self.canary_set)))
            self.canary_cap_x1e6 = int(snapshot.get("canary_cap_x1e6", self.canary_cap_x1e6))
            self.routes = defaultdict(int, {str(k): int(v) for k, v in snapshot.get("routes", {}).items()})
            self.total_routed = int(snapshot.get("total_routed", self.total_routed))
            self.started_at = float(snapshot.get("started_at", self.started_at))
            self.last_route_ts = float(snapshot.get("last_route_ts", 0.0))
            self.recovered_from_disk = True

    def status(self) -> dict:
        with self.lock:
            return {
                "status": "ok",
                "role": "router",
                "control_share_bps": self.control_share_bps,
                "beta": self.beta,
                "epsilon": self.epsilon,
                "weights": self.weights,
                "fitness": self.fitness,
                "routes_by_species": dict(self.routes),
                "total_routed": self.total_routed,
                "last_route_ts": self.last_route_ts,
                "state_file": str(self.state_file) if self.state_file else "",
                "recovered_from_disk": self.recovered_from_disk,
            }

    def route_intent(self, intent_data: dict) -> dict:
        """Route a single intent: control reservation → softmax species selection."""
        intent_id = intent_data.get("intent_id", "")
        profile = intent_data.get("profile", "BALANCED")

        # Deterministic control split
        h = hashlib.sha256(intent_id.encode()).hexdigest()
        bucket = int(h[:8], 16) % 10_000

        with self.lock:
            self.total_routed += 1

            if bucket < self.control_share_bps:
                species = "S0_SENTINEL"
                reason = "CONTROL"
            else:
                # Softmax over non-S0 species
                candidates = [(sid, w) for sid, w in self.weights.items() if sid != "S0_SENTINEL"]
                if not candidates:
                    species = "S0_SENTINEL"
                    reason = "FALLBACK"
                else:
                    max_f = max(self.fitness.get(sid, 0) for sid, _ in candidates)
                    exp_scores = []
                    for sid, w in candidates:
                        f = self.fitness.get(sid, 0)
                        a = w / 1_000_000
                        exp_scores.append((sid, a * math.exp(self.beta * (f - max_f))))

                    total_exp = sum(s for _, s in exp_scores)
                    if total_exp <= 0:
                        species = "S0_SENTINEL"
                        reason = "FALLBACK"
                    else:
                        # Deterministic selection based on intent hash
                        r = (int(h[8:16], 16) % 10_000) / 10_000 * total_exp
                        cumulative = 0.0
                        species = exp_scores[0][0]
                        for sid, score in exp_scores:
                            cumulative += score
                            if cumulative >= r:
                                species = sid
                                break
                        reason = "EXPLOIT"

            self.routes[species] += 1
            routed_at = time.time()
            self.last_route_ts = routed_at
            snapshot = self._snapshot_unlocked()

        self._persist_snapshot(snapshot)
        return {
            "intent_id": intent_id,
            "species_id": species,
            "reason": reason,
            "profile": profile,
            "routed_at": routed_at,
        }

    def update_weights(self, new_weights: dict[str, int]) -> None:
        with self.lock:
            self.weights.update(new_weights)
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)

    def update_fitness(self, new_fitness: dict[str, float]) -> None:
        with self.lock:
            self.fitness.update(new_fitness)
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)


STATE: RouterState | None = None


class RouterHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "router"})
        elif self.path == "/v1/status":
            self._json(200, STATE.status())
        elif self.path == "/v1/weights":
            with STATE.lock:
                self._json(200, {"weights": STATE.weights, "fitness": STATE.fitness})
        elif self.path == "/v1/stats":
            with STATE.lock:
                self._json(200, {
                    "total_routed": STATE.total_routed,
                    "routes_by_species": dict(STATE.routes),
                    "control_share_bps": STATE.control_share_bps,
                })
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if not require_admin_token(self):
            return
        try:
            body = load_json_body(self)
        except ValueError:
            self._json(400, {"error": "invalid_json"})
            return

        if self.path == "/v1/route":
            result = STATE.route_intent(body)
            self._json(200, result)
        elif self.path == "/v1/weights":
            STATE.update_weights(body.get("weights", {}))
            self._json(200, {"status": "updated"})
        elif self.path == "/v1/fitness":
            STATE.update_fitness(body.get("fitness", {}))
            self._json(200, {"status": "updated"})
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
    port = int(_sys.argv[1]) if len(_sys.argv) > 1 else 9444
    control = int(_sys.argv[2]) if len(_sys.argv) > 2 else 1500
    state_file = _sys.argv[3] if len(_sys.argv) > 3 else os.environ.get("DARWIN_ROUTER_STATE_FILE", "")
    bind_host = resolve_bind_host()
    enforce_secure_bind("darwin-routerd", bind_host)

    global STATE
    STATE = RouterState(control_share_bps=control, state_file=state_file)
    print(f"[darwin-routerd] Listening on :{port}")
    print(f"[darwin-routerd] Control share: {control/100:.1f}%")
    if state_file:
        print(f"[darwin-routerd] State file: {state_file}")
    print(f"[darwin-routerd] Endpoints:")
    print(f"  GET  /healthz       — health")
    print(f"  GET  /v1/status     — router status")
    print(f"  GET  /v1/weights    — current species weights")
    print(f"  GET  /v1/stats      — routing stats")
    print(f"  POST /v1/route      — route an intent")
    print(f"  POST /v1/weights    — update weights")
    print(f"  POST /v1/fitness    — update fitness scores")

    try:
        print(f"[darwin-routerd] Bind host: {bind_host}")
        HTTPServer((bind_host, port), RouterHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-routerd] Shutting down")


if __name__ == "__main__":
    main()
