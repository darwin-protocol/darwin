"""Deployment artifact loading for operator and gateway flows."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENTS_DIR = REPO_ROOT / "ops" / "deployments"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def _normalize_evm_address(addr: str) -> str:
    if not isinstance(addr, str) or not addr.startswith("0x") or len(addr) != 42:
        raise ValueError(f"invalid EVM address: {addr!r}")
    int(addr[2:], 16)
    return "0x" + addr[2:].lower()


@dataclass(slots=True)
class DarwinDeployment:
    path: Path
    network: str
    chain_id: int
    bond_asset_mode: str
    settlement_hub: str
    contracts: dict[str, str]
    roles: dict[str, str]
    deployer: str
    deployed_at: int
    drw: dict | None = None
    market: dict | None = None
    faucet: dict | None = None
    vnext: dict | None = None
    private_overlay_path: Path | None = None
    private_overlay_loaded: bool = False
    vnext_path: Path | None = None
    vnext_loaded: bool = False

    @property
    def has_private_operator_fields(self) -> bool:
        return bool(self.roles.get("governance")) and self.deployer != ZERO_ADDRESS


def _normalize_address_fields(values: dict) -> dict:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, str) and value.startswith("0x") and len(value) == 42:
            normalized[key] = _normalize_evm_address(value)
        else:
            normalized[key] = value
    return normalized


def default_deployment_path(network: str) -> Path:
    return DEPLOYMENTS_DIR / f"{network}.json"


def default_private_overlay_path(path: Path) -> Path:
    resolved_path = path.resolve()
    explicit_config_dir = os.environ.get("DARWIN_CONFIG_DIR")
    if explicit_config_dir:
        config_dir = Path(explicit_config_dir)
        return config_dir / "deployments" / f"{path.stem}.private.json"
    if resolved_path.parent == DEPLOYMENTS_DIR.resolve():
        config_dir = Path(Path.home() / ".config" / "darwin")
        return config_dir / "deployments" / f"{path.stem}.private.json"
    return resolved_path.with_name(f"{resolved_path.stem}.private.json")


def resolve_deployment_path(deployment_file: str | os.PathLike | None = None, network: str | None = None) -> Path:
    if deployment_file:
        return Path(deployment_file).expanduser().resolve()

    env_deployment_file = os.environ.get("DARWIN_DEPLOYMENT_FILE")
    if env_deployment_file:
        return Path(env_deployment_file).expanduser().resolve()

    resolved_network = network or os.environ.get("DARWIN_NETWORK")
    if resolved_network:
        return default_deployment_path(resolved_network).resolve()

    raise ValueError("deployment file or network is required")


def resolve_private_overlay_path(path: Path) -> Path | None:
    if os.environ.get("DARWIN_DISABLE_DEPLOYMENT_OVERLAY") == "1":
        return None

    env_overlay = os.environ.get("DARWIN_DEPLOYMENT_OVERLAY_FILE")
    if env_overlay:
        return Path(env_overlay).expanduser().resolve()

    return default_private_overlay_path(path)


def resolve_vnext_path(path: Path) -> Path | None:
    env_vnext = os.environ.get("DARWIN_VNEXT_FILE")
    if env_vnext:
        return Path(env_vnext).expanduser().resolve()
    resolved_path = path.resolve()
    return resolved_path.with_name(f"{resolved_path.stem}.vnext.json")


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_deployment_data(
    deployment_file: str | os.PathLike | None = None, network: str | None = None
) -> tuple[Path, dict, Path | None, bool, Path | None, dict | None, bool]:
    path = resolve_deployment_path(deployment_file=deployment_file, network=network)
    data = json.loads(path.read_text())
    overlay_path = resolve_private_overlay_path(path)
    overlay_loaded = False
    if overlay_path and overlay_path.exists():
        data = _deep_merge(data, json.loads(overlay_path.read_text()))
        overlay_loaded = True
    vnext_path = resolve_vnext_path(path)
    vnext_loaded = False
    vnext_data = None
    if vnext_path and vnext_path.exists():
        vnext_data = json.loads(vnext_path.read_text())
        vnext_loaded = True
    return path, data, overlay_path, overlay_loaded, vnext_path, vnext_data, vnext_loaded


def load_deployment(deployment_file: str | os.PathLike | None = None, network: str | None = None) -> DarwinDeployment:
    path, data, overlay_path, overlay_loaded, vnext_path, vnext_data, vnext_loaded = load_deployment_data(
        deployment_file=deployment_file, network=network
    )
    contracts = _normalize_address_fields(data["contracts"])
    roles = _normalize_address_fields(data.get("roles", {}))
    deployer = str(data.get("deployer", "") or "")
    normalized_deployer = _normalize_evm_address(deployer) if deployer.startswith("0x") and len(deployer) == 42 else ZERO_ADDRESS

    return DarwinDeployment(
        path=path,
        network=str(data["network"]),
        chain_id=int(data["chain_id"]),
        bond_asset_mode=str(data.get("bond_asset_mode", "external")),
        settlement_hub=contracts["settlement_hub"],
        contracts=contracts,
        roles=roles,
        deployer=normalized_deployer,
        deployed_at=int(data["deployed_at"]),
        drw=data.get("drw"),
        market=data.get("market"),
        faucet=data.get("faucet"),
        vnext=vnext_data.get("vnext") if isinstance(vnext_data, dict) else None,
        private_overlay_path=overlay_path,
        private_overlay_loaded=overlay_loaded,
        vnext_path=vnext_path,
        vnext_loaded=vnext_loaded,
    )
