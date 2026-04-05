"""DARWIN Router Service — control reservation + softmax species routing.

Receives admitted intents from the gateway, applies control/treatment split,
routes to species, collects fills, and forwards to the batch builder.

Port: 9444
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "sim"))

from darwin_sim.core.types import Side, to_x18, from_x18, BPS


class RouterState:
    def __init__(self, control_share_bps: int = 1500, beta: float = 2.0, epsilon: float = 0.08):
        self.control_share_bps = control_share_bps
        self.beta = beta
        self.epsilon = epsilon
        self.lock = Lock()

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

        return {
            "intent_id": intent_id,
            "species_id": species,
            "reason": reason,
            "profile": profile,
            "routed_at": time.time(),
        }

    def update_weights(self, new_weights: dict[str, int]) -> None:
        with self.lock:
            self.weights.update(new_weights)

    def update_fitness(self, new_fitness: dict[str, float]) -> None:
        with self.lock:
            self.fitness.update(new_fitness)


STATE: RouterState | None = None


class RouterHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "router"})
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
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}

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

    global STATE
    STATE = RouterState(control_share_bps=control)
    print(f"[darwin-routerd] Listening on :{port}")
    print(f"[darwin-routerd] Control share: {control/100:.1f}%")
    print(f"[darwin-routerd] Endpoints:")
    print(f"  GET  /healthz       — health")
    print(f"  GET  /v1/weights    — current species weights")
    print(f"  GET  /v1/stats      — routing stats")
    print(f"  POST /v1/route      — route an intent")
    print(f"  POST /v1/weights    — update weights")
    print(f"  POST /v1/fitness    — update fitness scores")

    try:
        HTTPServer(("0.0.0.0", port), RouterHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-routerd] Shutting down")


if __name__ == "__main__":
    main()
