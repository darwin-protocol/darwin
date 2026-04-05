"""Dual-envelope intent creation and signing.

PQ signature: real ML-DSA-65 (Dilithium3) via dilithium-py.
EVM signature: real secp256k1 ECDSA via eth-keys.
Both signatures are cryptographically bound through h_pq inclusion in h_evm.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from eth_keys import keys

from darwin_sim.sdk.accounts import (
    DarwinAccount,
    ZERO_EVM_ADDRESS,
    _hash_domain,
    derive_acct_id,
    normalize_evm_address,
    public_account_from_dict,
)
from darwin_sim.sdk.pq_crypto import pq_sign, pq_verify
from darwin_sim.core.types import to_x18


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
    chain_id: int = 1
    settlement_hub: str = ZERO_EVM_ADDRESS
    # Binding
    intent_hash: str = ""
    # Public account material needed for service-side verification
    account: dict = field(default_factory=dict)

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
                "chain_id": self.chain_id,
                "settlement_hub": self.settlement_hub,
            },
            "intent_hash": self.intent_hash,
            "account": self.account,
        }


def _build_intent_body(
    pair_id: str,
    side: str,
    qty_base_x18: int,
    limit_price_x18: int,
    max_slippage_bps: int,
    profile: str,
    expiry_ts: int,
    nonce: int,
) -> bytes:
    return (
        f"{pair_id}:{side}:{qty_base_x18}:{limit_price_x18}:"
        f"{max_slippage_bps}:{profile}:{expiry_ts}:{nonce}"
    ).encode()


def _intent_body_from_fields(intent_fields: dict) -> bytes:
    return _build_intent_body(
        pair_id=str(intent_fields["pair_id"]),
        side=str(intent_fields["side"]),
        qty_base_x18=int(intent_fields["qty_base_x18"]),
        limit_price_x18=int(intent_fields["limit_price_x18"]),
        max_slippage_bps=int(intent_fields["max_slippage_bps"]),
        profile=str(intent_fields["profile"]),
        expiry_ts=int(intent_fields["expiry_ts"]),
        nonce=int(intent_fields["nonce"]),
    )


def _intent_body_from_intent(intent: DualEnvelopeIntent) -> bytes:
    return _build_intent_body(
        pair_id=intent.pair_id,
        side=intent.side,
        qty_base_x18=to_x18(intent.qty_base),
        limit_price_x18=to_x18(intent.limit_price),
        max_slippage_bps=intent.max_slippage_bps,
        profile=intent.profile,
        expiry_ts=intent.expiry_ts,
        nonce=intent.nonce,
    )


def compute_pq_hash(acct_id: str, suite_id: str, intent_body: bytes) -> bytes:
    return _hash_domain(
        "DARWIN/Intent/v1",
        suite_id.encode(),
        acct_id.encode(),
        intent_body,
    )


def compute_evm_hash(
    chain_id: int,
    settlement_hub: str,
    suite_id: str,
    intent_body: bytes,
    pq_hash: bytes,
) -> bytes:
    evm_payload = hashlib.sha256(intent_body + pq_hash + suite_id.encode()).digest()
    return _hash_domain(
        "DARWIN/EVMEnvelope/v1",
        chain_id.to_bytes(4, "big"),
        bytes.fromhex(normalize_evm_address(settlement_hub)[2:]),
        evm_payload,
    )


def _sign_pq(sk: bytes, message: bytes) -> bytes:
    """Real ML-DSA-65 (Dilithium3) signature.
    FIPS 204 compliant. Signature is 3293 bytes.
    """
    return pq_sign(sk, message)


def _sign_evm(sk: bytes, message: bytes) -> bytes:
    """Sign an EVM envelope hash with secp256k1."""
    return keys.PrivateKey(sk).sign_msg_hash(message).to_bytes()


def _recover_evm_address(message: bytes, signature: bytes) -> str:
    return normalize_evm_address(
        keys.Signature(signature_bytes=signature).recover_public_key_from_msg_hash(message).to_checksum_address()
    )


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
    chain_id: int | None = None,
    settlement_hub: str = ZERO_EVM_ADDRESS,
    suite_id: str = "darwin-sim-v0.4",
) -> DualEnvelopeIntent:
    """Create a dual-envelope signed intent per v0.4 spec.

    Step 1: hash intent with PQ domain separation
    Step 2: sign with PQ hot key
    Step 3: bind PQ hash into EVM envelope
    Step 4: sign EVM envelope
    """
    qty_base_x18 = to_x18(qty_base)
    limit_price_x18 = to_x18(limit_price)
    intent_body = _build_intent_body(
        pair_id=pair_id,
        side=side,
        qty_base_x18=qty_base_x18,
        limit_price_x18=limit_price_x18,
        max_slippage_bps=max_slippage_bps,
        profile=profile,
        expiry_ts=expiry_ts,
        nonce=nonce,
    )
    chain_id = account.chain_id if chain_id is None else chain_id
    settlement_hub = normalize_evm_address(settlement_hub)

    # Step 1: PQ hash
    h_pq = compute_pq_hash(account.acct_id, suite_id, intent_body)
    pq_hash = h_pq.hex()

    # Step 2: PQ signature
    pq_sig = _sign_pq(account.pq_hot_sk, h_pq)

    # Step 3: EVM envelope (binds h_pq into the EVM hash)
    h_evm = compute_evm_hash(chain_id, settlement_hub, suite_id, intent_body, h_pq)
    eip712_hash = h_evm.hex()

    # Step 4: EVM signature
    evm_sig = _sign_evm(account.evm_sk, h_evm)

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
        chain_id=chain_id,
        settlement_hub=settlement_hub,
        intent_hash=intent_hash,
        account=account.to_dict(),
    )


def verify_pq_sig(account: DarwinAccount, intent: DualEnvelopeIntent) -> bool:
    """Verify the PQ leg signature using real ML-DSA-65."""
    expected = compute_pq_hash(account.acct_id, intent.suite_id, _intent_body_from_intent(intent)).hex()
    if expected != intent.pq_hash:
        return False
    h_pq = bytes.fromhex(expected)
    sig = bytes.fromhex(intent.pq_sig)
    return pq_verify(account.pq_hot_pk, h_pq, sig)


def verify_evm_sig(account: DarwinAccount, intent: DualEnvelopeIntent) -> bool:
    """Verify the EVM leg signature."""
    if normalize_evm_address(account.evm_addr) != normalize_evm_address(intent.evm_addr):
        return False
    expected = compute_evm_hash(
        chain_id=intent.chain_id,
        settlement_hub=intent.settlement_hub,
        suite_id=intent.suite_id,
        intent_body=_intent_body_from_intent(intent),
        pq_hash=bytes.fromhex(intent.pq_hash),
    ).hex()
    if expected != intent.eip712_hash:
        return False
    try:
        recovered = _recover_evm_address(bytes.fromhex(expected), bytes.fromhex(intent.evm_sig))
    except Exception:
        return False
    return recovered == normalize_evm_address(intent.evm_addr)


def verify_binding(intent: DualEnvelopeIntent) -> bool:
    """Verify PQ and EVM hashes are cryptographically bound."""
    h_pq = bytes.fromhex(intent.pq_hash)
    h_evm = bytes.fromhex(intent.eip712_hash)
    expected_hash = hashlib.sha256(h_pq + h_evm).hexdigest()[:32]
    return expected_hash == intent.intent_hash


def verify_intent_payload(intent_data: dict) -> tuple[bool, str]:
    """Verify a transport payload exactly as the gateway receives it."""
    try:
        account = public_account_from_dict(intent_data["account"])
        intent = intent_data["intent"]
        pq_leg = intent_data["pq_leg"]
        evm_leg = intent_data["evm_leg"]

        derived_acct_id = derive_acct_id(
            pq_hot_pk=account.pq_hot_pk,
            pq_cold_pk=account.pq_cold_pk,
            evm_addr=account.evm_addr,
            hot_capabilities=account.hot_capabilities,
            hot_value_limit_usd=account.hot_value_limit_usd,
            recovery_delay_sec=account.recovery_delay_sec,
            chain_id=account.chain_id,
        )
        if account.acct_id and account.acct_id != derived_acct_id:
            return False, "account_policy_mismatch"
        if pq_leg["acct_id"] != derived_acct_id:
            return False, "acct_id_mismatch"

        evm_addr = normalize_evm_address(evm_leg["evm_addr"])
        if evm_addr != account.evm_addr:
            return False, "evm_addr_mismatch"

        chain_id = int(evm_leg.get("chain_id", account.chain_id))
        if chain_id != account.chain_id:
            return False, "chain_id_mismatch"
        settlement_hub = normalize_evm_address(evm_leg.get("settlement_hub", ZERO_EVM_ADDRESS))

        intent_body = _intent_body_from_fields(intent)
        expected_pq_hash = compute_pq_hash(derived_acct_id, pq_leg["suite_id"], intent_body)
        if pq_leg["pq_hash"] != expected_pq_hash.hex():
            return False, "pq_hash_mismatch"
        if not pq_verify(account.pq_hot_pk, expected_pq_hash, bytes.fromhex(pq_leg["pq_sig"])):
            return False, "invalid_pq_sig"

        expected_evm_hash = compute_evm_hash(chain_id, settlement_hub, pq_leg["suite_id"], intent_body, expected_pq_hash)
        if evm_leg["eip712_hash"] != expected_evm_hash.hex():
            return False, "eip712_hash_mismatch"
        if _recover_evm_address(expected_evm_hash, bytes.fromhex(evm_leg["evm_sig"])) != evm_addr:
            return False, "invalid_evm_sig"

        expected_binding = hashlib.sha256(expected_pq_hash + expected_evm_hash).hexdigest()[:32]
        if intent_data.get("intent_hash", "") != expected_binding:
            return False, "binding_mismatch"

    except KeyError as exc:
        return False, f"missing_{exc.args[0]}"
    except (TypeError, ValueError):
        return False, "invalid_payload"
    except Exception:
        return False, "invalid_signature_payload"

    return True, ""
