"""Deterministic RNG for reproducible simulation runs."""

from __future__ import annotations

import hashlib
import struct
from random import Random


def make_rng(seed: int | str) -> Random:
    """Create a deterministic RNG from an integer or string seed."""
    if isinstance(seed, str):
        h = hashlib.sha256(seed.encode()).digest()
        seed = struct.unpack("<Q", h[:8])[0]
    return Random(seed)


def derive_seed(parent: Random, label: str) -> int:
    """Derive a child seed from a parent RNG + domain label. Deterministic."""
    raw = parent.getrandbits(64).to_bytes(8, "little") + label.encode()
    h = hashlib.sha256(raw).digest()
    return struct.unpack("<Q", h[:8])[0]
