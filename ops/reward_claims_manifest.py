#!/usr/bin/env python3
"""Shared reward-claims manifest selection helpers."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def load_optional_json(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    return load_json(path)


def default_reward_claims_paths(network_slug: str) -> tuple[Path, Path]:
    return (
        REPO_ROOT / "ops" / "state" / f"{network_slug}-epoch-rewards.json",
        REPO_ROOT / "ops" / "state" / f"{network_slug}-drw-merkle.json",
    )


def epoch_reward_distributor_live(reward_claims: dict, epoch_rewards_sidecar: dict) -> bool:
    if str(reward_claims.get("distributor", "") or "").strip():
        return True
    epoch_rewards = epoch_rewards_sidecar.get("epoch_rewards") or {}
    contracts = epoch_rewards.get("contracts") or {}
    return bool(str(contracts.get("drw_epoch_distributor", "") or "").strip())


def select_reward_claims_manifest(
    network_slug: str,
    reward_claims_path: Path | None = None,
    epoch_reward_manifest_path: Path | None = None,
    legacy_reward_manifest_path: Path | None = None,
    epoch_rewards_sidecar_path: Path | None = None,
) -> Path | None:
    if reward_claims_path is not None:
        return reward_claims_path if reward_claims_path.exists() else None

    epoch_manifest = epoch_reward_manifest_path
    legacy_manifest = legacy_reward_manifest_path
    if epoch_manifest is None or legacy_manifest is None:
        default_epoch, default_legacy = default_reward_claims_paths(network_slug)
        epoch_manifest = epoch_manifest or default_epoch
        legacy_manifest = legacy_manifest or default_legacy

    epoch_rewards_sidecar = load_optional_json(epoch_rewards_sidecar_path)
    if epoch_manifest.exists():
        epoch_reward_manifest = load_json(epoch_manifest)
        epoch_distributor_is_live = epoch_reward_distributor_live(epoch_reward_manifest, epoch_rewards_sidecar)
        if epoch_distributor_is_live or not legacy_manifest.exists():
            return epoch_manifest
    if legacy_manifest.exists():
        return legacy_manifest
    return None
