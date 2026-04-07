"""Security-oriented live role audit helpers for DARWIN deployments."""

from __future__ import annotations

from dataclasses import dataclass

from darwin_sim.sdk.accounts import normalize_evm_address
from darwin_sim.sdk.deployments import DarwinDeployment

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

# These contracts currently hard-wire governance in the constructor and expose no
# governance-rotation setter, so a governance-key compromise would still require
# redeployment for a full recovery.
IMMUTABLE_GOVERNANCE_CONTRACTS = (
    "bond_vault",
    "challenge_escrow",
    "epoch_manager",
    "score_registry",
    "settlement_hub",
    "shared_pair_vault",
    "species_registry",
)

# These contracts expose governance or operator mutation hooks, so they can be
# moved to a fresh wallet without redeploying the contract itself.
ROTATABLE_CONTRACTS = (
    "drw_token",
    "drw_staking",
    "drw_faucet",
    "reference_pool",
)


@dataclass(slots=True)
class LiveRoleState:
    token_governance: str
    token_genesis_operator: str
    token_genesis_finalized: bool
    staking_governance: str
    staking_genesis_operator: str
    faucet_governance: str
    pool_governance: str
    pool_market_operator: str
    hub_governance: str
    hub_batch_operator_deployer: bool
    hub_batch_operator_governance: bool


def _norm(address: str) -> str:
    if not address:
        return ZERO_ADDRESS
    return normalize_evm_address(address)


def build_role_audit_report(deployment: DarwinDeployment, live: LiveRoleState) -> dict:
    deployer = _norm(deployment.deployer)
    governance = _norm(deployment.roles["governance"])
    epoch_operator = _norm(deployment.roles["epoch_operator"])
    safe_mode_authority = _norm(deployment.roles["safe_mode_authority"])
    batch_operator = _norm(deployment.roles.get("batch_operator", governance))

    deployer_privileges: list[str] = []
    if _norm(live.token_genesis_operator) == deployer:
        deployer_privileges.append("drw_token.genesis_operator")
    if _norm(live.staking_genesis_operator) == deployer:
        deployer_privileges.append("drw_staking.genesis_operator")
    if live.hub_batch_operator_deployer:
        deployer_privileges.append("settlement_hub.batch_operator")
    if _norm(live.pool_market_operator) == deployer:
        deployer_privileges.append("reference_pool.market_operator")
    if deployer == governance:
        deployer_privileges.append("roles.governance")
    if deployer == epoch_operator:
        deployer_privileges.append("roles.epoch_operator")
    if deployer == safe_mode_authority:
        deployer_privileges.append("roles.safe_mode_authority")
    if deployer == batch_operator:
        deployer_privileges.append("roles.batch_operator")

    governance_checks = {
        "drw_token": _norm(live.token_governance) == governance,
        "drw_staking": _norm(live.staking_governance) == governance,
        "drw_faucet": _norm(live.faucet_governance) == governance,
        "reference_pool": _norm(live.pool_governance) == governance,
        "settlement_hub": _norm(live.hub_governance) == governance,
    }
    governance_drift = [label for label, ok in governance_checks.items() if not ok]

    deployer_retire_ready = (
        not deployer_privileges
        and _norm(live.token_genesis_operator) == ZERO_ADDRESS
        and _norm(live.staking_genesis_operator) == ZERO_ADDRESS
        and live.token_genesis_finalized
    )

    governance_root_summary = {
        "address": governance,
        "rotatable_contracts": list(ROTATABLE_CONTRACTS),
        "immutable_core_contracts": list(IMMUTABLE_GOVERNANCE_CONTRACTS),
        "compromise_requires_redeploy": True,
    }

    return {
        "deployer": deployer,
        "governance": governance,
        "epoch_operator": epoch_operator,
        "batch_operator": batch_operator,
        "safe_mode_authority": safe_mode_authority,
        "token_genesis_finalized": bool(live.token_genesis_finalized),
        "token_genesis_operator": _norm(live.token_genesis_operator),
        "staking_genesis_operator": _norm(live.staking_genesis_operator),
        "deployer_privileges": deployer_privileges,
        "deployer_retire_ready": deployer_retire_ready,
        "governance_matches_live": not governance_drift,
        "governance_drift": governance_drift,
        "governance_root_summary": governance_root_summary,
        "recommended_actions": _recommended_actions(
            deployer_retire_ready=deployer_retire_ready,
            deployer_privileges=deployer_privileges,
            governance_matches_live=not governance_drift,
        ),
    }


def _recommended_actions(
    *, deployer_retire_ready: bool, deployer_privileges: list[str], governance_matches_live: bool
) -> list[str]:
    actions: list[str] = []
    if deployer_retire_ready:
        actions.append("retire_old_deployer_for_future_deployments")
    else:
        actions.append("rotate_or_remove_remaining_deployer_privileges")
    if not governance_matches_live:
        actions.append("repair_governance_drift_before_any_rotation")
    actions.append("treat_governance_wallet_as_primary_root_of_trust")
    actions.append("if_governance_is_compromised_plan_full_core_redeploy")
    return actions
