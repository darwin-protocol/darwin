"""Deployment artifact loading for operator and gateway flows."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from darwin_sim.sdk.accounts import normalize_evm_address

REPO_ROOT = Path(__file__).resolve().parents[3]
DEPLOYMENTS_DIR = REPO_ROOT / "ops" / "deployments"


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


def _normalize_address_fields(values: dict) -> dict:
    normalized: dict[str, str] = {}
    for key, value in values.items():
        if isinstance(value, str) and value.startswith("0x") and len(value) == 42:
            normalized[key] = normalize_evm_address(value)
        else:
            normalized[key] = value
    return normalized


def default_deployment_path(network: str) -> Path:
    return DEPLOYMENTS_DIR / f"{network}.json"


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


def load_deployment(deployment_file: str | os.PathLike | None = None, network: str | None = None) -> DarwinDeployment:
    path = resolve_deployment_path(deployment_file=deployment_file, network=network)
    data = json.loads(path.read_text())
    contracts = _normalize_address_fields(data["contracts"])
    roles = _normalize_address_fields(data["roles"])

    return DarwinDeployment(
        path=path,
        network=str(data["network"]),
        chain_id=int(data["chain_id"]),
        bond_asset_mode=str(data.get("bond_asset_mode", "external")),
        settlement_hub=contracts["settlement_hub"],
        contracts=contracts,
        roles=roles,
        deployer=normalize_evm_address(data["deployer"]),
        deployed_at=int(data["deployed_at"]),
        drw=data.get("drw"),
        market=data.get("market"),
        faucet=data.get("faucet"),
    )
