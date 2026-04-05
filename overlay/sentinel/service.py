"""DARWIN Sentinel Service — monitors oracle divergence, liveness, and rebalance breaches.

Triggers safe mode when thresholds are crossed. Governance-controlled role.

Port: 9449
"""

from __future__ import annotations

import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Lock


class SentinelState:
    def __init__(self, oracle_divergence_bps: int = 100, liveness_timeout_sec: int = 120):
        self.oracle_divergence_bps = oracle_divergence_bps
        self.liveness_timeout_sec = liveness_timeout_sec
        self.lock = Lock()
        self.safe_mode = False
        self.safe_mode_reason = ""
        self.alerts: list[dict] = []
        self.last_heartbeat: dict[str, float] = {}

    def report_heartbeat(self, service: str) -> None:
        with self.lock:
            self.last_heartbeat[service] = time.time()

    def report_oracle_divergence(self, pair_id: str, divergence_bps: float) -> dict:
        with self.lock:
            alert = {
                "type": "oracle_divergence",
                "pair_id": pair_id,
                "divergence_bps": divergence_bps,
                "threshold_bps": self.oracle_divergence_bps,
                "ts": time.time(),
            }
            if divergence_bps > self.oracle_divergence_bps:
                alert["action"] = "SAFE_MODE_TRIGGERED"
                self.safe_mode = True
                self.safe_mode_reason = f"Oracle divergence {divergence_bps}bps > {self.oracle_divergence_bps}bps on {pair_id}"
            else:
                alert["action"] = "MONITORED"
            self.alerts.append(alert)
            return alert

    def report_hard_reset(self, species_id: str, pair_id: str) -> dict:
        with self.lock:
            alert = {
                "type": "hard_reset",
                "species_id": species_id,
                "pair_id": pair_id,
                "action": "SAFE_MODE_TRIGGERED",
                "ts": time.time(),
            }
            self.safe_mode = True
            self.safe_mode_reason = f"Hard reset on {species_id} for {pair_id}"
            self.alerts.append(alert)
            return alert

    def check_liveness(self) -> dict:
        with self.lock:
            now = time.time()
            stale = {}
            for svc, last in self.last_heartbeat.items():
                if now - last > self.liveness_timeout_sec:
                    stale[svc] = round(now - last, 1)
            return {"stale_services": stale, "safe_mode": self.safe_mode}

    def clear_safe_mode(self) -> dict:
        with self.lock:
            self.safe_mode = False
            self.safe_mode_reason = ""
            return {"safe_mode": False}


STATE: SentinelState | None = None


class SentinelHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "sentinel", "safe_mode": STATE.safe_mode})
        elif self.path == "/v1/status":
            liveness = STATE.check_liveness()
            with STATE.lock:
                self._json(200, {
                    "safe_mode": STATE.safe_mode,
                    "safe_mode_reason": STATE.safe_mode_reason,
                    "stale_services": liveness["stale_services"],
                    "alert_count": len(STATE.alerts),
                    "heartbeats": {k: round(time.time() - v, 1) for k, v in STATE.last_heartbeat.items()},
                })
        elif self.path == "/v1/alerts":
            with STATE.lock:
                self._json(200, {"alerts": STATE.alerts[-50:]})
        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}

        if self.path == "/v1/heartbeat":
            service = body.get("service", "")
            if service:
                STATE.report_heartbeat(service)
                self._json(200, {"status": "ok"})
            else:
                self._json(400, {"error": "service name required"})
        elif self.path == "/v1/oracle-divergence":
            result = STATE.report_oracle_divergence(body.get("pair_id", ""), body.get("divergence_bps", 0))
            self._json(200, result)
        elif self.path == "/v1/hard-reset":
            result = STATE.report_hard_reset(body.get("species_id", ""), body.get("pair_id", ""))
            self._json(200, result)
        elif self.path == "/v1/clear-safe-mode":
            self._json(200, STATE.clear_safe_mode())
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
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9449

    global STATE
    STATE = SentinelState()
    print(f"[darwin-sentineld] Listening on :{port}")
    print(f"[darwin-sentineld] Oracle divergence threshold: {STATE.oracle_divergence_bps}bps")
    print(f"[darwin-sentineld] Endpoints:")
    print(f"  GET  /healthz                — health + safe mode status")
    print(f"  GET  /v1/status              — full status")
    print(f"  GET  /v1/alerts              — recent alerts")
    print(f"  POST /v1/heartbeat           — service heartbeat")
    print(f"  POST /v1/oracle-divergence   — report oracle divergence")
    print(f"  POST /v1/hard-reset          — report hard reset")
    print(f"  POST /v1/clear-safe-mode     — clear safe mode (governance)")

    try:
        HTTPServer(("0.0.0.0", port), SentinelHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-sentineld] Shutting down")


if __name__ == "__main__":
    main()
