"""Deterministic control/treatment split for counterfactual scoring."""

from __future__ import annotations

import hashlib

from darwin_sim.core.types import IntentRecord


def is_control(intent: IntentRecord, control_share_bps: int) -> bool:
    """Deterministic hash-based assignment — reproducible without RNG state."""
    h = hashlib.sha256(intent.intent_id.encode()).hexdigest()
    bucket = int(h[:8], 16) % 10_000
    return bucket < control_share_bps


def split_control_treatment(
    intents: list[IntentRecord],
    control_share_bps: int,
) -> tuple[list[IntentRecord], list[IntentRecord]]:
    control: list[IntentRecord] = []
    treatment: list[IntentRecord] = []
    for intent in intents:
        if is_control(intent, control_share_bps):
            control.append(intent)
        else:
            treatment.append(intent)
    return control, treatment
