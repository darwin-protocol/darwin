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

import json
import os
import time
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Event, Lock, Thread

from darwin_sim.watcher.archive import (
    ArchiveSyncError,
    list_archive_epochs,
    mirror_epoch_from_archive,
    resolve_archive_epoch_id,
)
from darwin_sim.watcher.replay import artifact_hashes, replay_and_verify
from overlay.http_utils import load_json_body, require_admin_token, resolve_bind_host


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

    def __init__(self, archive_url: str, artifact_dir: str, gateway_url: str = "", poll_interval_sec: int = 0):
        self.archive_url = archive_url.rstrip("/")
        self.artifact_dir = Path(artifact_dir)
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self.gateway_url = gateway_url.rstrip("/") if gateway_url else ""
        self.poll_interval_sec = max(int(poll_interval_sec), 0)
        self.lock = Lock()
        self.epochs: dict[int, EpochReplayResult] = {}
        self.challenges: list[dict] = []
        self.last_check_ts: float = 0
        self.last_poll_attempt_ts: float = 0
        self.last_success_ts: float = 0
        self.consecutive_failures: int = 0
        self.healthy = True
        self.last_mirrored_epoch: str = ""
        self.last_error: str = ""
        self._stop_event = Event()
        self._poll_thread: Thread | None = None

    def replay_local_epoch(self, epoch_dir: str | Path, epoch_id: int | None = None) -> EpochReplayResult:
        """Replay an epoch from local artifacts (the core watcher function)."""
        epoch_dir = Path(epoch_dir)
        replay = replay_and_verify(epoch_dir)
        result = EpochReplayResult(
            epoch_id=_coerce_epoch_id(epoch_id, epoch_dir),
            passed=replay["passed"],
            control_fills=replay.get("control_fills_loaded", 0),
            treatment_fills=replay.get("treatment_fills_loaded", 0),
            rebalance_leaves=_count_rebalance_leaves(epoch_dir / "rebalance.ndjson"),
            published_uplift=replay.get("published_uplift", {}),
            recomputed_uplift=replay.get("recomputed_uplift", {}),
            mismatches=replay.get("mismatches", []),
            replayed_at=time.time(),
            artifact_hashes=artifact_hashes(epoch_dir),
        )
        self.last_check_ts = result.replayed_at
        self.last_success_ts = result.replayed_at
        self.consecutive_failures = 0
        self.healthy = True
        self.last_error = ""

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

    def fetch_and_replay_epoch(self, epoch_id: str = "latest") -> tuple[dict, EpochReplayResult]:
        sync = mirror_epoch_from_archive(self.archive_url, self.artifact_dir, epoch_id=epoch_id)
        result = self.replay_local_epoch(sync["artifact_dir"], epoch_id=_coerce_epoch_id(sync["epoch_id"]))
        self.last_mirrored_epoch = sync["epoch_id"]
        self.healthy = True
        return sync, result

    def poll_latest_once(self) -> dict:
        self.last_poll_attempt_ts = time.time()
        try:
            latest_epoch_id = resolve_archive_epoch_id(self.archive_url, epoch_id="latest")
            if latest_epoch_id == self.last_mirrored_epoch and latest_epoch_id:
                self.healthy = True
                self.last_error = ""
                return {
                    "status": "noop",
                    "archive_epoch_id": latest_epoch_id,
                    "replayed": False,
                    "reason": "already_mirrored",
                }

            sync, result = self.fetch_and_replay_epoch(epoch_id=latest_epoch_id)
            return {
                "status": "replayed",
                "archive_epoch_id": sync["epoch_id"],
                "artifact_dir": sync["artifact_dir"],
                "downloaded_files": sync["downloaded_files"],
                "replayed": True,
                "passed": result.passed,
                "mismatches": result.mismatches,
            }
        except ArchiveSyncError as exc:
            self.healthy = False
            self.last_error = str(exc)
            self.consecutive_failures += 1
            raise

    def _poll_loop(self):
        while not self._stop_event.is_set():
            try:
                self.poll_latest_once()
            except ArchiveSyncError:
                pass
            if self._stop_event.wait(self.poll_interval_sec):
                break

    def start_background_polling(self) -> bool:
        if self.poll_interval_sec <= 0:
            return False
        if self._poll_thread and self._poll_thread.is_alive():
            return False
        self._stop_event.clear()
        self._poll_thread = Thread(target=self._poll_loop, daemon=True, name="darwin-watcher-poll")
        self._poll_thread.start()
        return True

    def stop_background_polling(self):
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5)

    def archive_epochs(self) -> list[dict]:
        return list_archive_epochs(self.archive_url)

    def health_check(self) -> dict:
        with self.lock:
            total = len(self.epochs)
            passed = sum(1 for e in self.epochs.values() if e.passed)
            open_challenges = len(self.challenges)
        return {
            "status": "ok" if self.healthy else "degraded",
            "ready": self.healthy and total > 0,
            "role": "watcher",
            "epochs_replayed": total,
            "epochs_passed": passed,
            "open_challenges": open_challenges,
            "last_check": self.last_check_ts,
            "last_poll_attempt": self.last_poll_attempt_ts,
            "last_success": self.last_success_ts,
            "consecutive_failures": self.consecutive_failures,
            "last_mirrored_epoch": self.last_mirrored_epoch,
            "last_error": self.last_error,
            "auto_sync": self.poll_interval_sec > 0,
            "poll_interval_sec": self.poll_interval_sec,
        }


