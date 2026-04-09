"""DARWIN Sentinel Service — monitors oracle divergence, liveness, and rebalance breaches.

Triggers safe mode when thresholds are crossed. Governance-controlled role.

Port: 9449
"""

from __future__ import annotations

import json
import os
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock

from overlay.http_utils import load_json_body, require_admin_token, resolve_bind_host


class SentinelState:
    def __init__(
        self,
        oracle_divergence_bps: int = 100,
        liveness_timeout_sec: int = 120,
        state_file: str = "",
    ):
        self.oracle_divergence_bps = oracle_divergence_bps
        self.liveness_timeout_sec = liveness_timeout_sec
        self.lock = Lock()
        self.started_at = time.time()
        self.safe_mode = False
        self.safe_mode_reason = ""
        self.safe_mode_triggered_at = 0.0
        self.alerts: list[dict] = []
        self.last_heartbeat: dict[str, float] = {}
        self.last_alert_ts = 0.0
        self.state_file = Path(state_file) if state_file else None
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.recovered_from_disk = False
        self._load_state()

    def _snapshot_unlocked(self) -> dict:
        return {
            "oracle_divergence_bps": self.oracle_divergence_bps,
            "liveness_timeout_sec": self.liveness_timeout_sec,
            "safe_mode": self.safe_mode,
            "safe_mode_reason": self.safe_mode_reason,
            "safe_mode_triggered_at": self.safe_mode_triggered_at,
            "alerts": self.alerts[-200:],
            "last_heartbeat": self.last_heartbeat,
            "last_alert_ts": self.last_alert_ts,
            "started_at": self.started_at,
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
            self.safe_mode = bool(snapshot.get("safe_mode", False))
            self.safe_mode_reason = str(snapshot.get("safe_mode_reason", ""))
            self.safe_mode_triggered_at = float(snapshot.get("safe_mode_triggered_at", 0.0))
            self.alerts = list(snapshot.get("alerts", []))
            self.last_heartbeat = {str(k): float(v) for k, v in snapshot.get("last_heartbeat", {}).items()}
            self.last_alert_ts = float(snapshot.get("last_alert_ts", 0.0))
            self.started_at = float(snapshot.get("started_at", self.started_at))
            self.recovered_from_disk = True

    def status(self) -> dict:
        liveness = self.check_liveness()
        with self.lock:
            return {
                "status": "ok",
                "role": "sentinel",
                "safe_mode": self.safe_mode,
                "safe_mode_reason": self.safe_mode_reason,
                "safe_mode_triggered_at": self.safe_mode_triggered_at,
                "stale_services": liveness["stale_services"],
                "alert_count": len(self.alerts),
                "last_alert_ts": self.last_alert_ts,
                "heartbeats": {k: round(time.time() - v, 1) for k, v in self.last_heartbeat.items()},
                "oracle_divergence_bps": self.oracle_divergence_bps,
                "liveness_timeout_sec": self.liveness_timeout_sec,
                "state_file": str(self.state_file) if self.state_file else "",
                "recovered_from_disk": self.recovered_from_disk,
            }

    def report_heartbeat(self, service: str) -> None:
        with self.lock:
            self.last_heartbeat[service] = time.time()
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)

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
                self.safe_mode_triggered_at = time.time()
                self.safe_mode_reason = f"Oracle divergence {divergence_bps}bps > {self.oracle_divergence_bps}bps on {pair_id}"
            else:
                alert["action"] = "MONITORED"
            self.alerts.append(alert)
            self.last_alert_ts = alert["ts"]
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)
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
            self.safe_mode_triggered_at = alert["ts"]
            self.safe_mode_reason = f"Hard reset on {species_id} for {pair_id}"
            self.alerts.append(alert)
            self.last_alert_ts = alert["ts"]
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)
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
            self.safe_mode_triggered_at = 0.0
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)
        return {"safe_mode": False}


STATE: SentinelState | None = None


class SentinelHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "sentinel", "safe_mode": STATE.safe_mode})
        elif self.path == "/v1/status":
            self._json(200, STATE.status())
        elif self.path == "/v1/alerts":
            with STATE.lock:
                self._json(200, {"alerts": STATE.alerts[-50:]})
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
    state_file = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DARWIN_SENTINEL_STATE_FILE", "")

    global STATE
    STATE = SentinelState(state_file=state_file)
    print(f"[darwin-sentineld] Listening on :{port}")
    print(f"[darwin-sentineld] Oracle divergence threshold: {STATE.oracle_divergence_bps}bps")
    if state_file:
        print(f"[darwin-sentineld] State file: {state_file}")
    print(f"[darwin-sentineld] Endpoints:")
    print(f"  GET  /healthz                — health + safe mode status")
    print(f"  GET  /v1/status              — full status")
    print(f"  GET  /v1/alerts              — recent alerts")
    print(f"  POST /v1/heartbeat           — service heartbeat")
    print(f"  POST /v1/oracle-divergence   — report oracle divergence")
    print(f"  POST /v1/hard-reset          — report hard reset")
    print(f"  POST /v1/clear-safe-mode     — clear safe mode (governance)")

    try:
        bind_host = resolve_bind_host()
        print(f"[darwin-sentineld] Bind host: {bind_host}")
        HTTPServer((bind_host, port), SentinelHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-sentineld] Shutting down")


if __name__ == "__main__":
    main()
