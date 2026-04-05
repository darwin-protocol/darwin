"""DARWIN PQ Crypto — real ML-DSA (Dilithium3) signatures.

Uses dilithium-py for NIST FIPS 204 compatible lattice-based signatures.
Dilithium3 = ML-DSA-65 (NIST security category 3).

Signature sizes: pk=1952B, sk=4000B, sig=3293B.
"""

from __future__ import annotations

from dilithium_py.dilithium import Dilithium3


def pq_keygen() -> tuple[bytes, bytes]:
    """Generate an ML-DSA-65 (Dilithium3) keypair.
    Returns (public_key, secret_key).
    """
    pk, sk = Dilithium3.keygen()
    return pk, sk


def pq_sign(sk: bytes, message: bytes) -> bytes:
    """Sign a message with ML-DSA-65.
    Returns the signature (3293 bytes).
    """
    return Dilithium3.sign(sk, message)


def pq_verify(pk: bytes, message: bytes, signature: bytes) -> bool:
    """Verify an ML-DSA-65 signature.
    Returns True if valid.
    """
    return Dilithium3.verify(pk, message, signature)
