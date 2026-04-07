#!/usr/bin/env python3
"""Build a Safe Transaction Builder batch for DARWIN vNext promotion."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SIM = ROOT / "sim"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIM))

from darwin_sim.sdk.deployments import load_deployment_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deployment-file",
        default=str(ROOT / "ops" / "deployments" / "base-sepolia.json"),
        help="Merged DARWIN deployment artifact",
    )
    parser.add_argument(
        "--vnext-file",
        default=str(ROOT / "ops" / "deployments" / "base-sepolia.vnext.json"),
        help="vNext sidecar artifact",
    )
    parser.add_argument("--out", required=True, help="Output Safe batch path")
    parser.add_argument("--batch-name", default="DARWIN vNext promotion", help="Batch display name")
    parser.add_argument("--description", default="", help="Optional batch description")
    parser.add_argument("--safe-address", default="", help="Optional Safe address metadata")
    parser.add_argument("--market-operator", default="", help="Optional new market operator to set before handoff")
    parser.add_argument(
        "--no-fund-distributor",
        action="store_true",
        help="Do not include the DRW transfer that funds the Merkle distributor",
    )
    return parser.parse_args()


def normalize_address(address: str, *, allow_empty: bool = False) -> str:
    if allow_empty and address == "":
        return ""
    if not isinstance(address, str) or not address.startswith("0x") or len(address) != 42:
        raise ValueError(f"invalid address: {address!r}")
    int(address[2:], 16)
    return "0x" + address[2:].lower()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def method(name: str, *inputs: tuple[str, str]) -> dict:
    return {
        "name": name,
        "payable": False,
        "inputs": [{"internalType": internal_type, "name": arg_name, "type": arg_type} for arg_name, internal_type, arg_type in inputs],
    }


def tx(to: str, contract_method: dict, values: dict[str, str]) -> dict:
    return {
        "to": normalize_address(to),
        "value": "0",
        "data": None,
        "contractMethod": contract_method,
        "contractInputsValues": values,
    }


def build_description(base: str, *, safe_address: str, timelock: str, distributor: str, total_amount: str) -> str:
    lines: list[str] = []
    if base:
        lines.append(base.strip())
    lines.append(f"Timelock: {timelock}")
    lines.append(f"Distributor: {distributor}")
    lines.append(f"Distribution total: {total_amount}")
    if safe_address:
        lines.append(f"Safe: {safe_address}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    deployment_path = Path(args.deployment_file).expanduser().resolve()
    vnext_path = Path(args.vnext_file).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    _, deployment, *_ = load_deployment_data(deployment_file=deployment_path)
    vnext_root = load_json(vnext_path)
    vnext = vnext_root["vnext"]
    contracts = deployment["contracts"]
    token = normalize_address(contracts["drw_token"])
    timelock = normalize_address(vnext["contracts"]["darwin_timelock"])
    distributor = normalize_address(vnext["contracts"]["drw_merkle_distributor"])
    total_amount = str(vnext["distribution"].get("total_amount", "0"))

    transactions: list[dict] = []
    if not args.no_fund_distributor and int(total_amount) > 0:
        transactions.append(
            tx(
                token,
                method(
                    "transfer",
                    ("to", "address", "address"),
                    ("amount", "uint256", "uint256"),
                ),
                {
                    "to": distributor,
                    "amount": total_amount,
                },
            )
        )

    reference_pool = contracts.get("reference_pool", "")
    if args.market_operator and reference_pool:
        transactions.append(
            tx(
                reference_pool,
                method(
                    "setMarketOperator",
                    ("newOperator", "address", "address"),
                ),
                {
                    "newOperator": normalize_address(args.market_operator),
                },
            )
        )

    for contract_name in ("drw_token", "drw_staking", "drw_faucet", "reference_pool"):
        contract_address = contracts.get(contract_name, "")
        if not contract_address:
            continue
        transactions.append(
            tx(
                contract_address,
                method(
                    "setGovernance",
                    ("newGovernance", "address", "address"),
                ),
                {
                    "newGovernance": timelock,
                },
            )
        )

    if not transactions:
        raise SystemExit("no vNext promotion transactions were generated")

    chain_id = str(vnext_root.get("chain_id") or deployment.get("chain_id"))
    safe_address = normalize_address(args.safe_address, allow_empty=True)
    payload = {
        "version": "1.0",
        "chainId": chain_id,
        "createdAt": int(time.time()),
        "meta": {
            "name": args.batch_name,
            "description": build_description(
                args.description,
                safe_address=safe_address,
                timelock=timelock,
                distributor=distributor,
                total_amount=total_amount,
            ),
        },
        "transactions": transactions,
    }
    if safe_address:
        payload["meta"]["safeAddress"] = safe_address

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    print("[vnext-safe-batch] ready")
    print(f"  deployment_file: {deployment_path}")
    print(f"  vnext_file:      {vnext_path}")
    print(f"  out:             {out_path}")
    print(f"  transactions:    {len(transactions)}")
    print(f"  timelock:        {timelock}")
    print(f"  distributor:     {distributor}")
    print(f"  total_amount:    {total_amount}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
