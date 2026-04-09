"""DARWIN Finalizer Service — permissionless epoch finalization.

Monitors epoch state. Once the challenge window expires and all roots
are present, anyone can call finalizeEpoch. This service automates that.

Lightest overlay role: 2 vCPU, 8 GB RAM.
Port: 9448
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Event, Lock, Thread
from urllib.request import Request, urlopen

from overlay.http_utils import (
    enforce_secure_bind,
    load_json_body,
    require_admin_token,
    resolve_bind_host,
)


def _load_epoch_manager_address(deployment_file: str) -> str:
    if not deployment_file:
        return ""
    try:
        data = json.loads(Path(deployment_file).read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    return str((data.get("contracts") or {}).get("epoch_manager", ""))


ZERO_ROOT = "0x" + ("00" * 32)
GET_EPOCH_SELECTOR = bytes.fromhex("12a02c82")


def _uint256_word(value: int) -> bytes:
    return int(value).to_bytes(32, "big")


def _rpc_json(url: str, method: str, params: list) -> dict:
    request = Request(
        url,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "darwin-finalizer/1"},
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
    )
    return json.loads(urlopen(request, timeout=20).read().decode())


def _eth_call(url: str, to: str, data: str) -> str:
    payload = _rpc_json(url, "eth_call", [{"to": to, "data": data}, "latest"])
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return str(payload.get("result") or "0x")


def _decode_epoch(result_hex: str) -> dict:
    payload = bytes.fromhex(str(result_hex or "0x").removeprefix("0x"))
    if not payload:
        return {
            "config_epoch_id": 0,
            "state": 0,
            "manifest_root": ZERO_ROOT,
            "score_root": ZERO_ROOT,
            "weight_root": ZERO_ROOT,
            "rebalance_root": ZERO_ROOT,
            "closed_at": 0,
            "finalized_at": 0,
        }
    words = [payload[idx : idx + 32] for idx in range(0, len(payload), 32)]
    if len(words) < 13:
        raise RuntimeError(f"unexpected getEpoch response length: {len(words)}")
    return {
        "config_epoch_id": int.from_bytes(words[0], "big"),
        "state": int.from_bytes(words[6], "big"),
        "manifest_root": "0x" + words[7].hex(),
        "score_root": "0x" + words[8].hex(),
        "weight_root": "0x" + words[9].hex(),
        "rebalance_root": "0x" + words[10].hex(),
        "closed_at": int.from_bytes(words[11], "big"),
        "finalized_at": int.from_bytes(words[12], "big"),
    }


class FinalizerState:
    def __init__(
        self,
        archive_url: str = "",
        challenge_window_sec: int = 1800,
        state_file: str = "",
        poll_interval_sec: int = 0,
    ):
        self.archive_url = archive_url
        self.challenge_window_sec = challenge_window_sec
        self.lock = Lock()
        self.started_at = time.time()
        self.epochs: dict[int, dict] = {}
        self.finalized: dict[int, dict] = {}
        self.state_file = Path(state_file) if state_file else None
        if self.state_file:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.poll_interval_sec = max(int(poll_interval_sec), 0)
        self.last_poll_attempt_ts = 0.0
        self.last_success_ts = 0.0
        self.consecutive_failures = 0
        self.recovered_from_disk = False
        self._stop_event = Event()
        self._poll_thread: Thread | None = None
        self.rpc_url = os.environ.get("DARWIN_RPC_URL", "")
        self.deployment_file = os.environ.get("DARWIN_DEPLOYMENT_FILE", "")
        self.epoch_manager_address = _load_epoch_manager_address(self.deployment_file)
        self.finalizer_private_key = os.environ.get("DARWIN_FINALIZER_PRIVATE_KEY", "")
        self.epoch_operator_private_key = os.environ.get("DARWIN_EPOCH_OPERATOR_PRIVATE_KEY", "")
        self.onchain_enabled = bool(self.rpc_url and self.epoch_manager_address and self.finalizer_private_key)
        self.root_posting_enabled = bool(self.rpc_url and self.epoch_manager_address and self.epoch_operator_private_key)
        self._load_state()

    def _snapshot_unlocked(self) -> dict:
        return {
            "archive_url": self.archive_url,
            "challenge_window_sec": self.challenge_window_sec,
            "epochs": self.epochs,
            "finalized": self.finalized,
            "started_at": self.started_at,
            "last_poll_attempt_ts": self.last_poll_attempt_ts,
            "last_success_ts": self.last_success_ts,
            "consecutive_failures": self.consecutive_failures,
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
            self.archive_url = str(snapshot.get("archive_url", self.archive_url))
            self.challenge_window_sec = int(snapshot.get("challenge_window_sec", self.challenge_window_sec))
            self.epochs = {int(k): dict(v) for k, v in snapshot.get("epochs", {}).items()}
            self.finalized = {int(k): dict(v) for k, v in snapshot.get("finalized", {}).items()}
            self.started_at = float(snapshot.get("started_at", self.started_at))
            self.last_poll_attempt_ts = float(snapshot.get("last_poll_attempt_ts", 0.0))
            self.last_success_ts = float(snapshot.get("last_success_ts", 0.0))
            self.consecutive_failures = int(snapshot.get("consecutive_failures", 0))
            self.recovered_from_disk = True

    def status(self) -> dict:
        with self.lock:
            registered = sorted(self.epochs)
            finalized = sorted(self.finalized)
            return {
                "status": "ok",
                "role": "finalizer",
                "registered_epochs": len(self.epochs),
                "finalized_epochs": len(self.finalized),
                "latest_registered_epoch": registered[-1] if registered else 0,
                "latest_finalized_epoch": finalized[-1] if finalized else 0,
                "challenge_window_sec": self.challenge_window_sec,
                "auto_finalize": self.poll_interval_sec > 0,
                "poll_interval_sec": self.poll_interval_sec,
                "last_poll_attempt": self.last_poll_attempt_ts,
                "last_success": self.last_success_ts,
                "consecutive_failures": self.consecutive_failures,
                "state_file": str(self.state_file) if self.state_file else "",
                "recovered_from_disk": self.recovered_from_disk,
                "mode": "onchain" if self.onchain_enabled else "local",
                "rpc_url": self.rpc_url,
                "epoch_manager": self.epoch_manager_address,
                "root_posting_enabled": self.root_posting_enabled,
                "epoch_operator_present": bool(self.epoch_operator_private_key),
            }

    def register_epoch(
        self,
        epoch_id: int,
        closed_at: float,
        score_root: str,
        weight_root: str,
        rebalance_root: str,
        manifest_root: str = "",
    ) -> dict:
        """Register a closed epoch for finalization tracking."""
        with self.lock:
            self.epochs[epoch_id] = {
                "epoch_id": epoch_id,
                "closed_at": closed_at,
                "manifest_root": manifest_root,
                "score_root": score_root,
                "weight_root": weight_root,
                "rebalance_root": rebalance_root,
                "registered_at": time.time(),
            }
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)
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
        """Mark an epoch as finalized, optionally submitting finalizeEpoch on-chain."""
        check = self.check_finalizable(epoch_id)
        if not check["finalizable"]:
            return {"error": check["reason"]}

        tx_hash = ""
        tx_output = ""
        if self.onchain_enabled:
            try:
                tx_hash, tx_output = self._finalize_onchain(epoch_id)
            except RuntimeError as exc:
                return {"error": str(exc)}

        with self.lock:
            epoch = self.epochs[epoch_id]
            self.finalized[epoch_id] = {
                "epoch_id": epoch_id,
                "finalized_at": time.time(),
                "score_root": epoch["score_root"],
                "weight_root": epoch["weight_root"],
                "rebalance_root": epoch.get("rebalance_root", ""),
                "finalized_by": "darwin-finalizerd",
                "mode": "onchain" if self.onchain_enabled else "local",
                "tx_hash": tx_hash,
                "tx_output": tx_output,
            }
            self.last_success_ts = self.finalized[epoch_id]["finalized_at"]
            self.consecutive_failures = 0
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)
        return {"epoch_id": epoch_id, "status": "finalized", "finalized_at": self.finalized[epoch_id]["finalized_at"]}

    def _finalize_onchain(self, epoch_id: int) -> tuple[str, str]:
        self._prepare_onchain_epoch(epoch_id)
        onchain = self._get_onchain_epoch(epoch_id)
        if int(onchain.get("state", 0)) == 2:
            return ("", "already_finalized")
        cmd = [
            "cast",
            "send",
            self.epoch_manager_address,
            "finalizeEpoch(uint64)",
            str(epoch_id),
            "--rpc-url",
            self.rpc_url,
            "--private-key",
            self.finalizer_private_key,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"onchain_finalize_failed: {proc.stderr.strip() or proc.stdout.strip()}")
        output = proc.stdout.strip()
        match = re.search(r"0x[a-fA-F0-9]{64}", output)
        return (match.group(0) if match else "", output)

    def _cast_send(self, function_sig: str, args: list[str], private_key: str) -> tuple[str, str]:
        cmd = [
            "cast",
            "send",
            self.epoch_manager_address,
            function_sig,
            *args,
            "--rpc-url",
            self.rpc_url,
            "--private-key",
            private_key,
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"{function_sig} failed")
        output = proc.stdout.strip()
        match = re.search(r"0x[a-fA-F0-9]{64}", output)
        return (match.group(0) if match else "", output)

    def _get_onchain_epoch(self, epoch_id: int) -> dict:
        data = "0x" + (GET_EPOCH_SELECTOR + _uint256_word(epoch_id)).hex()
        return _decode_epoch(_eth_call(self.rpc_url, self.epoch_manager_address, data))

    def _prepare_onchain_epoch(self, epoch_id: int) -> None:
        if not self.root_posting_enabled:
            return

        epoch = self.epochs.get(epoch_id) or {}
        onchain = self._get_onchain_epoch(epoch_id)
        if int(onchain.get("config_epoch_id", 0)) == 0:
            raise RuntimeError("onchain_epoch_missing")
        if int(onchain.get("state", 0)) == 2:
            return

        manifest_root = str(epoch.get("manifest_root", "") or "")
        if int(onchain.get("state", 0)) == 0:
            if not manifest_root:
                raise RuntimeError("onchain_epoch_open_missing_manifest_root")
            if onchain.get("manifest_root", ZERO_ROOT) not in {ZERO_ROOT, manifest_root.lower(), manifest_root}:
                raise RuntimeError("onchain_manifest_root_mismatch")
            self._cast_send(
                "closeEpoch(uint64,bytes32)",
                [str(epoch_id), manifest_root],
                self.epoch_operator_private_key,
            )
            onchain["state"] = 1
            onchain["manifest_root"] = manifest_root

        root_specs = [
            ("score_root", "postScoreRoot(uint64,bytes32)"),
            ("weight_root", "postWeightRoot(uint64,bytes32)"),
            ("rebalance_root", "postRebalanceRoot(uint64,bytes32)"),
        ]
        for local_key, function_sig in root_specs:
            expected = str(epoch.get(local_key, "") or "")
            if not expected:
                continue
            current = str(onchain.get(local_key, ZERO_ROOT) or ZERO_ROOT)
            if current not in {ZERO_ROOT, expected.lower(), expected} and current.lower() != expected.lower():
                raise RuntimeError(f"onchain_{local_key}_mismatch")
            if current == ZERO_ROOT:
                self._cast_send(
                    function_sig,
                    [str(epoch_id), expected],
                    self.epoch_operator_private_key,
                )
                onchain[local_key] = expected

    def poll_once(self) -> dict:
        self.last_poll_attempt_ts = time.time()
        finalized_now: list[int] = []
        errors: dict[int, str] = {}

        with self.lock:
            epoch_ids = sorted(self.epochs)

        for epoch_id in epoch_ids:
            check = self.check_finalizable(epoch_id)
            if check["finalizable"]:
                result = self.finalize_epoch(epoch_id)
                if result.get("status") == "finalized":
                    finalized_now.append(epoch_id)
                else:
                    errors[epoch_id] = result.get("error", "unknown_error")
            elif check["reason"] not in {"already finalized", "challenge window active (0s remaining)"}:
                # keep non-ready reasons informational only
                pass

        if errors:
            self.consecutive_failures += 1
        else:
            self.consecutive_failures = 0

        with self.lock:
            snapshot = self._snapshot_unlocked()
        self._persist_snapshot(snapshot)

        return {
            "status": "ok" if not errors else "degraded",
            "finalized_now": finalized_now,
            "finalized_count": len(finalized_now),
            "errors": errors,
        }

    def _poll_loop(self):
        while not self._stop_event.is_set():
            self.poll_once()
            if self._stop_event.wait(self.poll_interval_sec):
                break

    def start_background_polling(self) -> bool:
        if self.poll_interval_sec <= 0:
            return False
        if self._poll_thread and self._poll_thread.is_alive():
            return False
        self._stop_event.clear()
        self._poll_thread = Thread(target=self._poll_loop, daemon=True, name="darwin-finalizer-poll")
        self._poll_thread.start()
        return True

    def stop_background_polling(self) -> None:
        self._stop_event.set()
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5)


STATE: FinalizerState | None = None


class FinalizerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self._json(200, {"status": "ok", "role": "finalizer"})
        elif self.path == "/v1/status":
            self._json(200, STATE.status())

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
        if not require_admin_token(self):
            return
        try:
            body = load_json_body(self)
        except ValueError:
            self._json(400, {"error": "invalid_json"})
            return

        if self.path == "/v1/register":
            epoch_id = body.get("epoch_id", 0)
            result = STATE.register_epoch(
                epoch_id=epoch_id,
                closed_at=body.get("closed_at", time.time()),
                manifest_root=body.get("manifest_root", ""),
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
        elif self.path == "/v1/poll-once":
            self._json(200, STATE.poll_once())

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
    state_file = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("DARWIN_FINALIZER_STATE_FILE", "")
    poll_interval_sec = int(sys.argv[4]) if len(sys.argv) > 4 else int(os.environ.get("DARWIN_FINALIZER_POLL_SEC", "0"))
    bind_host = resolve_bind_host()
    enforce_secure_bind("darwin-finalizerd", bind_host)

    global STATE
    STATE = FinalizerState(
        challenge_window_sec=challenge_window,
        state_file=state_file,
        poll_interval_sec=poll_interval_sec,
    )
    print(f"[darwin-finalizerd] Listening on :{port}")
    print(f"[darwin-finalizerd] Challenge window: {challenge_window}s")
    if state_file:
        print(f"[darwin-finalizerd] State file: {state_file}")
    print(f"[darwin-finalizerd] Auto finalize: {'on' if poll_interval_sec > 0 else 'off'}")
    print(f"[darwin-finalizerd] Mode: {'onchain' if STATE.onchain_enabled else 'local'}")
    if STATE.epoch_manager_address:
        print(f"[darwin-finalizerd] Epoch manager: {STATE.epoch_manager_address}")
    print(f"[darwin-finalizerd] Endpoints:")
    print(f"  GET  /healthz              — health")
    print(f"  GET  /v1/status            — finalizer status")
    print(f"  GET  /v1/finalized         — list finalized epochs")
    print(f"  GET  /v1/check/:epoch_id   — check if epoch is finalizable")
    print(f"  POST /v1/register          — register a closed epoch")
    print(f"  POST /v1/finalize/:id      — finalize an epoch")
    print(f"  POST /v1/poll-once         — finalize all ready epochs once")
    try:
        STATE.start_background_polling()
        print(f"[darwin-finalizerd] Bind host: {bind_host}")
        HTTPServer((bind_host, port), FinalizerHandler).serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-finalizerd] Shutting down")
    finally:
        STATE.stop_background_polling()


if __name__ == "__main__":
    main()
