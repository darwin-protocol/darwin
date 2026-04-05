"""Dual-envelope intent creation and signing.

v1: PQ signature (simulated ML-DSA-65) + EVM signature (simulated ECDSA).
Both signatures are cryptographically bound through h_pq inclusion in h_evm.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from darwin_sim.sdk.accounts import DarwinAccount, _hash_domain
from darwin_sim.core.types import Side, to_x18


@dataclass(slots=True)
class DualEnvelopeIntent:
    """A fully signed dual-envelope intent per v0.4 spec."""
    # Intent body
    pair_id: str = ""
    side: str = ""
    qty_base: float = 0.0
    limit_price: float = 0.0
    max_slippage_bps: int = 50
    profile: str = "BALANCED"
    expiry_ts: int = 0
    nonce: int = 0
    # PQ leg
    acct_id: str = ""
    pq_hash: str = ""
    pq_sig: str = ""
    suite_id: str = "darwin-sim-v0.4"
    # EVM leg
    evm_addr: str = ""
    eip712_hash: str = ""
    evm_sig: str = ""
    # Binding
    intent_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "intent": {
                "pair_id": self.pair_id,
                "side": self.side,
                "qty_base_x18": str(to_x18(self.qty_base)),
                "limit_price_x18": str(to_x18(self.limit_price)),
                "max_slippage_bps": self.max_slippage_bps,
                "profile": self.profile,
                "expiry_ts": self.expiry_ts,
                "nonce": self.nonce,
            },
            "pq_leg": {
                "acct_id": self.acct_id,
                "pq_hash": self.pq_hash,
                "pq_sig": self.pq_sig,
                "suite_id": self.suite_id,
            },
            "evm_leg": {
                "evm_addr": self.evm_addr,
                "eip712_hash": self.eip712_hash,
                "evm_sig": self.evm_sig,
            },
            "intent_hash": self.intent_hash,
        }


def _sign_pq(sk: bytes, message: bytes) -> bytes:
    """Simulated ML-DSA-65 signature (HMAC-SHA256 stand-in).
    Production: FIPS 204 ML-DSA-65.Sign(sk, msg).
    """
    return hmac.new(sk, message, hashlib.sha256).digest()


def _sign_evm(pk: bytes, message: bytes) -> bytes:
    """Simulated ECDSA signature (HMAC-SHA256 stand-in).
    Production: secp256k1 ECDSA.Sign(sk, msg).
    """
    return hmac.new(pk, message, hashlib.sha256).digest()


def create_intent(
    account: DarwinAccount,
    pair_id: str,
    side: str,
    qty_base: float,
    limit_price: float,
    max_slippage_bps: int = 50,
    profile: str = "BALANCED",
    expiry_ts: int = 0,
    nonce: int = 0,
    chain_id: int = 1,
    suite_id: str = "darwin-sim-v0.4",
) -> DualEnvelopeIntent:
    """Create a dual-envelope signed intent per v0.4 spec.

    Step 1: hash intent with PQ domain separation
    Step 2: sign with PQ hot key
    Step 3: bind PQ hash into EVM envelope
    Step 4: sign EVM envelope
    """
    # Serialize intent body
    intent_body = (
        f"{pair_id}:{side}:{to_x18(qty_base)}:{to_x18(limit_price)}:"
        f"{max_slippage_bps}:{profile}:{expiry_ts}:{nonce}"
    ).encode()

    # Step 1: PQ hash
    h_pq = _hash_domain(
        "DARWIN/Intent/v1",
        suite_id.encode(),
        account.acct_id.encode(),
        intent_body,
    )
    pq_hash = h_pq.hex()

    # Step 2: PQ signature
    pq_sig = _sign_pq(account.pq_hot_sk, h_pq)

    # Step 3: EVM envelope (binds h_pq into the EVM hash)
    evm_payload = hashlib.sha256(intent_body + h_pq + suite_id.encode()).digest()
    h_evm = _hash_domain(
        "DARWIN/EVMEnvelope/v1",
        chain_id.to_bytes(4, "big"),
        b"\x00" * 20,  # settlement hub address placeholder
        evm_payload,
    )
    eip712_hash = h_evm.hex()

    # Step 4: EVM signature
    evm_sig = _sign_evm(account.evm_pk, h_evm)

    # Full intent hash for deduplication
    intent_hash = hashlib.sha256(h_pq + h_evm).hexdigest()[:32]

    return DualEnvelopeIntent(
        pair_id=pair_id,
        side=side,
        qty_base=qty_base,
        limit_price=limit_price,
        max_slippage_bps=max_slippage_bps,
        profile=profile,
        expiry_ts=expiry_ts,
        nonce=nonce,
        acct_id=account.acct_id,
        pq_hash=pq_hash,
        pq_sig=pq_sig.hex(),
        suite_id=suite_id,
        evm_addr=account.evm_addr,
        eip712_hash=eip712_hash,
        evm_sig=evm_sig.hex(),
        intent_hash=intent_hash,
    )


def verify_pq_sig(account: DarwinAccount, intent: DualEnvelopeIntent) -> bool:
    """Verify the PQ leg signature."""
    h_pq = bytes.fromhex(intent.pq_hash)
    expected = _sign_pq(account.pq_hot_sk, h_pq)
    return hmac.compare_digest(expected.hex(), intent.pq_sig)


def verify_evm_sig(account: DarwinAccount, intent: DualEnvelopeIntent) -> bool:
    """Verify the EVM leg signature."""
    h_evm = bytes.fromhex(intent.eip712_hash)
    expected = _sign_evm(account.evm_pk, h_evm)
    return hmac.compare_digest(expected.hex(), intent.evm_sig)


def verify_binding(intent: DualEnvelopeIntent) -> bool:
    """Verify PQ and EVM hashes are cryptographically bound."""
    h_pq = bytes.fromhex(intent.pq_hash)
    h_evm = bytes.fromhex(intent.eip712_hash)
    expected_hash = hashlib.sha256(h_pq + h_evm).hexdigest()[:32]
    return expected_hash == intent.intent_hash
