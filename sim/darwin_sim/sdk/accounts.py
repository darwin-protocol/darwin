"""DARWIN account creation — PQ account policy + EVM binding.

Uses real ML-DSA-65 (Dilithium3) for PQ signatures and secp256k1
for the classical EVM settlement leg. The account model uses
policy-hash addresses committing to capabilities.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass

from eth_keys import keys
from darwin_sim.sdk.pq_crypto import pq_keygen

ZERO_EVM_ADDRESS = "0x" + ("00" * 20)


@dataclass(slots=True)
class DarwinAccount:
    """A DARWIN account with hot/cold keys and policy."""
    acct_id: str = ""
    pq_hot_pk: bytes = b""
    pq_hot_sk: bytes = b""
    pq_cold_pk: bytes = b""
    pq_cold_sk: bytes = b""
    evm_addr: str = ""
    evm_sk: bytes = b""
    chain_id: int = 1
    hot_capabilities: int = 0xFF  # all capabilities
    hot_value_limit_usd: int = 50_000
    recovery_delay_sec: int = 86400  # 24 hours

    def to_dict(self) -> dict:
        return {
            "acct_id": self.acct_id,
            "pq_hot_pk": self.pq_hot_pk.hex(),
            "pq_cold_pk": self.pq_cold_pk.hex(),
            "evm_addr": self.evm_addr,
            "chain_id": self.chain_id,
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


def normalize_evm_address(addr: str) -> str:
    """Normalize an EVM address to lowercase hex with 0x prefix."""
    if not isinstance(addr, str) or not addr.startswith("0x") or len(addr) != 42:
        raise ValueError(f"invalid EVM address: {addr!r}")
    int(addr[2:], 16)
    return "0x" + addr[2:].lower()


def _parse_int(value: int | str) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.startswith("0x"):
        return int(value, 16)
    return int(value)


def derive_acct_id(
    pq_hot_pk: bytes,
    pq_cold_pk: bytes,
    evm_addr: str,
    hot_capabilities: int,
    hot_value_limit_usd: int,
    recovery_delay_sec: int,
    chain_id: int = 1,
) -> str:
    """Derive the public account identifier from the account policy."""
    evm_addr = normalize_evm_address(evm_addr)
    policy_hash = _hash_domain(
        "DARWIN/AcctPolicy/v1",
        pq_hot_pk,
        pq_cold_pk,
        evm_addr.encode(),
        hot_capabilities.to_bytes(4, "big"),
        hot_value_limit_usd.to_bytes(8, "big"),
        recovery_delay_sec.to_bytes(4, "big"),
    )
    return _hash_domain(
        "DARWIN/Address/v1",
        chain_id.to_bytes(4, "big"),
        policy_hash,
    ).hex()[:32]


def public_account_from_dict(data: dict) -> DarwinAccount:
    """Load the public account material needed for gateway verification."""
    return DarwinAccount(
        acct_id=data.get("acct_id", ""),
        pq_hot_pk=bytes.fromhex(data["pq_hot_pk"]),
        pq_cold_pk=bytes.fromhex(data["pq_cold_pk"]),
        evm_addr=normalize_evm_address(data["evm_addr"]),
        chain_id=_parse_int(data.get("chain_id", 1)),
        hot_capabilities=_parse_int(data.get("hot_capabilities", 0xFF)),
        hot_value_limit_usd=_parse_int(data.get("hot_value_limit_usd", 50_000)),
        recovery_delay_sec=_parse_int(data.get("recovery_delay_sec", 86400)),
    )


def _gen_evm_keypair() -> tuple[str, bytes]:
    """Generate a secp256k1 private key and its bound EVM address."""
    evm_sk = secrets.token_bytes(32)
    evm_addr = normalize_evm_address(keys.PrivateKey(evm_sk).public_key.to_checksum_address())
    return evm_addr, evm_sk


def create_account(
    chain_id: int = 1,
    hot_capabilities: int = 0xFF,
    hot_value_limit_usd: int = 50_000,
    recovery_delay_sec: int = 86400,
) -> DarwinAccount:
    """Create a new DARWIN account with PQ + EVM keys.

    acct_id = H_{DARWIN/AcctPolicy/v1}(pk_hot, pk_cold, evm_addr, capabilities, limit, delay)
    """
    hot_pk, hot_sk = _gen_pq_keypair()
    cold_pk, cold_sk = _gen_pq_keypair()
    evm_addr, evm_sk = _gen_evm_keypair()
    acct_id = derive_acct_id(
        hot_pk,
        cold_pk,
        evm_addr,
        hot_capabilities,
        hot_value_limit_usd,
        recovery_delay_sec,
        chain_id=chain_id,
    )

    return DarwinAccount(
        acct_id=acct_id,
        pq_hot_pk=hot_pk,
        pq_hot_sk=hot_sk,
        pq_cold_pk=cold_pk,
        pq_cold_sk=cold_sk,
        evm_addr=evm_addr,
        evm_sk=evm_sk,
        chain_id=chain_id,
        hot_capabilities=hot_capabilities,
        hot_value_limit_usd=hot_value_limit_usd,
        recovery_delay_sec=recovery_delay_sec,
    )
