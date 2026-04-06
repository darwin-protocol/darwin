#!/usr/bin/env python3
"""Check whether a wallet is ready to seed a DRW market on Base Sepolia."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def http_post_json(url: str, payload: dict) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "darwin-market-preflight/0.1",
        },
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def rpc_json(url: str, method: str, params: list) -> dict:
    return http_post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def rpc_chain_id(url: str) -> int:
    return int(rpc_json(url, "eth_chainId", [])["result"], 16)


def rpc_balance(url: str, address: str) -> int:
    return int(rpc_json(url, "eth_getBalance", [address, "latest"])["result"], 16)


def rpc_call(url: str, address: str, data: str) -> str:
    return str(rpc_json(url, "eth_call", [{"to": address, "data": data}, "latest"])["result"])


def abi_encode_address(address: str) -> str:
    return address.lower().replace("0x", "").rjust(64, "0")


def decode_uint(result: str) -> int:
    if not result.startswith("0x"):
        raise ValueError(f"invalid uint result: {result}")
    return int(result, 16)


def decode_string(result: str) -> str:
    if not result.startswith("0x"):
        raise ValueError(f"invalid string result: {result}")
    data = bytes.fromhex(result[2:])
    if len(data) < 64:
        return ""
    offset = int.from_bytes(data[0:32], "big")
    if len(data) < offset + 64:
        return ""
    length = int.from_bytes(data[offset:offset + 32], "big")
    raw = data[offset + 32:offset + 32 + length]
    return raw.decode(errors="ignore")


def rpc_call_uint(url: str, address: str, selector: str) -> int:
    return decode_uint(rpc_call(url, address, selector))


def rpc_call_symbol(url: str, address: str) -> str:
    try:
        return decode_string(rpc_call(url, address, "0x95d89b41"))
    except Exception:
        return ""


def rpc_call_decimals(url: str, address: str) -> int:
    try:
        return rpc_call_uint(url, address, "0x313ce567")
    except Exception:
        return 18


def rpc_call_balance_of(url: str, token: str, holder: str) -> int:
    return rpc_call_uint(url, token, "0x70a08231" + abi_encode_address(holder))


def wei_to_unit(value: int, decimals: int) -> str:
    if decimals <= 0:
        return str(value)
    scale = 10 ** decimals
    whole = value // scale
    frac = value % scale
    if frac == 0:
        return str(whole)
    frac_text = str(frac).rjust(decimals, "0").rstrip("0")
    return f"{whole}.{frac_text}"


def default_base_rpc_url() -> str:
    if os.environ.get("BASE_SEPOLIA_RPC_URL"):
        return os.environ["BASE_SEPOLIA_RPC_URL"]
    if os.environ.get("DARWIN_RPC_URL"):
        return os.environ["DARWIN_RPC_URL"]
    if os.environ.get("ALCHEMY_API_KEY"):
        return f"https://base-sepolia.g.alchemy.com/v2/{os.environ['ALCHEMY_API_KEY']}"
    return "https://sepolia.base.org"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check DRW market bootstrap readiness")
    parser.add_argument("--deployment-file", default=str(ROOT / "ops" / "deployments" / "base-sepolia.json"))
    parser.add_argument("--wallet-address", default="")
    parser.add_argument("--quote-token", default="")
    parser.add_argument("--quote-symbol", default="")
    parser.add_argument("--base-rpc-url", default="")
    parser.add_argument("--json-out", default="")
    parser.add_argument("--markdown-out", default="")
    parser.add_argument("--min-base-eth-wei", default=str(10**15))
    args = parser.parse_args()

    deployment_path = Path(args.deployment_file).expanduser().resolve()
    deployment = json.loads(deployment_path.read_text())
    drw = deployment.get("drw") or {}
    drw_contracts = drw.get("contracts") or {}
    roles = deployment.get("roles") or {}

    wallet_address = args.wallet_address or roles.get("governance", "")
    quote_token = args.quote_token or deployment.get("contracts", {}).get("bond_asset", "")
    base_rpc_url = args.base_rpc_url or default_base_rpc_url()

    blockers: list[str] = []
    notes: list[str] = []
    checks: dict[str, dict] = {}

    chain_id = rpc_chain_id(base_rpc_url)
    expected_chain = int(deployment["chain_id"])
    chain_ok = chain_id == expected_chain
    checks["rpc_chain"] = {
        "state": "OK" if chain_ok else "FAIL",
        "detail": f"rpc_chain={chain_id} expected={expected_chain}",
    }
    if not chain_ok:
        blockers.append("rpc_chain_mismatch")

    if not wallet_address:
        blockers.append("missing_wallet_address")

    drw_token = drw_contracts.get("drw_token", "")
    if not drw_token:
        blockers.append("missing_drw_token")

    if not quote_token:
        blockers.append("missing_quote_token")

    base_balance = rpc_balance(base_rpc_url, wallet_address) if wallet_address else 0
    min_base_wei = int(args.min_base_eth_wei)
    base_ok = base_balance >= min_base_wei
    checks["gas_balance"] = {
        "state": "OK" if base_ok else "FAIL",
        "detail": f"base_eth={wei_to_unit(base_balance, 18)} min={wei_to_unit(min_base_wei, 18)}",
    }
    if not base_ok:
        blockers.append("insufficient_base_eth")

    drw_symbol = rpc_call_symbol(base_rpc_url, drw_token) if drw_token else "DRW"
    drw_decimals = rpc_call_decimals(base_rpc_url, drw_token) if drw_token else 18
    drw_balance = rpc_call_balance_of(base_rpc_url, drw_token, wallet_address) if drw_token and wallet_address else 0
    drw_ok = drw_balance > 0
    checks["drw_balance"] = {
        "state": "OK" if drw_ok else "FAIL",
        "detail": f"{drw_symbol or 'DRW'}={wei_to_unit(drw_balance, drw_decimals)}",
    }
    if not drw_ok:
        blockers.append("no_drw_balance")

    quote_symbol = args.quote_symbol or (rpc_call_symbol(base_rpc_url, quote_token) if quote_token else "")
    quote_decimals = rpc_call_decimals(base_rpc_url, quote_token) if quote_token else 18
    quote_balance = rpc_call_balance_of(base_rpc_url, quote_token, wallet_address) if quote_token and wallet_address else 0
    quote_ok = quote_balance > 0
    checks["quote_balance"] = {
        "state": "OK" if quote_ok else "FAIL",
        "detail": f"{quote_symbol or 'QUOTE'}={wei_to_unit(quote_balance, quote_decimals)}",
    }
    if not quote_ok:
        blockers.append("no_quote_token_balance")
        if quote_token.lower() == "0x4200000000000000000000000000000000000006" and base_balance > 0:
            notes.append("wallet has Base Sepolia ETH but zero WETH; wrap ETH before seeding a DRW/WETH pool")

    drw_live = bool(drw.get("enabled"))
    checks["deployment_drw"] = {
        "state": "OK" if drw_live else "FAIL",
        "detail": f"token={drw_token} staking={drw_contracts.get('drw_staking', '')}",
    }
    if not drw_live:
        blockers.append("deployment_has_no_live_drw")

    checks["market_pair"] = {
        "state": "INFO",
        "detail": f"recommended_pair={drw_symbol or 'DRW'}/{quote_symbol or 'QUOTE'}",
    }
    notes.append("do not self-trade for optics; seed a pool, publish the address, and rely on third-party swaps")
    notes.append("the current live canary still bonds in WETH even though DRW token/staking are live")

    report = {
        "generated_at": utc_now(),
        "ready": not blockers,
        "deployment": {
            "network": deployment["network"],
            "chain_id": expected_chain,
            "artifact": str(deployment_path),
            "drw_token": drw_token,
            "drw_staking": drw_contracts.get("drw_staking", ""),
            "quote_token": quote_token,
            "quote_symbol": quote_symbol,
            "wallet_address": wallet_address,
        },
        "checks": checks,
        "balances": {
            "base_eth_wei": str(base_balance),
            "drw_balance": str(drw_balance),
            "drw_symbol": drw_symbol or "DRW",
            "drw_decimals": drw_decimals,
            "quote_balance": str(quote_balance),
            "quote_symbol": quote_symbol or "QUOTE",
            "quote_decimals": quote_decimals,
        },
        "blockers": blockers,
        "notes": notes,
    }

    lines = [
        "# DARWIN Market Bootstrap",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Ready: `{report['ready']}`",
        f"- Network: `{deployment['network']}`",
        f"- Wallet: `{wallet_address}`",
        f"- DRW token: `{drw_token}`",
        f"- Quote token: `{quote_token}` `{quote_symbol or 'QUOTE'}`",
        "",
        "## Checks",
        "",
    ]
    for name, check in checks.items():
        lines.append(f"- `{name}`: `{check['state']}` {check['detail']}".rstrip())
    lines.extend(["", "## Blockers", ""])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(["", "## Notes", ""])
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("- none")
    markdown = "\n".join(lines) + "\n"

    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.markdown_out:
        path = Path(args.markdown_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(markdown)

    print("[market-bootstrap] DARWIN")
    print(f"  Ready:         {'yes' if report['ready'] else 'no'}")
    print(f"  Network:       {deployment['network']} chain={expected_chain}")
    print(f"  Wallet:        {wallet_address}")
    print(f"  DRW token:     {drw_token}")
    print(f"  Quote token:   {quote_token} ({quote_symbol or 'QUOTE'})")
    print(f"  Base ETH:      {wei_to_unit(base_balance, 18)}")
    print(f"  DRW balance:   {wei_to_unit(drw_balance, drw_decimals)} {drw_symbol or 'DRW'}")
    print(f"  Quote balance: {wei_to_unit(quote_balance, quote_decimals)} {quote_symbol or 'QUOTE'}")
    if blockers:
        print(f"  Blockers:      {', '.join(blockers)}")
        raise SystemExit(1)
    print("  Blockers:      none")


if __name__ == "__main__":
    main()
