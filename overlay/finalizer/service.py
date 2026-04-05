"""DARWIN Finalizer Service — permissionless epoch finalization.

Monitors epoch state. Once the challenge window expires and all roots
are present, anyone can call finalizeEpoch. This service automates that.

Lightest overlay role: 2 vCPU, 8 GB RAM.
Port: 9448
"""

from __future__ import annotations

import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock


class FinalizerState:
    def __init__(self, archive_url: str = "", challenge_window_sec: int = 1800):
        self.archive_url = archive_url
        self.challenge_window_sec = challenge_window_sec
        self.lock = Lock()
        self.epochs: dict[int, dict] = {}
        self.finalized: dict[int, dict] = {}

    def register_epoch(self, epoch_id: int, closed_at: float, score_root: str,
                       weight_root: str, rebalance_root: str) -> dict:
        """Register a closed epoch for finalization tracking."""
        with self.lock:
            self.epochs[epoch_id] = {
                "epoch_id": epoch_id,
                "closed_at": closed_at,
                "score_root": score_root,
                "weight_root": weight_root,
                "rebalance_root": rebalance_root,
                "registered_at": time.time(),
            }
        return {"epoch_id": epoch_id, "status": "registered"}

    def check_finalizable(self, epoch_id: int) -> dict:
        """Check if an epoch can be finalized."""
        with self.lock:
            epoch = self.epochs.get(epoch_id)
            if not epoch:
                return {"finalizable": False, "reason": "epoch not registered"}

            if epoch_id in self.finalized:
                return {"finalizable": False, "reason": "already finalized"}

            now = time.time()
            window_end = epoch["closed_at"] + self.challenge_window_sec
            if now < window_end:
                remaining = window_end - now
                return {"finalizable": False, "reason": f"challenge window active ({remaining:.0f}s remaining)"}

            if not epoch.get("score_root") or not epoch.get("weight_root"):
                return {"finalizable": False, "reason": "roots missing"}

            return {"finalizable": True, "epoch_id": epoch_id}

    def finalize_epoch(self, epoch_id: int) -> dict:
        """Mark an epoch as finalized (in production, this calls the contract)."""
        check = self.check_finalizable(epoch_id)
        if not check["finalizable"]:
            return {"error": check["reason"]}

        with self.lock:
            epoch = self.epochs[epoch_id]
            self.finalized[epoch_id] = {
                "epoch_id": epoch_id,
                "finalized_at": time.time(),
                "score_root": epoch["score_root"],
                "weight_root": epoch["weight_root"],
                "rebalance_root": epoch.get("rebalance_root", ""),
                "finalized_by": "darwin-finalizerd",
            }
        return {"epoch_id": epoch_id, "status": "finalized",
                "finalized_at": self.finalized[epoch_id]["finalized_at"]}


STATE: FinalizerState | None = None


class FinalizerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "finalizer"})

        elif self.path == "/v1/finalized":
            with STATE.lock:
                self._json(200, {"finalized": list(STATE.finalized.values())})

        elif self.path.startswith("/v1/check/"):
            try:
                epoch_id = int(self.path.split("/")[-1])
                self._json(200, STATE.check_finalizable(epoch_id))
            except ValueError:
                self._json(400, {"error": "invalid epoch_id"})

        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_len)) if content_len > 0 else {}

        if self.path == "/v1/register":
            epoch_id = body.get("epoch_id", 0)
            result = STATE.register_epoch(
                epoch_id=epoch_id,
                closed_at=body.get("closed_at", time.time()),
                score_root=body.get("score_root", ""),
                weight_root=body.get("weight_root", ""),
                rebalance_root=body.get("rebalance_root", ""),
            )
            self._json(201, result)

        elif self.path.startswith("/v1/finalize/"):
            try:
                epoch_id = int(self.path.split("/")[-1])
                result = STATE.finalize_epoch(epoch_id)
                code = 200 if "error" not in result else 400
                self._json(code, result)
            except ValueError:
                self._json(400, {"error": "invalid epoch_id"})

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
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9448
    challenge_window = int(sys.argv[2]) if len(sys.argv) > 2 else 1800

    global STATE
    STATE = FinalizerState(challenge_window_sec=challenge_window)
    print(f"[darwin-finalizerd] Listening on :{port}")
    print(f"[darwin-finalizerd] Challenge window: {challenge_window}s")
    print(f"[darwin-finalizerd] Endpoints:")
    print(f"  GET  /healthz              — health")
    print(f"  GET  /v1/finalized         — list finalized epochs")
    print(f"  GET  /v1/check/:epoch_id   — check if epoch is finalizable")
    print(f"  POST /v1/register          — register a closed epoch")
    print(f"  POST /v1/finalize/:id      — finalize an epoch")

    try:
        HTTPServer(("0.0.0.0", port), FinalizerHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-finalizerd] Shutting down")


if __name__ == "__main__":
    main()
