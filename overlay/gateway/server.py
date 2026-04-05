"""DARWIN Gateway Service — accepts, validates, and routes dual-envelope intents.

This is the first overlay service. It accepts intents via HTTP,
validates both PQ and EVM signatures, assigns buckets, and archives.

v1: runs as a standalone HTTP server on port 9443.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Lock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "sim"))

from darwin_sim.sdk.accounts import ZERO_EVM_ADDRESS, normalize_evm_address
from darwin_sim.sdk.deployments import load_deployment
from darwin_sim.sdk.intents import verify_intent_payload


class GatewayState:
    """In-memory gateway state."""

    def __init__(
        self,
        archive_dir: str = "gateway_archive",
        deployment_file: str | None = None,
        allowed_chain_id: int | None = None,
        allowed_settlement_hub: str | None = None,
    ):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self.intents: dict[str, dict] = {}
        self.nonces: set[str] = set()
        self.rate_limits: dict[str, list[float]] = defaultdict(list)
        self.lock = Lock()
        self.stats = {"admitted": 0, "rejected": 0, "total": 0}

        deployment = None
        deployment_file = deployment_file or os.environ.get("DARWIN_DEPLOYMENT_FILE")
        if deployment_file:
            deployment = load_deployment(deployment_file=deployment_file)

        self.allowed_chain_id = (
            allowed_chain_id
            if allowed_chain_id is not None
            else (deployment.chain_id if deployment else None)
        )
        if self.allowed_chain_id is None and os.environ.get("DARWIN_ALLOWED_CHAIN_ID"):
            self.allowed_chain_id = int(os.environ["DARWIN_ALLOWED_CHAIN_ID"])

        self.allowed_settlement_hub = (
            normalize_evm_address(allowed_settlement_hub)
            if allowed_settlement_hub is not None
            else (deployment.settlement_hub if deployment else None)
        )
        if self.allowed_settlement_hub is None and os.environ.get("DARWIN_ALLOWED_SETTLEMENT_HUB"):
            self.allowed_settlement_hub = normalize_evm_address(os.environ["DARWIN_ALLOWED_SETTLEMENT_HUB"])

    def admit_intent(self, intent_data: dict) -> dict:
        """Validate and admit a dual-envelope intent."""
        with self.lock:
            self.stats["total"] += 1

            # Extract fields
            intent = intent_data.get("intent", {})
            pq_leg = intent_data.get("pq_leg", {})
            evm_leg = intent_data.get("evm_leg", {})
            account = intent_data.get("account", {})

            # 1. Schema validation
            required_intent = [
                "pair_id",
                "side",
                "qty_base_x18",
                "limit_price_x18",
                "max_slippage_bps",
                "profile",
                "expiry_ts",
                "nonce",
            ]
            for field in required_intent:
                if field not in intent:
                    return self._reject(f"missing intent field: {field}")

            required_pq = ["acct_id", "pq_hash", "pq_sig", "suite_id"]
            for field in required_pq:
                if field not in pq_leg:
                    return self._reject(f"missing pq_leg field: {field}")

            required_evm = ["evm_addr", "eip712_hash", "evm_sig"]
            for field in required_evm:
                if field not in evm_leg:
                    return self._reject(f"missing evm_leg field: {field}")

            required_account = [
                "acct_id",
                "pq_hot_pk",
                "pq_cold_pk",
                "evm_addr",
                "chain_id",
                "hot_capabilities",
                "hot_value_limit_usd",
                "recovery_delay_sec",
            ]
            for field in required_account:
                if field not in account:
                    return self._reject(f"missing account field: {field}")

            # 2. Cryptographic validation
            ok, reason = verify_intent_payload(intent_data)
            if not ok:
                return self._reject(reason)

            # 3. Deployment policy checks (optional hard pinning to one live hub)
            chain_id = int(evm_leg.get("chain_id", account["chain_id"]))
            if self.allowed_chain_id is not None and chain_id != self.allowed_chain_id:
                return self._reject("unsupported_chain_id")

            settlement_hub = normalize_evm_address(evm_leg.get("settlement_hub", ZERO_EVM_ADDRESS))
            if self.allowed_settlement_hub is not None and settlement_hub != self.allowed_settlement_hub:
                return self._reject("unsupported_settlement_hub")

            # 4. Nonce check (replay protection)
            nonce_key = f"{pq_leg['acct_id']}:{intent['nonce']}"
            if nonce_key in self.nonces:
                return self._reject("nonce_replay")

            # 5. Rate limiting (60/min per acct_id)
            acct_id = pq_leg["acct_id"]
            now = time.time()
            window = [t for t in self.rate_limits[acct_id] if t > now - 60]
            if len(window) >= 60:
                return self._reject("rate_limited")
            window.append(now)
            self.rate_limits[acct_id] = window
            self.nonces.add(nonce_key)

            # 6. Assign bucket
            profile = intent.get("profile", "BALANCED")
            bucket_id = profile

            # 7. Generate intent_id
            intent_hash = intent_data.get("intent_hash", "")
            intent_id = hashlib.sha256(
                f"{acct_id}:{intent['nonce']}:{intent_hash}".encode()
            ).hexdigest()[:32]

            # 8. Archive
            admission = {
                "intent_id": intent_id,
                "status": "ADMITTED",
                "bucket_id": bucket_id,
                "received_at": int(now),
                "acct_id": acct_id,
                "pair_id": intent.get("pair_id"),
                "pq_verified": True,
                "evm_verified": True,
                "binding_verified": True,
            }

            self.intents[intent_id] = {
                "admission": admission,
                "intent_data": intent_data,
            }

            # Write to archive
            archive_path = self.archive_dir / f"{intent_id}.json"
            with archive_path.open("w") as f:
                json.dump(self.intents[intent_id], f, indent=2)

            self.stats["admitted"] += 1
            return admission

    def _reject(self, reason: str) -> dict:
        self.stats["rejected"] += 1
        return {"status": "REJECTED", "reason": reason}


# Global state
STATE = GatewayState()


class GatewayHandler(BaseHTTPRequestHandler):
    """HTTP handler for the DARWIN gateway."""

    def do_POST(self):
        if self.path == "/v1/intents":
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len)

            try:
                intent_data = json.loads(body)
            except json.JSONDecodeError:
                self._respond(400, {"error": "invalid_json"})
                return

            result = STATE.admit_intent(intent_data)

            if result.get("status") == "ADMITTED":
                self._respond(201, result)
            else:
                self._respond(400, result)

        else:
            self._respond(404, {"error": "not_found"})

    def do_GET(self):
        if self.path == "/healthz":
            self._respond(200, {"status": "ok", "role": "gateway"})

        elif self.path == "/v1/stats":
            self._respond(200, STATE.stats)

        elif self.path == "/v1/config":
            self._respond(200, {
                "allowed_chain_id": STATE.allowed_chain_id,
                "allowed_settlement_hub": STATE.allowed_settlement_hub,
            })

        elif self.path.startswith("/v1/intents/"):
            intent_id = self.path.split("/")[-1]
            record = STATE.intents.get(intent_id)
            if record:
                self._respond(200, record["admission"])
            else:
                self._respond(404, {"error": "intent_not_found"})

        elif self.path == "/v1/species":
            self._respond(200, {
                "species": [
                    {"id": "S0_SENTINEL", "state": "ACTIVE", "canary": False},
                    {"id": "S1_BATCH_5S", "state": "CANARY", "canary": True},
                    {"id": "S2_RFQ_ORACLE", "state": "CANARY", "canary": True},
                ]
            })

        elif self.path == "/v1/pairs":
            self._respond(200, {
                "pairs": [
                    {"pair_id": "ETH_USDC", "shared_vault_enabled": True},
                    {"pair_id": "BTC_USDC", "shared_vault_enabled": True},
                ]
            })

        else:
            self._respond(404, {"error": "not_found"})

    def _respond(self, code: int, data: dict):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def log_message(self, format, *args):
        # Suppress default logging for clean output
        pass


def main():
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9443
    archive = sys.argv[2] if len(sys.argv) > 2 else "gateway_archive"

    global STATE
    STATE = GatewayState(archive_dir=archive)

    server = HTTPServer(("0.0.0.0", port), GatewayHandler)
    print(f"[darwin-gatewayd] Listening on :{port}")
    print(f"[darwin-gatewayd] Archive: {archive}")
    print(f"[darwin-gatewayd] Endpoints:")
    print(f"  POST /v1/intents     — submit dual-envelope intent")
    print(f"  GET  /v1/intents/:id — query intent status")
    print(f"  GET  /v1/species     — list active species")
    print(f"  GET  /v1/pairs       — list active pairs")
    print(f"  GET  /v1/stats       — gateway stats")
    print(f"  GET  /healthz        — health check")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[darwin-gatewayd] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