def _coerce_epoch_id(epoch_id: int | str | None, epoch_dir: str | Path | None = None) -> int:
    if epoch_id is not None:
        try:
            return int(epoch_id)
        except (TypeError, ValueError):
            pass
    if epoch_dir is not None:
        name = Path(epoch_dir).name
        if name.startswith("epoch_"):
            try:
                return int(name.replace("epoch_", "", 1))
            except ValueError:
                pass
    return 0


def _count_rebalance_leaves(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open() as f:
        return sum(1 for line in f if line.strip())


# --- HTTP Service ---

STATE: WatcherState | None = None


class WatcherHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, STATE.health_check())

        elif self.path == "/readyz":
            health = STATE.health_check()
            code = 200 if health["ready"] else 503
            self._json(code, health)

        elif self.path == "/v1/challenges/open":
            with STATE.lock:
                self._json(200, {"challenges": STATE.challenges})

        elif self.path == "/v1/archive/epochs":
            try:
                self._json(200, {"epochs": STATE.archive_epochs()})
            except ArchiveSyncError as exc:
                STATE.healthy = False
                STATE.last_error = str(exc)
                self._json(502, {"error": str(exc)})

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
            health = STATE.health_check()
            with STATE.lock:
                epochs = {
                    str(k): {"passed": v.passed, "mismatches": len(v.mismatches)}
                    for k, v in STATE.epochs.items()
                }
            self._json(200, {"health": health, "epochs": epochs})

        else:
            self._json(404, {"error": "not_found"})

    def do_POST(self):
        if not require_admin_token(self):
            return
        if self.path.startswith("/v1/replay/"):
            try:
                body = load_json_body(self)
            except ValueError:
                self._json(400, {"error": "invalid_json"})
                return
            try:
                if self.path == "/v1/replay/local":
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
                    return

                if self.path in {"/v1/replay/archive", "/v1/replay/latest"}:
                    epoch_id = body.get("epoch_id", "latest")
                    if self.path == "/v1/replay/latest":
                        epoch_id = "latest"
                    sync, result = STATE.fetch_and_replay_epoch(epoch_id=epoch_id)
                    self._json(200, {
                        "epoch_id": result.epoch_id,
                        "archive_epoch_id": sync["epoch_id"],
                        "artifact_dir": sync["artifact_dir"],
                        "downloaded_files": sync["downloaded_files"],
                        "passed": result.passed,
                        "mismatches": result.mismatches,
                        "recomputed_uplift": result.recomputed_uplift,
                    })
                    return

                if self.path == "/v1/replay/poll-once":
                    poll = STATE.poll_latest_once()
                    self._json(200, poll)
                    return
            except ArchiveSyncError as exc:
                STATE.healthy = False
                STATE.last_error = str(exc)
                self._json(502, {"error": str(exc)})
                return

            self._json(404, {"error": "not_found"})
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
    poll_interval_sec = int(sys.argv[4]) if len(sys.argv) > 4 else int(os.environ.get("DARWIN_WATCHER_POLL_SEC", "0"))

    global STATE
    STATE = WatcherState(
        archive_url=archive_url,
        artifact_dir=artifact_dir,
        poll_interval_sec=poll_interval_sec,
    )

    bind_host = resolve_bind_host()
    server = HTTPServer((bind_host, port), WatcherHandler)
    print(f"[darwin-watcherd] Listening on :{port}")
    print(f"[darwin-watcherd] Bind host: {bind_host}")
    print(f"[darwin-watcherd] Artifacts: {artifact_dir}")
    print(f"[darwin-watcherd] Auto-sync: {'on' if poll_interval_sec > 0 else 'off'}")
    if poll_interval_sec > 0:
        print(f"[darwin-watcherd] Poll interval: {poll_interval_sec}s")
    print(f"[darwin-watcherd] Endpoints:")
    print(f"  GET  /healthz              — health check")
    print(f"  GET  /readyz               — readiness check")
    print(f"  GET  /v1/archive/epochs    — list archive epochs")
    print(f"  GET  /v1/status            — all replay statuses")
    print(f"  GET  /v1/epochs/:id        — single epoch replay result")
    print(f"  GET  /v1/challenges/open   — open challenge candidates")
    print(f"  POST /v1/replay/local      — replay from local artifacts")
    print(f"  POST /v1/replay/archive    — mirror from archive and replay")
    print(f"  POST /v1/replay/latest     — mirror latest archive epoch and replay")
    print(f"  POST /v1/replay/poll-once  — replay latest epoch only if archive advanced")

    STATE.start_background_polling()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-watcherd] Shutting down")
        server.shutdown()
    finally:
        STATE.stop_background_polling()


if __name__ == "__main__":
    main()
