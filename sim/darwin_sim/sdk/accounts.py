"""DARWIN account creation — PQ account policy + EVM binding.

Uses real ML-DSA-65 (Dilithium3) for PQ signatures.
The account model uses policy-hash addresses committing to capabilities.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass, field

from darwin_sim.sdk.pq_crypto import pq_keygen


@dataclass(slots=True)
class DarwinAccount:
    """A DARWIN account with hot/cold keys and policy."""
    acct_id: str = ""
    pq_hot_pk: bytes = b""
    pq_hot_sk: bytes = b""
    pq_cold_pk: bytes = b""
    pq_cold_sk: bytes = b""
    evm_addr: str = ""
    evm_pk: bytes = b""
    hot_capabilities: int = 0xFF  # all capabilities
    hot_value_limit_usd: int = 50_000
    recovery_delay_sec: int = 86400  # 24 hours

    def to_dict(self) -> dict:
        return {
            "acct_id": self.acct_id,
            "pq_hot_pk": self.pq_hot_pk.hex(),
            "pq_cold_pk": self.pq_cold_pk.hex(),
            "evm_addr": self.evm_addr,
            "hot_capabilities": hex(self.hot_capabilities),
            "hot_value_limit_usd": self.hot_value_limit_usd,
            "recovery_delay_sec": self.recovery_delay_sec,
        }


def _hash_domain(domain: str, *parts: bytes) -> bytes:
    """Domain-separated hash (TupleHash256 stand-in using SHA-256)."""
    h = hashlib.sha256()
    h.update(domain.encode())
    for part in parts:
        h.update(len(part).to_bytes(4, "big"))
        h.update(part)
    return h.digest()


def _gen_pq_keypair() -> tuple[bytes, bytes]:
    """Generate a real ML-DSA-65 (Dilithium3) keypair.
    pk=1952 bytes, sk=4000 bytes per FIPS 204.
    """
    return pq_keygen()


def _gen_evm_addr() -> tuple[str, bytes]:
    """Generate a simulated EVM address."""
    pk = secrets.token_bytes(32)
    addr = "0x" + hashlib.sha256(pk).hexdigest()[:40]
    return addr, pk


def create_account(
    hot_capabilities: int = 0xFF,
    hot_value_limit_usd: int = 50_000,
    recovery_delay_sec: int = 86400,
) -> DarwinAccount:
    """Create a new DARWIN account with PQ + EVM keys.

    acct_id = H_{DARWIN/AcctPolicy/v1}(pk_hot, pk_cold, evm_addr, capabilities, limit, delay)
    """
    hot_pk, hot_sk = _gen_pq_keypair()
    cold_pk, cold_sk = _gen_pq_keypair()
    evm_addr, evm_pk = _gen_evm_addr()

    # Account policy hash (v0.4 spec)
    policy_hash = _hash_domain(
        "DARWIN/AcctPolicy/v1",
        hot_pk,
        cold_pk,
        evm_addr.encode(),
        hot_capabilities.to_bytes(4, "big"),
        hot_value_limit_usd.to_bytes(8, "big"),
        recovery_delay_sec.to_bytes(4, "big"),
    )

    # Account ID = H(chain_id, policy)
    acct_id = _hash_domain(
        "DARWIN/Address/v1",
        b"\x00\x00\x00\x01",  # chain_id placeholder
        policy_hash,
    ).hex()[:32]

    return DarwinAccount(
        acct_id=acct_id,
        pq_hot_pk=hot_pk,
        pq_hot_sk=hot_sk,
        pq_cold_pk=cold_pk,
        pq_cold_sk=cold_sk,
        evm_addr=evm_addr,
        evm_pk=evm_pk,
        hot_capabilities=hot_capabilities,
        hot_value_limit_usd=hot_value_limit_usd,
        recovery_delay_sec=recovery_delay_sec,
    )
