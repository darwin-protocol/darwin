"""darwinctl — DARWIN operator CLI.

Commands:
  keys gen          Generate PQ + EVM keypair
  wallet init       Create an encrypted DARWIN wallet file
  wallet show       Inspect a DARWIN wallet's public data
  wallet export     Export public account material from a wallet file
  deployment show   Inspect a deployment artifact
  config lint       Validate a node config against schema
  intent create     Create and sign a dual-envelope intent
  intent verify     Verify a dual-envelope intent's signatures
  replay fetch      Mirror epoch artifacts from archive, then verify them
  status check      Inspect all overlay services from one command
  wallet check      Inspect deployer/testnet wallet balances
  replay verify     Watcher replay verification on published artifacts
  sim run-e2        Run E2 batch-lane uplift experiment
  sim run-suite     Run full E1-E7 experiment suite
  sim sweep         Run beta/epsilon parameter sweep
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from decimal import Decimal, getcontext
from datetime import datetime, timezone
from pathlib import Path
from getpass import getpass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

getcontext().prec = 40

_RPC_DEFAULTS = {
    1: "https://ethereum-rpc.publicnode.com",
    10: "https://optimism-rpc.publicnode.com",
    42161: "https://arb1.arbitrum.io/rpc",
    421614: "https://sepolia-rollup.arbitrum.io/rpc",
    8453: "https://mainnet.base.org",
    84532: "https://sepolia.base.org",
    11155111: "https://ethereum-sepolia-rpc.publicnode.com",
}


def _load_deployment_or_none(args):
    deployment_file = getattr(args, "deployment_file", None)
    network = getattr(args, "network", None)
    if not deployment_file and not network and "DARWIN_DEPLOYMENT_FILE" not in os.environ and "DARWIN_NETWORK" not in os.environ:
        return None

    from darwin_sim.sdk.deployments import load_deployment
    return load_deployment(deployment_file=deployment_file, network=network)


def _http_get_json(url: str) -> dict:
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _default_base_sepolia_rpc_url() -> str:
    if os.environ.get("BASE_SEPOLIA_RPC_URL"):
        return os.environ["BASE_SEPOLIA_RPC_URL"]
    if os.environ.get("DARWIN_RPC_URL"):
        return os.environ["DARWIN_RPC_URL"]
    if os.environ.get("ALCHEMY_API_KEY"):
        return f"https://base-sepolia.g.alchemy.com/v2/{os.environ['ALCHEMY_API_KEY']}"
    return "https://sepolia.base.org"


def _default_sepolia_rpc_url() -> str:
    if os.environ.get("SEPOLIA_RPC_URL"):
        return os.environ["SEPOLIA_RPC_URL"]
    if os.environ.get("ALCHEMY_API_KEY"):
        return f"https://eth-sepolia.g.alchemy.com/v2/{os.environ['ALCHEMY_API_KEY']}"
    return "https://ethereum-sepolia-rpc.publicnode.com"


def _default_rpc_url_for_chain(chain_id: int) -> str:
    return _RPC_DEFAULTS.get(int(chain_id), "")


def _resolve_deployment_rpc_url(args, deployment=None) -> str:
    direct = getattr(args, "rpc_url", "") or getattr(args, "base_rpc_url", "")
    if direct:
        return direct
    if os.environ.get("DARWIN_RPC_URL"):
        return os.environ["DARWIN_RPC_URL"]
    if deployment is not None:
        default = _default_rpc_url_for_chain(deployment.chain_id)
        if default:
            return default
    return _default_base_sepolia_rpc_url()


def _http_post_json(url: str, payload: dict) -> dict:
    req = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "darwinctl/0.1",
        },
        method="POST",
    )
    with urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def _rpc_json(url: str, method: str, params: list) -> dict:
    return _http_post_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})


def _rpc_chain_id(url: str) -> int:
    payload = _rpc_json(url, "eth_chainId", [])
    return int(payload["result"], 16)


def _rpc_balance(url: str, address: str) -> int:
    payload = _rpc_json(url, "eth_getBalance", [address, "latest"])
    return int(payload["result"], 16)


def _rpc_code(url: str, address: str) -> str:
    payload = _rpc_json(url, "eth_getCode", [address, "latest"])
    return str(payload["result"])


def _rpc_call(url: str, address: str, data: str) -> str:
    payload = _rpc_json(url, "eth_call", [{"to": address, "data": data}, "latest"])
    return str(payload["result"])


def _abi_encode_address(address: str) -> str:
    return address.lower().replace("0x", "").rjust(64, "0")


def _decode_address(result: str) -> str:
    from darwin_sim.sdk.accounts import normalize_evm_address

    if not result.startswith("0x") or len(result) < 66:
        raise ValueError(f"invalid eth_call address result: {result}")
    return normalize_evm_address("0x" + result[-40:])


def _decode_bool(result: str) -> bool:
    if not result.startswith("0x"):
        raise ValueError(f"invalid eth_call bool result: {result}")
    return int(result, 16) != 0


def _decode_uint(result: str) -> int:
    if not result.startswith("0x"):
        raise ValueError(f"invalid eth_call uint result: {result}")
    return int(result, 16)


def _rpc_call_address(url: str, address: str, selector: str) -> str:
    return _decode_address(_rpc_call(url, address, selector))


def _rpc_call_bool(url: str, address: str, call_data: str) -> bool:
    return _decode_bool(_rpc_call(url, address, call_data))


def _rpc_call_uint(url: str, address: str, call_data: str) -> int:
    return _decode_uint(_rpc_call(url, address, call_data))


def _rpc_call_erc20_balance(url: str, token: str, holder: str) -> int:
    return _rpc_call_uint(url, token, "0x70a08231" + _abi_encode_address(holder))


def _normalize_address(value: str) -> str:
    from darwin_sim.sdk.accounts import normalize_evm_address

    return normalize_evm_address(value)


def _aggregate_expected_drw_balances(drw: dict | None) -> dict[str, int]:
    allocations = (drw or {}).get("allocations", {})
    expected: dict[str, int] = {}
    for bucket in (
        ("treasury_recipient", "treasury_amount"),
        ("insurance_recipient", "insurance_amount"),
        ("sponsor_rewards_recipient", "sponsor_rewards_amount"),
        ("community_recipient", "community_amount"),
        ("staking_recipient", "staking_amount"),
    ):
        recipient = allocations.get(bucket[0], "")
        amount = int(allocations.get(bucket[1], 0) or 0)
        if not recipient or amount <= 0:
            continue
        normalized = _normalize_address(recipient)
        expected[normalized] = expected.get(normalized, 0) + amount
    return expected


def _effective_mutable_governance(deployment) -> str:
    governance = deployment.roles.get("governance", "")
    vnext = deployment.vnext or {}
    contracts = vnext.get("contracts", {}) if isinstance(vnext, dict) else {}
    timelock = contracts.get("darwin_timelock", "") if isinstance(contracts, dict) else ""
    selected = timelock or governance
    return _normalize_address(selected) if selected else ""


def _build_expected_drw_windows(deployment) -> dict[str, dict[str, int | bool]]:
    allocations = (deployment.drw or {}).get("allocations", {})
    windows: dict[str, dict[str, int | bool]] = {}
    buckets = (
        ("treasury_recipient", "treasury_amount", False),
        ("insurance_recipient", "insurance_amount", False),
        ("sponsor_rewards_recipient", "sponsor_rewards_amount", False),
        # Community allocation is intentionally spendable after launch.
        ("community_recipient", "community_amount", True),
        ("staking_recipient", "staking_amount", False),
    )
    for recipient_key, amount_key, allows_variance in buckets:
        recipient = allocations.get(recipient_key, "")
        amount = int(allocations.get(amount_key, 0) or 0)
        if not recipient or amount <= 0:
            continue
        normalized = _normalize_address(recipient)
        detail = windows.setdefault(
            normalized,
            {
                "expected": 0,
                "minimum": 0,
                "variable_amount": 0,
                "allows_variance": False,
            },
        )
        detail["expected"] = int(detail["expected"]) + amount
        if allows_variance:
            detail["variable_amount"] = int(detail["variable_amount"]) + amount
            detail["allows_variance"] = True
        else:
            detail["minimum"] = int(detail["minimum"]) + amount
    return windows


def _wei_to_eth(wei: int) -> str:
    return f"{(Decimal(wei) / Decimal(10**18)):.8f}"


def _utc_timestamp(ts: float | None = None) -> str:
    observed = ts if ts is not None else time.time()
    return datetime.fromtimestamp(observed, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _write_report(path_value: str, content: str) -> None:
    path = Path(path_value)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(content)
    tmp_path.replace(path)


def _render_status_markdown(report: dict) -> str:
    lines = [
        "# DARWIN Status Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Overall status: `{'READY' if report['ready'] else 'BLOCKED'}`",
        f"- Cold watcher allowed: `{report['allow_cold_watcher']}`",
    ]

    deployment = report.get("deployment")
    if deployment:
        roles = deployment.get("roles", {})
        lines.extend([
            f"- Deployment: `{deployment['network']}` chain `{deployment['chain_id']}` mode `{deployment['bond_asset_mode']}`",
            f"- Settlement hub: `{deployment['settlement_hub']}`",
            f"- Bond asset: `{deployment['bond_asset']}`",
            f"- Governance: `{roles.get('governance', '')}`",
            f"- Epoch operator: `{roles.get('epoch_operator', '')}`",
            f"- Batch operator: `{roles.get('batch_operator', roles.get('epoch_operator', ''))}`",
            f"- Safe mode authority: `{roles.get('safe_mode_authority', '')}`",
        ])
        drw = deployment.get("drw")
        if drw:
            contracts = drw.get("contracts", {})
            lines.extend([
                f"- DRW enabled: `{drw.get('enabled', False)}`",
                f"- DRW token: `{contracts.get('drw_token', '')}`",
                f"- DRW staking: `{contracts.get('drw_staking', '')}`",
                f"- DRW supply: `{drw.get('total_supply', '')}`",
                f"- DRW duration: `{drw.get('staking_duration', '')}`",
            ])

    lines.extend([
        "",
        "## Services",
        "",
        "| Check | State | Detail |",
        "|---|---|---|",
    ])

    for name, status in report["checks"].items():
        detail = status.get("detail", "")
        lines.append(f"| `{name}` | `{status['state']}` | `{detail}` |")

    onchain_auth = report.get("onchain_auth")
    if onchain_auth:
        lines.extend(["", "## On-Chain Auth", ""])
        for name, detail in onchain_auth.get("components", {}).items():
            state = "OK" if detail.get("ok") else "FAIL"
            lines.append(f"- `{name}`: `{state}` {detail.get('summary', '')}".rstrip())

    onchain_drw = report.get("onchain_drw")
    if onchain_drw:
        lines.extend(["", "## On-Chain DRW", ""])
        lines.append(
            f"- Summary: `{'OK' if onchain_drw.get('ok') else 'FAIL'}` "
            f"holders=`{len(onchain_drw.get('holders', {}))}` "
            f"tracked_supply=`{onchain_drw.get('tracked_total', 0)}`/"
            f"`{onchain_drw.get('expected_total_supply', 0)}`"
        )
        for holder, detail in sorted(onchain_drw.get("holders", {}).items()):
            if detail.get("allows_variance"):
                lines.append(
                    f"- `{holder}`: minimum=`{detail.get('minimum', 0)}` "
                    f"expected=`{detail.get('expected', 0)}` "
                    f"observed=`{detail.get('observed', 0)}`"
                )
            else:
                lines.append(
                    f"- `{holder}`: expected=`{detail.get('expected', 0)}` "
                    f"observed=`{detail.get('observed', 0)}`"
                )
        for label, detail in sorted(onchain_drw.get("auxiliary_holders", {}).items()):
            lines.append(
                f"- `{label}` (`{detail.get('holder', '')}`): observed=`{detail.get('observed', 0)}`"
            )
        if "circulating_total" in onchain_drw:
            lines.append(f"- circulating=`{onchain_drw.get('circulating_total', 0)}`")

    blockers = report.get("blockers", [])
    lines.extend(["", "## Blockers", ""])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")

    notes = report.get("notes", [])
    lines.extend(["", "## Notes", ""])
    if notes:
        lines.extend(f"- {note}" for note in notes)
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def _resolve_wallet_passphrase(args, require: bool = True) -> str:
    direct = getattr(args, "passphrase", "") or ""
    if direct:
        return direct

    env_name = getattr(args, "passphrase_env", "") or "DARWIN_WALLET_PASSPHRASE"
    if env_name and os.environ.get(env_name):
        return os.environ[env_name]

    if require and sys.stdin.isatty():
        return getpass("DARWIN wallet passphrase: ")

    if require:
        raise ValueError("wallet passphrase is required (--passphrase or DARWIN_WALLET_PASSPHRASE)")
    return ""


def cmd_keys_gen(args):
    from darwin_sim.sdk.accounts import create_account
    deployment = _load_deployment_or_none(args)
    chain_id = args.chain_id if args.chain_id is not None else (deployment.chain_id if deployment else 1)
    account = create_account(chain_id=chain_id)
    out = Path(args.out) if args.out else Path("darwin_account.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(account.to_dict(), f, indent=2)
    print(f"[darwinctl] Account created")
    print(f"  acct_id:  {account.acct_id}")
    print(f"  evm_addr: {account.evm_addr}")
    print(f"  chain_id: {account.chain_id}")
    print(f"  PQ hot:   {account.pq_hot_pk.hex()[:16]}...")
    print(f"  PQ cold:  {account.pq_cold_pk.hex()[:16]}...")
    print(f"  Output:   {out}")
    print("  Note:     public account material only; use wallet-init for a reusable signing wallet")


def cmd_wallet_init(args):
    from darwin_sim.sdk.wallets import create_wallet, save_wallet

    deployment = _load_deployment_or_none(args)
    chain_id = args.chain_id if args.chain_id is not None else (deployment.chain_id if deployment else 1)
    passphrase = _resolve_wallet_passphrase(args)
    wallet = create_wallet(
        label=args.label,
        chain_id=chain_id,
        hot_capabilities=int(args.hot_capabilities, 0),
        hot_value_limit_usd=args.hot_value_limit_usd,
        recovery_delay_sec=args.recovery_delay_sec,
    )
    out = Path(args.out) if args.out else Path("darwin_wallet.json")
    save_wallet(wallet, out, passphrase)
    print("[darwinctl] Wallet created")
    print(f"  label:      {wallet.label or '-'}")
    print(f"  acct_id:    {wallet.account.acct_id}")
    print(f"  evm_addr:   {wallet.account.evm_addr}")
    print(f"  chain_id:   {wallet.account.chain_id}")
    print(f"  created_at: {wallet.created_at}")
    print(f"  output:     {out}")


def cmd_wallet_show(args):
    from darwin_sim.sdk.wallets import load_wallet_metadata

    wallet = load_wallet_metadata(args.wallet_file)
    public_account = wallet["public_account"]
    print("[darwinctl] Wallet")
    print(f"  label:       {wallet.get('label', '') or '-'}")
    print(f"  created_at:  {wallet.get('created_at', '')}")
    print(f"  acct_id:     {public_account.get('acct_id', '')}")
    print(f"  evm_addr:    {public_account.get('evm_addr', '')}")
    print(f"  chain_id:    {public_account.get('chain_id', '')}")
    print(f"  capabilities:{public_account.get('hot_capabilities', '')}")
    print(f"  value_limit: {public_account.get('hot_value_limit_usd', '')}")
    print(f"  recovery:    {public_account.get('recovery_delay_sec', '')}")
    print(f"  path:        {Path(args.wallet_file).resolve()}")


def cmd_wallet_export_public(args):
    from darwin_sim.sdk.wallets import load_wallet_metadata

    wallet = load_wallet_metadata(args.wallet_file)
    out = Path(args.out) if args.out else Path("darwin_account.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(wallet["public_account"], indent=2) + "\n")
    print("[darwinctl] Wallet public account exported")
    print(f"  acct_id:    {wallet['public_account'].get('acct_id', '')}")
    print(f"  evm_addr:   {wallet['public_account'].get('evm_addr', '')}")
    print(f"  output:     {out}")


def _encode_token_amount(amount_text: str, decimals: int) -> int:
    amount = Decimal(str(amount_text))
    if amount <= 0:
        raise ValueError("amount must be positive")
    scale = Decimal(10) ** decimals
    return int((amount * scale).to_integral_value())


def cmd_wallet_request(args):
    from darwin_sim.sdk.wallets import load_wallet_metadata

    deployment = _load_deployment_or_none(args)
    if deployment is None or not deployment.drw:
        print("[darwinctl] wallet-request requires a deployment artifact with DRW enabled")
        sys.exit(1)

    wallet = load_wallet_metadata(args.wallet_file)
    public_account = wallet["public_account"]
    recipient = args.recipient or public_account.get("evm_addr", "")
    if not recipient:
        print("[darwinctl] wallet-request could not resolve a recipient address")
        sys.exit(1)

    drw = deployment.drw or {}
    contracts = drw.get("contracts", {})
    token_address = contracts.get("drw_token", "")
    if not token_address:
        print("[darwinctl] wallet-request requires a DRW token address in the deployment artifact")
        sys.exit(1)

    decimals = int(drw.get("decimals", 18) or 18)
    amount_text = str(args.amount).strip() if args.amount else ""
    uri = f"ethereum:{token_address}@{deployment.chain_id}/transfer?address={recipient}"
    if amount_text:
        uri = f"{uri}&uint256={_encode_token_amount(amount_text, decimals)}"

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(uri + "\n")

    print("[darwinctl] Wallet request")
    print(f"  wallet:     {Path(args.wallet_file).resolve()}")
    print(f"  recipient:  {recipient}")
    print(f"  token:      {token_address}")
    print(f"  chain_id:   {deployment.chain_id}")
    print(f"  amount:     {amount_text or '-'}")
    if args.out:
        print(f"  output:     {Path(args.out).resolve()}")
    print(f"  uri:        {uri}")


def cmd_deployment_show(args):
    deployment = _load_deployment_or_none(args)
    if deployment is None:
        print("[darwinctl] deployment-show requires --deployment-file, --network, or DARWIN_DEPLOYMENT_FILE")
        sys.exit(1)

    print("[darwinctl] Deployment artifact")
    print(f"  Path:             {deployment.path}")
    print(f"  Network:          {deployment.network}")
    print(f"  Chain ID:         {deployment.chain_id}")
    print(f"  Bond asset mode:  {deployment.bond_asset_mode}")
    print(f"  Bond asset:       {deployment.contracts.get('bond_asset', '')}")
    print(f"  Settlement hub:   {deployment.settlement_hub}")
    if deployment.has_private_operator_fields:
        print(f"  Governance:       {deployment.roles.get('governance', '')}")
        print(f"  Epoch operator:   {deployment.roles.get('epoch_operator', '')}")
        if deployment.roles.get("batch_operator"):
            print(f"  Batch operator:   {deployment.roles['batch_operator']}")
        print(f"  Safe mode auth:   {deployment.roles.get('safe_mode_authority', '')}")
    else:
        print("  Operator roles:   local private overlay not loaded")
    if deployment.drw:
        drw = deployment.drw
        contracts = drw.get("contracts", {})
        allocations = drw.get("allocations", {})
        print("  DRW enabled:      yes")
        print(f"  DRW token:        {contracts.get('drw_token', '')}")
        print(f"  DRW staking:      {contracts.get('drw_staking', '')}")
        print(f"  DRW supply:       {drw.get('total_supply', '')}")
        print(f"  DRW duration:     {drw.get('staking_duration', '')}")
        if allocations.get("treasury_recipient"):
            print(f"  DRW treasury:     {allocations.get('treasury_recipient', '')} ({allocations.get('treasury_amount', '')})")
            print(
                f"  DRW insurance:    {allocations.get('insurance_recipient', '')} ({allocations.get('insurance_amount', '')})"
            )
            print(
                "  DRW staking res:  "
                f"{allocations.get('staking_recipient', '')} ({allocations.get('staking_amount', '')})"
            )
        else:
            print(f"  DRW treasury:     hidden ({allocations.get('treasury_amount', '')})")
            print(f"  DRW insurance:    hidden ({allocations.get('insurance_amount', '')})")
            print(f"  DRW staking res:  contract ({allocations.get('staking_amount', '')})")
    else:
        print("  DRW enabled:      no")
    if deployment.market:
        market = deployment.market
        contracts = market.get("contracts", {})
        print("  Market enabled:   yes")
        print(f"  Market venue:     {market.get('venue_id', '')}")
        print(f"  Market type:      {market.get('venue_type', '')}")
        print(f"  Market pool:      {contracts.get('reference_pool', '')}")
        print(f"  Market operator:  {market.get('market_operator', 'hidden') or 'hidden'}")
        print(f"  Market base:      {market.get('base_token', '')}")
        print(f"  Market quote:     {market.get('quote_token', '')}")
        print(f"  Market fee bps:   {market.get('fee_bps', '')}")
        print(f"  Market seeded:    {market.get('seeded', False)}")
    else:
        print("  Market enabled:   no")
    if deployment.faucet:
        faucet = deployment.faucet
        contracts = faucet.get("contracts", {})
        print("  Faucet enabled:   yes")
        print(f"  Faucet contract:  {contracts.get('drw_faucet', '')}")
        print(f"  Faucet claim:     {faucet.get('claim_amount', '')}")
        print(f"  Faucet native:    {faucet.get('native_drip_amount', '')}")
        print(f"  Faucet cooldown:  {faucet.get('claim_cooldown', '')}")
        print(f"  Faucet funded:    {faucet.get('funded', False)}")
    else:
        print("  Faucet enabled:   no")


def cmd_role_audit(args):
    deployment = _load_deployment_or_none(args)
    if deployment is None:
        print("[darwinctl] role-audit requires --deployment-file, --network, or DARWIN_DEPLOYMENT_FILE")
        sys.exit(1)
    if not deployment.has_private_operator_fields:
        overlay = deployment.private_overlay_path or Path("~/.config/darwin/deployments").expanduser()
        print("[darwinctl] role-audit requires a local private deployment overlay")
        print(f"  expected_overlay:       {overlay}")
        sys.exit(1)

    base_rpc_url = _resolve_deployment_rpc_url(args, deployment)
    contracts = deployment.contracts

    from darwin_sim.sdk.role_audit import LiveRoleState, build_role_audit_report

    live = LiveRoleState(
        token_governance = _rpc_call_address(base_rpc_url, contracts["drw_token"], "0x5aa6e675"),
        token_genesis_operator = _rpc_call_address(base_rpc_url, contracts["drw_token"], "0x018b2a45"),
        token_genesis_finalized = _rpc_call_bool(base_rpc_url, contracts["drw_token"], "0x4421d5f5"),
        staking_governance = _rpc_call_address(base_rpc_url, contracts["drw_staking"], "0x5aa6e675"),
        staking_genesis_operator = _rpc_call_address(base_rpc_url, contracts["drw_staking"], "0x018b2a45"),
        faucet_governance = _rpc_call_address(base_rpc_url, contracts["drw_faucet"], "0x5aa6e675"),
        pool_governance = _rpc_call_address(base_rpc_url, contracts["reference_pool"], "0x5aa6e675"),
        pool_market_operator = _rpc_call_address(base_rpc_url, contracts["reference_pool"], "0xb1ae3471"),
        hub_governance = _rpc_call_address(base_rpc_url, contracts["settlement_hub"], "0x5aa6e675"),
        hub_batch_operator_deployer = _rpc_call_bool(
            base_rpc_url, contracts["settlement_hub"], "0xd220935c" + _abi_encode_address(deployment.deployer)
        ),
        hub_batch_operator_governance = _rpc_call_bool(
            base_rpc_url,
            contracts["settlement_hub"],
            "0xd220935c" + _abi_encode_address(deployment.roles["governance"]),
        ),
    )
    report = build_role_audit_report(deployment, live)

    if args.json_out:
        _write_report(args.json_out, json.dumps(report, indent=2, sort_keys=True) + "\n")

    print("[darwinctl] Live role audit")
    print(f"  Network:                {deployment.network}")
    print(f"  Chain ID:               {deployment.chain_id}")
    print(f"  RPC:                    {base_rpc_url}")
    print(f"  Deployer:               {report['deployer']}")
    print(f"  Governance:             {report['governance']}")
    if report["effective_mutable_governance"] != report["governance"]:
        print(f"  Mutable governance:     {report['effective_mutable_governance']}")
    print(f"  Epoch operator:         {report['epoch_operator']}")
    print(f"  Batch operator:         {report['batch_operator']}")
    print(f"  Safe mode auth:         {report['safe_mode_authority']}")
    print(f"  Token genesis closed:   {'yes' if report['token_genesis_finalized'] else 'no'}")
    print(f"  Token genesis operator: {report['token_genesis_operator']}")
    print(f"  Staking genesis admin:  {report['staking_genesis_operator']}")
    print(f"  Deployer retire ready:  {'yes' if report['deployer_retire_ready'] else 'no'}")
    print(f"  Governance drift:       {'none' if not report['governance_drift'] else ', '.join(report['governance_drift'])}")
    if report["deployer_privileges"]:
        print(f"  Deployer privileges:    {', '.join(report['deployer_privileges'])}")
    else:
        print("  Deployer privileges:    none")
    print(
        "  Governance root:       "
        f"rotatable={','.join(report['governance_root_summary']['rotatable_contracts'])} "
        f"immutable={','.join(report['governance_root_summary']['immutable_core_contracts'])}"
    )
    if args.json_out:
        print(f"  JSON report:            {Path(args.json_out).resolve()}")


def cmd_config_lint(args):
    from darwin_sim.core.config import SimConfig
    try:
        cfg = SimConfig.from_yaml(args.config)
        # Validate critical fields
        errors = []
        if not cfg.pairs:
            errors.append("No pairs defined")
        if not cfg.species:
            errors.append("No species defined")
        if cfg.rebalance.kappa_reb <= 0 or cfg.rebalance.kappa_reb > 1:
            errors.append(f"kappa_reb={cfg.rebalance.kappa_reb} out of range (0,1]. gain_bps={cfg.rebalance.gain_bps}")
        if abs(sum([cfg.scoring.weights.trader_surplus, cfg.scoring.weights.lp_return,
                     cfg.scoring.weights.fill_rate, cfg.scoring.weights.revenue,
                     cfg.scoring.weights.adverse_markout, cfg.scoring.weights.risk_penalty]) - 1.0) > 0.01:
            errors.append("Scoring weight coefficients don't sum to 1.0")

        sentinel_found = any(s.id == "S0_SENTINEL" for s in cfg.species)
        if not sentinel_found:
            errors.append("S0_SENTINEL species missing — constitutional baseline required")

        if errors:
            print(f"[darwinctl] Config INVALID: {args.config}")
            for e in errors:
                print(f"  ERROR: {e}")
            sys.exit(1)
        else:
            print(f"[darwinctl] Config VALID: {args.config}")
            print(f"  suite_id: {cfg.suite_id}")
            print(f"  pairs: {cfg.pairs}")
            print(f"  species: {[s.id for s in cfg.species]}")
            print(f"  kappa_reb: {cfg.rebalance.kappa_reb} (gain_bps={cfg.rebalance.gain_bps} / 10000)")
            print(f"  control_share: {cfg.epochs.control_share_bps_default/100:.1f}%")
    except Exception as e:
        print(f"[darwinctl] Config FAILED: {e}")
        sys.exit(1)


def cmd_intent_create(args):
    from darwin_sim.sdk.intents import create_intent, verify_pq_sig, verify_evm_sig, verify_binding
    from darwin_sim.sdk.accounts import create_account
    from darwin_sim.sdk.wallets import load_wallet

    deployment = _load_deployment_or_none(args)
    chain_id = args.chain_id if args.chain_id is not None else (deployment.chain_id if deployment else 1)
    settlement_hub = args.settlement_hub if args.settlement_hub is not None else (
        deployment.settlement_hub if deployment else "0x0000000000000000000000000000000000000000"
    )
    if args.wallet_file:
        passphrase = _resolve_wallet_passphrase(args)
        wallet = load_wallet(args.wallet_file, passphrase)
        account = wallet.account
        if account.chain_id != chain_id:
            raise ValueError(f"wallet chain_id {account.chain_id} does not match requested chain_id {chain_id}")
    else:
        account = create_account(chain_id=chain_id)
    intent = create_intent(
        account=account,
        pair_id=args.pair,
        side=args.side.upper(),
        qty_base=args.qty,
        limit_price=args.price,
        max_slippage_bps=args.slippage,
        profile=args.profile.upper(),
        expiry_ts=int(time.time()) + 300,
        nonce=1,
        chain_id=chain_id,
        settlement_hub=settlement_hub,
    )

    # Verify
    pq_ok = verify_pq_sig(account, intent)
    evm_ok = verify_evm_sig(account, intent)
    bind_ok = verify_binding(intent)

    out = Path(args.out) if args.out else Path("intent.json")
    with out.open("w") as f:
        json.dump(intent.to_dict(), f, indent=2)

    print(f"[darwinctl] Intent created")
    print(f"  intent_hash: {intent.intent_hash}")
    print(f"  acct_id:     {intent.acct_id}")
    print(f"  pair:        {intent.pair_id}")
    print(f"  side:        {intent.side}")
    print(f"  qty:         {intent.qty_base}")
    print(f"  price:       {intent.limit_price}")
    print(f"  profile:     {intent.profile}")
    print(f"  chain_id:    {intent.chain_id}")
    print(f"  settle_hub:  {intent.settlement_hub}")
    print(f"  PQ sig OK:   {pq_ok}")
    print(f"  EVM sig OK:  {evm_ok}")
    print(f"  Binding OK:  {bind_ok}")
    print(f"  Output:      {out}")
    if args.wallet_file:
        print(f"  Wallet:      {Path(args.wallet_file).resolve()}")


def cmd_intent_verify(args):
    from darwin_sim.sdk.accounts import ZERO_EVM_ADDRESS, normalize_evm_address
    from darwin_sim.sdk.intents import verify_intent_payload

    payload = json.loads(Path(args.intent_file).read_text())
    ok, reason = verify_intent_payload(payload)
    if not ok:
        print("[darwinctl] Intent verification: FAIL")
        print(f"  Reason:      {reason}")
        sys.exit(1)

    deployment = _load_deployment_or_none(args)
    deployment_status = "unbound"
    if deployment is not None:
        chain_id = int(payload["evm_leg"].get("chain_id", 0))
        settlement_hub = normalize_evm_address(payload["evm_leg"].get("settlement_hub", ZERO_EVM_ADDRESS))
        if chain_id != deployment.chain_id:
            print("[darwinctl] Intent verification: FAIL")
            print("  Reason:      deployment_chain_id_mismatch")
            sys.exit(1)
        if settlement_hub != deployment.settlement_hub:
            print("[darwinctl] Intent verification: FAIL")
            print("  Reason:      deployment_settlement_hub_mismatch")
            sys.exit(1)
        deployment_status = "matched"

    print("[darwinctl] Intent verification: PASS")
    print(f"  Intent hash: {payload.get('intent_hash', '')}")
    print(f"  Account:     {payload.get('pq_leg', {}).get('acct_id', '')}")
    print(f"  Chain ID:    {payload.get('evm_leg', {}).get('chain_id', '')}")
    print(f"  Settle hub:  {payload.get('evm_leg', {}).get('settlement_hub', '')}")
    print(f"  Deployment:  {deployment_status}")


def cmd_replay_verify(args):
    from darwin_sim.watcher.replay import replay_and_verify, write_replay_report
    result = replay_and_verify(args.artifacts)
    report_path = write_replay_report(args.artifacts, result)
    status = "PASS" if result["passed"] else "FAIL"
    print(f"[darwinctl] Replay verification: {status}")
    print(f"  Control fills:   {result['control_fills_loaded']}")
    print(f"  Treatment fills: {result['treatment_fills_loaded']}")
    print(f"  Recomputed:      {result['recomputed_uplift']}")
    print(f"  Published:       {result['published_uplift']}")
    print(f"  Report:          {report_path}")
    if result["mismatches"]:
        print(f"  MISMATCHES ({len(result['mismatches'])}):")
        for m in result["mismatches"]:
            print(f"    {m}")
    if not result["passed"]:
        sys.exit(1)


def cmd_replay_fetch(args):
    from darwin_sim.watcher.archive import ArchiveSyncError, mirror_epoch_from_archive
    from darwin_sim.watcher.replay import replay_and_verify, write_replay_report

    try:
        sync = mirror_epoch_from_archive(args.archive_url, args.out, epoch_id=args.epoch)
    except ArchiveSyncError as exc:
        print("[darwinctl] Archive replay: FAIL")
        print(f"  Reason:          {exc}")
        sys.exit(1)

    result = replay_and_verify(sync["artifact_dir"])
    report_path = write_replay_report(sync["artifact_dir"], result)
    status = "PASS" if result["passed"] else "FAIL"

    print(f"[darwinctl] Archive replay: {status}")
    print(f"  Epoch:           {sync['epoch_id']}")
    print(f"  Artifact dir:    {sync['artifact_dir']}")
    print(f"  Files mirrored:  {sync['file_count']}")
    print(f"  Control fills:   {result['control_fills_loaded']}")
    print(f"  Treatment fills: {result['treatment_fills_loaded']}")
    print(f"  Recomputed:      {result['recomputed_uplift']}")
    print(f"  Published:       {result['published_uplift']}")
    print(f"  Report:          {report_path}")
    if result["mismatches"]:
        print(f"  MISMATCHES ({len(result['mismatches'])}):")
        for mismatch in result["mismatches"]:
            print(f"    {mismatch}")
    if not result["passed"]:
        sys.exit(1)


def cmd_status_check(args):
    endpoints = [
        ("archive", args.archive_url.rstrip("/") + "/healthz", True),
        ("gateway", args.gateway_url.rstrip("/") + "/healthz", True),
        ("router", args.router_url.rstrip("/") + "/healthz", True),
        ("scorer", args.scorer_url.rstrip("/") + "/healthz", True),
        ("watcher", args.watcher_url.rstrip("/") + "/healthz", True),
        ("finalizer", args.finalizer_url.rstrip("/") + "/healthz", True),
        ("sentinel", args.sentinel_url.rstrip("/") + "/healthz", True),
        ("watcher_ready", args.watcher_url.rstrip("/") + "/readyz", False),
        ("watcher_status", args.watcher_url.rstrip("/") + "/v1/status", False),
        ("router_status", args.router_url.rstrip("/") + "/v1/status", False),
        ("finalizer_status", args.finalizer_url.rstrip("/") + "/v1/status", False),
        ("sentinel_status", args.sentinel_url.rstrip("/") + "/v1/status", False),
        ("gateway_config", args.gateway_url.rstrip("/") + "/v1/config", False),
    ]

    results: dict[str, dict] = {}
    failures: list[str] = []
    deployment = _load_deployment_or_none(args)
    report = {
        "generated_at": _utc_timestamp(),
        "allow_cold_watcher": bool(args.allow_cold_watcher),
        "checks": {},
        "failures": failures,
        "notes": [],
        "blockers": [],
        "ready": False,
    }

    for name, url, required in endpoints:
        try:
            payload = _http_get_json(url)
            results[name] = {"ok": True, "payload": payload}
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            results[name] = {"ok": False, "error": str(exc)}
            if required:
                failures.append(name)

    print("[darwinctl] Overlay status")
    for service in ("archive", "gateway", "router", "scorer", "watcher", "finalizer", "sentinel"):
        result = results[service]
        status = "UP" if result["ok"] else "DOWN"
        detail = result["payload"].get("status", "ok") if result["ok"] else result["error"]
        print(f"  {service:12} {status:4} {detail}")
        report["checks"][service] = {
            "state": status,
            "detail": detail,
            "required": True,
        }

    watcher_ready = results["watcher_ready"]
    watcher_ready_failed = False
    if watcher_ready["ok"]:
        payload = watcher_ready["payload"]
        print(
            f"  {'watcher_ready':12} {'YES' if payload.get('ready') else 'NO ':4} "
            f"epochs={payload.get('epochs_replayed', 0)} mirrored={payload.get('last_mirrored_epoch', '')}"
        )
        watcher_ready_failed = not payload.get("ready")
        report["checks"]["watcher_ready"] = {
            "state": "YES" if payload.get("ready") else "NO",
            "detail": (
                f"epochs={payload.get('epochs_replayed', 0)} "
                f"mirrored={payload.get('last_mirrored_epoch', '')}"
            ).strip(),
            "required": not args.allow_cold_watcher,
        }
    else:
        if args.allow_cold_watcher and "HTTP Error 503" in watcher_ready["error"]:
            print(f"  {'watcher_ready':12} COLD {watcher_ready['error']}")
            report["checks"]["watcher_ready"] = {
                "state": "COLD",
                "detail": watcher_ready["error"],
                "required": False,
            }
            report["notes"].append("watcher bootstrap is still cold; first archive replay remains pending")
        else:
            print(f"  {'watcher_ready':12} DOWN {watcher_ready['error']}")
            watcher_ready_failed = True
            report["checks"]["watcher_ready"] = {
                "state": "DOWN",
                "detail": watcher_ready["error"],
                "required": not args.allow_cold_watcher,
            }

    if watcher_ready_failed and not args.allow_cold_watcher:
        failures.append("watcher_ready")

    watcher_status = results["watcher_status"]
    if watcher_status["ok"]:
        payload = watcher_status["payload"]
        health = payload.get("health", {})
        print(
            f"  {'watcher_sync':12} {'ON ' if health.get('auto_sync') else 'OFF':4} "
            f"poll={health.get('poll_interval_sec', 0)}s failures={health.get('consecutive_failures', 0)}"
        )
        report["checks"]["watcher_sync"] = {
            "state": "ON" if health.get("auto_sync") else "OFF",
            "detail": (
                f"poll={health.get('poll_interval_sec', 0)}s "
                f"failures={health.get('consecutive_failures', 0)}"
            ),
            "required": False,
        }
    else:
        print(f"  {'watcher_sync':12} DOWN {watcher_status['error']}")
        report["checks"]["watcher_sync"] = {
            "state": "DOWN",
            "detail": watcher_status["error"],
            "required": False,
        }

    router_status = results["router_status"]
    if router_status["ok"]:
        payload = router_status["payload"]
        print(
            f"  {'router_flow':12} {'OK ':4} "
            f"routed={payload.get('total_routed', 0)} control={payload.get('control_share_bps', 0)}bps"
        )
        report["checks"]["router_flow"] = {
            "state": "OK",
            "detail": (
                f"routed={payload.get('total_routed', 0)} "
                f"control={payload.get('control_share_bps', 0)}bps"
            ),
            "required": False,
        }
    else:
        print(f"  {'router_flow':12} DOWN {router_status['error']}")
        report["checks"]["router_flow"] = {
            "state": "DOWN",
            "detail": router_status["error"],
            "required": False,
        }

    finalizer_status = results["finalizer_status"]
    if finalizer_status["ok"]:
        payload = finalizer_status["payload"]
        print(
            f"  {'finalizer':12} {'AUTO' if payload.get('auto_finalize') else 'MAN ':4} "
            f"registered={payload.get('registered_epochs', 0)} finalized={payload.get('finalized_epochs', 0)}"
        )
        report["checks"]["finalizer_status"] = {
            "state": "AUTO" if payload.get("auto_finalize") else "MAN",
            "detail": (
                f"registered={payload.get('registered_epochs', 0)} "
                f"finalized={payload.get('finalized_epochs', 0)}"
            ),
            "required": False,
        }
    else:
        print(f"  {'finalizer':12} DOWN {finalizer_status['error']}")
        report["checks"]["finalizer_status"] = {
            "state": "DOWN",
            "detail": finalizer_status["error"],
            "required": False,
        }

    sentinel_status = results["sentinel_status"]
    if sentinel_status["ok"]:
        payload = sentinel_status["payload"]
        safe_mode = bool(payload.get("safe_mode"))
        stale = payload.get("stale_services", {})
        print(
            f"  {'sentinel':12} {'SAFE' if safe_mode else 'OK ':4} "
            f"alerts={payload.get('alert_count', 0)} stale={len(stale)}"
        )
        report["checks"]["sentinel_status"] = {
            "state": "SAFE" if safe_mode else "OK",
            "detail": f"alerts={payload.get('alert_count', 0)} stale={len(stale)}",
            "required": False,
        }
        if safe_mode:
            failures.append("sentinel_safe_mode")
        if stale:
            failures.append("sentinel_stale_services")
    else:
        print(f"  {'sentinel':12} DOWN {sentinel_status['error']}")
        report["checks"]["sentinel_status"] = {
            "state": "DOWN",
            "detail": sentinel_status["error"],
            "required": False,
        }

    gateway_config = results["gateway_config"]
    if gateway_config["ok"]:
        payload = gateway_config["payload"]
        print(
            f"  {'gateway_cfg':12} {'OK ':4} "
            f"chain={payload.get('allowed_chain_id', '')} hub={payload.get('allowed_settlement_hub', '')}"
        )
        report["checks"]["gateway_cfg"] = {
            "state": "OK",
            "detail": (
                f"chain={payload.get('allowed_chain_id', '')} "
                f"hub={payload.get('allowed_settlement_hub', '')}"
            ),
            "required": False,
        }
    else:
        print(f"  {'gateway_cfg':12} DOWN {gateway_config['error']}")
        report["checks"]["gateway_cfg"] = {
            "state": "DOWN",
            "detail": gateway_config["error"],
            "required": False,
        }

    if deployment is not None:
        print(
            f"  {'deployment':12} {'PIN':4} "
            f"{deployment.network} chain={deployment.chain_id} mode={deployment.bond_asset_mode}"
        )
        report["deployment"] = {
            "network": deployment.network,
            "chain_id": deployment.chain_id,
            "bond_asset_mode": deployment.bond_asset_mode,
            "bond_asset": deployment.contracts.get("bond_asset", ""),
            "settlement_hub": deployment.settlement_hub,
            "artifact": str(deployment.path),
            "drw": deployment.drw,
        }
        if deployment.has_private_operator_fields:
            report["deployment"]["deployer"] = deployment.deployer
            report["deployment"]["roles"] = deployment.roles
            effective_mutable_governance = _effective_mutable_governance(deployment)
            if effective_mutable_governance and effective_mutable_governance != deployment.roles["governance"]:
                report["deployment"]["effective_mutable_governance"] = effective_mutable_governance
        report["checks"]["deployment"] = {
            "state": "PIN",
            "detail": f"{deployment.network} chain={deployment.chain_id} mode={deployment.bond_asset_mode}",
            "required": False,
        }

        if gateway_config["ok"]:
            payload = gateway_config["payload"]
            if payload.get("allowed_chain_id") != deployment.chain_id:
                failures.append("gateway_chain_policy_mismatch")
            if str(payload.get("allowed_settlement_hub", "")).lower() != deployment.settlement_hub:
                failures.append("gateway_settlement_hub_mismatch")
        else:
            failures.append("gateway_config_unreachable")

        base_rpc_url = _resolve_deployment_rpc_url(args, deployment)
        try:
            rpc_chain_id = _rpc_chain_id(base_rpc_url)
            if rpc_chain_id != deployment.chain_id:
                failures.append("deployment_chain_id_mismatch")

            deployed = 0
            missing: list[str] = []
            for name, address in deployment.contracts.items():
                code = _rpc_code(base_rpc_url, address)
                if code and code != "0x":
                    deployed += 1
                else:
                    missing.append(name)

            status = "OK " if not missing and rpc_chain_id == deployment.chain_id else "FAIL"
            print(
                f"  {'onchain':12} {status:4} "
                f"rpc_chain={rpc_chain_id} contracts={deployed}/{len(deployment.contracts)}"
            )
            report["checks"]["onchain"] = {
                "state": status.strip(),
                "detail": f"rpc_chain={rpc_chain_id} contracts={deployed}/{len(deployment.contracts)}",
                "required": False,
            }
            report["onchain"] = {
                "ok": not missing and rpc_chain_id == deployment.chain_id,
                "rpc_chain_id": rpc_chain_id,
                "contracts_present": deployed,
                "contracts_total": len(deployment.contracts),
                "missing": missing,
            }
            if missing:
                print(f"  {'missing_code':12} {', '.join(missing)}")
                failures.append("deployment_code_missing")
        except Exception as exc:  # noqa: BLE001
            print(f"  {'onchain':12} DOWN {exc}")
            report["checks"]["onchain"] = {
                "state": "DOWN",
                "detail": str(exc),
                "required": False,
            }
            report["onchain"] = {"ok": False, "error": str(exc)}
            failures.append("deployment_rpc_unreachable")

        if not deployment.has_private_operator_fields:
            print(f"  {'authz':12} SKIP private overlay not loaded")
            report["checks"]["onchain_auth"] = {
                "state": "SKIP",
                "detail": "private overlay not loaded",
                "required": False,
            }
            report["onchain_auth"] = {"ok": False, "skipped": True, "reason": "private overlay not loaded"}
        else:
            try:
                auth_failures: list[str] = []
                auth_components: dict[str, dict] = {}
                expected_governance = deployment.roles["governance"]
                expected_mutable_governance = _effective_mutable_governance(deployment) or expected_governance
                expected_safe_mode = deployment.roles["safe_mode_authority"]
                expected_batch_operator = deployment.roles.get("batch_operator") or deployment.roles["epoch_operator"]
                expected_epoch_operator = deployment.roles["epoch_operator"]
                expected_bond_asset = deployment.contracts.get("bond_asset", "")
                expected_challenge_escrow = deployment.contracts.get("challenge_escrow", "")

                settlement_hub = deployment.contracts.get("settlement_hub", "")
                if settlement_hub:
                    observed_governance = _rpc_call_address(base_rpc_url, settlement_hub, "0x5aa6e675")
                    observed_safe_mode = _rpc_call_address(base_rpc_url, settlement_hub, "0x6900b3a3")
                    observed_batch_operator = _rpc_call_bool(
                        base_rpc_url,
                        settlement_hub,
                        "0xd220935c" + _abi_encode_address(expected_batch_operator),
                    )
                    settlement_ok = (
                        observed_governance == expected_governance
                        and observed_safe_mode == expected_safe_mode
                        and observed_batch_operator
                    )
                    auth_components["settlement_hub"] = {
                        "ok": settlement_ok,
                        "expected": {
                            "governance": expected_governance,
                            "safe_mode_authority": expected_safe_mode,
                            "batch_operator": expected_batch_operator,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "safe_mode_authority": observed_safe_mode,
                            "batch_operator_allowed": observed_batch_operator,
                        },
                        "summary": (
                            f"governance={observed_governance} safe_mode={observed_safe_mode} "
                            f"batch_operator={'yes' if observed_batch_operator else 'no'}"
                        ),
                    }
                    if observed_governance != expected_governance:
                        auth_failures.append("deployment_settlement_governance_mismatch")
                    if observed_safe_mode != expected_safe_mode:
                        auth_failures.append("deployment_safe_mode_authority_mismatch")
                    if not observed_batch_operator:
                        auth_failures.append("deployment_batch_operator_mismatch")

                challenge_escrow = deployment.contracts.get("challenge_escrow", "")
                if challenge_escrow:
                    observed_governance = _rpc_call_address(base_rpc_url, challenge_escrow, "0x5aa6e675")
                    observed_bond_asset = _rpc_call_address(base_rpc_url, challenge_escrow, "0xbabef33e")
                    escrow_ok = observed_governance == expected_governance and observed_bond_asset == expected_bond_asset
                    auth_components["challenge_escrow"] = {
                        "ok": escrow_ok,
                        "expected": {
                            "governance": expected_governance,
                            "bond_asset": expected_bond_asset,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "bond_asset": observed_bond_asset,
                        },
                        "summary": f"governance={observed_governance} bond_asset={observed_bond_asset}",
                    }
                    if observed_governance != expected_governance:
                        auth_failures.append("deployment_challenge_escrow_governance_mismatch")
                    if expected_bond_asset and observed_bond_asset != expected_bond_asset:
                        auth_failures.append("deployment_challenge_escrow_bond_asset_mismatch")

                bond_vault = deployment.contracts.get("bond_vault", "")
                if bond_vault:
                    observed_governance = _rpc_call_address(base_rpc_url, bond_vault, "0x5aa6e675")
                    observed_challenge_escrow = _rpc_call_address(base_rpc_url, bond_vault, "0x92433067")
                    observed_bond_asset = _rpc_call_address(base_rpc_url, bond_vault, "0xbabef33e")
                    vault_ok = (
                        observed_governance == expected_governance
                        and observed_challenge_escrow == expected_challenge_escrow
                        and observed_bond_asset == expected_bond_asset
                    )
                    auth_components["bond_vault"] = {
                        "ok": vault_ok,
                        "expected": {
                            "governance": expected_governance,
                            "challenge_escrow": expected_challenge_escrow,
                            "bond_asset": expected_bond_asset,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "challenge_escrow": observed_challenge_escrow,
                            "bond_asset": observed_bond_asset,
                        },
                        "summary": (
                            f"governance={observed_governance} escrow={observed_challenge_escrow} "
                            f"bond_asset={observed_bond_asset}"
                        ),
                    }
                    if observed_governance != expected_governance:
                        auth_failures.append("deployment_bond_vault_governance_mismatch")
                    if expected_challenge_escrow and observed_challenge_escrow != expected_challenge_escrow:
                        auth_failures.append("deployment_bond_vault_challenge_escrow_mismatch")
                    if expected_bond_asset and observed_bond_asset != expected_bond_asset:
                        auth_failures.append("deployment_bond_vault_bond_asset_mismatch")

                species_registry = deployment.contracts.get("species_registry", "")
                if species_registry:
                    observed_governance = _rpc_call_address(base_rpc_url, species_registry, "0x5aa6e675")
                    observed_epoch_operator = _rpc_call_address(base_rpc_url, species_registry, "0x1942c738")
                    observed_challenge_escrow = _rpc_call_address(base_rpc_url, species_registry, "0x92433067")
                    registry_ok = (
                        observed_governance == expected_governance
                        and observed_epoch_operator == expected_epoch_operator
                        and observed_challenge_escrow == expected_challenge_escrow
                    )
                    auth_components["species_registry"] = {
                        "ok": registry_ok,
                        "expected": {
                            "governance": expected_governance,
                            "epoch_operator": expected_epoch_operator,
                            "challenge_escrow": expected_challenge_escrow,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "epoch_operator": observed_epoch_operator,
                            "challenge_escrow": observed_challenge_escrow,
                        },
                        "summary": (
                            f"governance={observed_governance} epoch_operator={observed_epoch_operator} "
                            f"escrow={observed_challenge_escrow}"
                        ),
                    }
                    if observed_governance != expected_governance:
                        auth_failures.append("deployment_species_registry_governance_mismatch")
                    if observed_epoch_operator != expected_epoch_operator:
                        auth_failures.append("deployment_species_registry_epoch_operator_mismatch")
                    if expected_challenge_escrow and observed_challenge_escrow != expected_challenge_escrow:
                        auth_failures.append("deployment_species_registry_challenge_escrow_mismatch")

                score_registry = deployment.contracts.get("score_registry", "")
                if score_registry:
                    observed_governance = _rpc_call_address(base_rpc_url, score_registry, "0x5aa6e675")
                    observed_epoch_operator = _rpc_call_address(base_rpc_url, score_registry, "0x1942c738")
                    score_ok = observed_governance == expected_governance and observed_epoch_operator == expected_epoch_operator
                    auth_components["score_registry"] = {
                        "ok": score_ok,
                        "expected": {
                            "governance": expected_governance,
                            "epoch_operator": expected_epoch_operator,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "epoch_operator": observed_epoch_operator,
                        },
                        "summary": (
                            f"governance={observed_governance} "
                            f"epoch_operator={observed_epoch_operator}"
                        ),
                    }
                    if observed_governance != expected_governance:
                        auth_failures.append("deployment_score_registry_governance_mismatch")
                    if observed_epoch_operator != expected_epoch_operator:
                        auth_failures.append("deployment_score_registry_epoch_operator_mismatch")

                drw_token = deployment.contracts.get("drw_token", "")
                if drw_token:
                    observed_governance = _rpc_call_address(base_rpc_url, drw_token, "0x5aa6e675")
                    observed_finalized = _rpc_call_bool(base_rpc_url, drw_token, "0x4421d5f5")
                    observed_total_supply = _rpc_call_uint(base_rpc_url, drw_token, "0x18160ddd")
                    expected_total_supply = int((deployment.drw or {}).get("total_supply", 0))
                    token_ok = (
                        observed_governance == expected_mutable_governance
                        and observed_finalized
                        and (expected_total_supply == 0 or observed_total_supply == expected_total_supply)
                    )
                    auth_components["drw_token"] = {
                        "ok": token_ok,
                        "expected": {
                            "governance": expected_mutable_governance,
                            "genesis_finalized": True,
                            "total_supply": expected_total_supply,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "genesis_finalized": observed_finalized,
                            "total_supply": observed_total_supply,
                        },
                        "summary": (
                            f"governance={observed_governance} "
                            f"genesis_finalized={'yes' if observed_finalized else 'no'} "
                            f"total_supply={observed_total_supply}"
                        ),
                    }
                    if observed_governance != expected_mutable_governance:
                        auth_failures.append("deployment_drw_token_governance_mismatch")
                    if not observed_finalized:
                        auth_failures.append("deployment_drw_token_genesis_open")
                    if expected_total_supply and observed_total_supply != expected_total_supply:
                        auth_failures.append("deployment_drw_token_supply_mismatch")

                drw_staking = deployment.contracts.get("drw_staking", "")
                if drw_staking:
                    observed_governance = _rpc_call_address(base_rpc_url, drw_staking, "0x5aa6e675")
                    observed_token = _rpc_call_address(base_rpc_url, drw_staking, "0x6891e77c")
                    observed_duration = _rpc_call_uint(base_rpc_url, drw_staking, "0xf520e7e5")
                    expected_duration = int((deployment.drw or {}).get("staking_duration", 0))
                    staking_ok = (
                        observed_governance == expected_mutable_governance
                        and (not drw_token or observed_token == drw_token)
                        and (expected_duration == 0 or observed_duration == expected_duration)
                    )
                    auth_components["drw_staking"] = {
                        "ok": staking_ok,
                        "expected": {
                            "governance": expected_mutable_governance,
                            "drw_token": drw_token,
                            "reward_duration": expected_duration,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "drw_token": observed_token,
                            "reward_duration": observed_duration,
                        },
                        "summary": (
                            f"governance={observed_governance} "
                            f"token={observed_token} duration={observed_duration}"
                        ),
                    }
                    if observed_governance != expected_mutable_governance:
                        auth_failures.append("deployment_drw_staking_governance_mismatch")
                    if drw_token and observed_token != drw_token:
                        auth_failures.append("deployment_drw_staking_token_mismatch")
                    if expected_duration and observed_duration != expected_duration:
                        auth_failures.append("deployment_drw_staking_duration_mismatch")

                drw_faucet = deployment.contracts.get("drw_faucet", "")
                if drw_faucet:
                    observed_governance = _rpc_call_address(base_rpc_url, drw_faucet, "0x5aa6e675")
                    faucet_ok = observed_governance == expected_mutable_governance
                    auth_components["drw_faucet"] = {
                        "ok": faucet_ok,
                        "expected": {
                            "governance": expected_mutable_governance,
                        },
                        "observed": {
                            "governance": observed_governance,
                        },
                        "summary": f"governance={observed_governance}",
                    }
                    if observed_governance != expected_mutable_governance:
                        auth_failures.append("deployment_drw_faucet_governance_mismatch")

                reference_pool = deployment.contracts.get("reference_pool", "")
                if reference_pool:
                    observed_governance = _rpc_call_address(base_rpc_url, reference_pool, "0x5aa6e675")
                    observed_market_operator = _rpc_call_address(base_rpc_url, reference_pool, "0xb1ae3471")
                    expected_market_operator = (
                        (deployment.market or {}).get("market_operator")
                        or expected_governance
                    )
                    if expected_market_operator:
                        expected_market_operator = _normalize_address(expected_market_operator)
                    pool_ok = (
                        observed_governance == expected_mutable_governance
                        and (not expected_market_operator or observed_market_operator == expected_market_operator)
                    )
                    auth_components["reference_pool"] = {
                        "ok": pool_ok,
                        "expected": {
                            "governance": expected_mutable_governance,
                            "market_operator": expected_market_operator,
                        },
                        "observed": {
                            "governance": observed_governance,
                            "market_operator": observed_market_operator,
                        },
                        "summary": (
                            f"governance={observed_governance} "
                            f"market_operator={observed_market_operator}"
                        ),
                    }
                    if observed_governance != expected_mutable_governance:
                        auth_failures.append("deployment_reference_pool_governance_mismatch")
                    if expected_market_operator and observed_market_operator != expected_market_operator:
                        auth_failures.append("deployment_reference_pool_market_operator_mismatch")

                drw_expected_windows = _build_expected_drw_windows(deployment)
                if drw_token and drw_expected_windows:
                    expected_total_supply = int((deployment.drw or {}).get("total_supply", 0) or 0)
                    observed_holders: dict[str, dict[str, int]] = {}
                    tracked_total = 0
                    for holder, expected_window in sorted(drw_expected_windows.items()):
                        observed_amount = _rpc_call_erc20_balance(base_rpc_url, drw_token, holder)
                        observed_holders[holder] = {
                            "expected": int(expected_window["expected"]),
                            "minimum": int(expected_window["minimum"]),
                            "variable_amount": int(expected_window["variable_amount"]),
                            "allows_variance": bool(expected_window["allows_variance"]),
                            "observed": observed_amount,
                        }
                        tracked_total += observed_amount

                    auxiliary_holders: dict[str, dict[str, int | str]] = {}
                    auxiliary_total = 0
                    auxiliary_contracts = {
                        "drw_faucet": drw_faucet,
                        "reference_pool": reference_pool,
                        "drw_merkle_distributor": ((deployment.vnext or {}).get("contracts") or {}).get(
                            "drw_merkle_distributor", ""
                        ),
                    }
                    for label, holder in auxiliary_contracts.items():
                        if not holder:
                            continue
                        normalized = _normalize_address(holder)
                        if normalized in observed_holders:
                            continue
                        observed_amount = _rpc_call_erc20_balance(base_rpc_url, drw_token, normalized)
                        auxiliary_holders[label] = {
                            "holder": normalized,
                            "observed": observed_amount,
                        }
                        auxiliary_total += observed_amount

                    circulating_total = (
                        expected_total_supply - tracked_total - auxiliary_total if expected_total_supply else 0
                    )
                    drw_balances_ok = (
                        all(
                            (
                                detail["observed"] == detail["expected"]
                                if not detail["allows_variance"]
                                else detail["observed"] >= detail["minimum"]
                            )
                            for detail in observed_holders.values()
                        )
                        and (expected_total_supply == 0 or circulating_total >= 0)
                    )
                    print(
                        f"  {'onchain_drw':12} {'OK ' if drw_balances_ok else 'FAIL':4} "
                        f"holders={len(observed_holders)} tracked_supply={tracked_total}/{expected_total_supply}"
                    )
                    report["checks"]["onchain_drw"] = {
                        "state": "OK" if drw_balances_ok else "FAIL",
                        "detail": f"holders={len(observed_holders)} tracked_supply={tracked_total}/{expected_total_supply}",
                        "required": False,
                    }
                    report["onchain_drw"] = {
                        "ok": drw_balances_ok,
                        "holders": observed_holders,
                        "tracked_total": tracked_total,
                        "auxiliary_holders": auxiliary_holders,
                        "auxiliary_total": auxiliary_total,
                        "circulating_total": max(circulating_total, 0),
                        "expected_total_supply": expected_total_supply,
                    }
                    if not drw_balances_ok:
                        auth_failures.append("deployment_drw_allocation_mismatch")

                auth_ok = not auth_failures
                print(
                    f"  {'authz':12} {'OK ' if auth_ok else 'FAIL':4} "
                    f"components={len(auth_components)} batch_operator={expected_batch_operator}"
                )
                report["checks"]["onchain_auth"] = {
                    "state": "OK" if auth_ok else "FAIL",
                    "detail": f"components={len(auth_components)} batch_operator={expected_batch_operator}",
                    "required": False,
                }
                report["onchain_auth"] = {
                    "ok": auth_ok,
                    "components": auth_components,
                }
                failures.extend(auth_failures)
            except Exception as exc:  # noqa: BLE001
                print(f"  {'authz':12} DOWN {exc}")
                report["checks"]["onchain_auth"] = {
                    "state": "DOWN",
                    "detail": str(exc),
                    "required": False,
                }
                report["onchain_auth"] = {"ok": False, "error": str(exc)}
                failures.append("deployment_auth_unverifiable")

    blocker_messages = {
        "watcher_ready": "watcher has not replayed an epoch yet",
        "sentinel_safe_mode": "sentinel entered safe mode and settlement should be halted",
        "sentinel_stale_services": "sentinel detected stale overlay service heartbeats",
        "gateway_chain_policy_mismatch": "gateway chain policy does not match the pinned deployment",
        "gateway_settlement_hub_mismatch": "gateway settlement hub policy does not match the pinned deployment",
        "gateway_config_unreachable": "gateway config endpoint is unreachable; deployment pinning is unverified",
        "deployment_chain_id_mismatch": "RPC chain id does not match the pinned deployment",
        "deployment_code_missing": "one or more pinned contracts have no code on the target chain",
        "deployment_rpc_unreachable": "Base Sepolia RPC is unreachable for pinned deployment verification",
        "deployment_auth_unverifiable": "on-chain auth wiring could not be verified for the pinned deployment",
        "deployment_settlement_governance_mismatch": "settlement hub governance does not match the pinned deployment",
        "deployment_safe_mode_authority_mismatch": "settlement hub safe-mode authority does not match the pinned deployment",
        "deployment_batch_operator_mismatch": "settlement hub batch operator is not authorized as pinned",
        "deployment_challenge_escrow_governance_mismatch": "challenge escrow governance does not match the pinned deployment",
        "deployment_challenge_escrow_bond_asset_mismatch": "challenge escrow bond asset does not match the pinned deployment",
        "deployment_bond_vault_governance_mismatch": "bond vault governance does not match the pinned deployment",
        "deployment_bond_vault_challenge_escrow_mismatch": "bond vault challenge escrow does not match the pinned deployment",
        "deployment_bond_vault_bond_asset_mismatch": "bond vault bond asset does not match the pinned deployment",
        "deployment_species_registry_governance_mismatch": "species registry governance does not match the pinned deployment",
        "deployment_species_registry_epoch_operator_mismatch": "species registry epoch operator does not match the pinned deployment",
        "deployment_species_registry_challenge_escrow_mismatch": "species registry challenge escrow does not match the pinned deployment",
        "deployment_score_registry_governance_mismatch": "score registry governance does not match the pinned deployment",
        "deployment_score_registry_epoch_operator_mismatch": "score registry epoch operator does not match the pinned deployment",
        "deployment_drw_token_governance_mismatch": "DRW token governance does not match the pinned deployment",
        "deployment_drw_token_genesis_open": "DRW token genesis is still open and not finalized",
        "deployment_drw_token_supply_mismatch": "DRW token total supply does not match the pinned deployment",
        "deployment_drw_staking_governance_mismatch": "DRW staking governance does not match the pinned deployment",
        "deployment_drw_staking_token_mismatch": "DRW staking token does not match the pinned deployment",
        "deployment_drw_staking_duration_mismatch": "DRW staking reward duration does not match the pinned deployment",
        "deployment_drw_faucet_governance_mismatch": "DRW faucet governance does not match the pinned deployment",
        "deployment_reference_pool_governance_mismatch": "reference pool governance does not match the pinned deployment",
        "deployment_reference_pool_market_operator_mismatch": "reference pool market operator does not match the pinned deployment",
        "deployment_drw_allocation_mismatch": "DRW holder balances do not match the pinned deployment allocations",
    }
    report["blockers"] = [blocker_messages.get(name, name) for name in failures]
    watcher_state = report["checks"].get("watcher_ready", {}).get("state", "")
    report["ready"] = (not failures) and watcher_state not in {"COLD", "NO", "DOWN"}
    if watcher_state == "COLD":
        report["blockers"].append("watcher bootstrap incomplete: first archive replay still pending")

    if args.json_out:
        _write_report(args.json_out, json.dumps(report, indent=2, sort_keys=True) + "\n")
    if args.markdown_out:
        _write_report(args.markdown_out, _render_status_markdown(report))

    if failures:
        sys.exit(1)


def cmd_wallet_check(args):
    address = args.address or os.environ.get("DARWIN_DEPLOYER_ADDRESS") or os.environ.get("DARWIN_EXPECTED_DEPLOYER")
    if not address:
        print("[darwinctl] wallet-check requires --address or DARWIN_DEPLOYER_ADDRESS")
        sys.exit(1)

    base_rpc_url = args.base_rpc_url or _default_base_sepolia_rpc_url()
    sepolia_rpc_url = args.sepolia_rpc_url or _default_sepolia_rpc_url()
    expected = args.expect_address.lower() if args.expect_address else ""
    observed = address.lower()
    failures: list[str] = []

    try:
        base_chain_id = _rpc_chain_id(base_rpc_url)
        base_balance = _rpc_balance(base_rpc_url, address)
    except Exception as exc:  # noqa: BLE001
        print("[darwinctl] Wallet check: FAIL")
        print(f"  Base RPC:     {base_rpc_url}")
        print(f"  Reason:       {exc}")
        sys.exit(1)

    try:
        sepolia_chain_id = _rpc_chain_id(sepolia_rpc_url)
        sepolia_balance = _rpc_balance(sepolia_rpc_url, address)
    except Exception:
        sepolia_chain_id = 0
        sepolia_balance = 0

    if expected and observed != expected:
        failures.append("address_mismatch")
    if base_chain_id != 84532:
        failures.append("unexpected_base_chain_id")

    print("[darwinctl] Wallet check")
    print(f"  Address:            {address}")
    if expected:
        print(f"  Expected address:   {args.expect_address}")
        print(f"  Address match:      {observed == expected}")
    print(f"  Base RPC:           {base_rpc_url}")
    print(f"  Base chain id:      {base_chain_id}")
    print(f"  Base balance ETH:   {_wei_to_eth(base_balance)}")
    print(f"  Sepolia RPC:        {sepolia_rpc_url}")
    print(f"  Sepolia chain id:   {sepolia_chain_id or 'unreachable'}")
    print(f"  Sepolia balance:    {_wei_to_eth(sepolia_balance)}")

    if failures:
        print(f"  Status:             FAIL ({', '.join(failures)})")
        sys.exit(1)
    print("  Status:             OK")


def cmd_sim_e2(args):
    from darwin_sim.core.config import SimConfig
    from darwin_sim.experiments.runner import run_e2
    cfg = SimConfig.from_yaml(args.config)
    run_e2(cfg, args.data, args.out)


def cmd_sim_suite(args):
    from darwin_sim.core.config import SimConfig
    from darwin_sim.experiments.suite import run_full_suite
    cfg = SimConfig.from_yaml(args.config)
    run_full_suite(cfg, args.out, n_swaps=args.n_swaps, seed=args.seed)


def cmd_sim_sweep(args):
    from darwin_sim.core.config import SimConfig
    from darwin_sim.experiments.sweep import run_parameter_sweep
    cfg = SimConfig.from_yaml(args.config)
    run_parameter_sweep(cfg, args.out, n_swaps=args.n_swaps, seed=args.seed)


def main():
    parser = argparse.ArgumentParser(prog="darwinctl", description="DARWIN operator CLI")
    sub = parser.add_subparsers(dest="command")

    # keys gen
    p = sub.add_parser("keys-gen", help="Generate PQ + EVM keypair")
    p.add_argument("--chain-id", type=int)
    p.add_argument("--deployment-file")
    p.add_argument("--network")
    p.add_argument("--out", default="darwin_account.json")

    # wallet init
    p = sub.add_parser("wallet-init", help="Create an encrypted DARWIN wallet")
    p.add_argument("--chain-id", type=int)
    p.add_argument("--deployment-file")
    p.add_argument("--network")
    p.add_argument("--label", default="")
    p.add_argument("--hot-capabilities", default="0xff")
    p.add_argument("--hot-value-limit-usd", type=int, default=50_000)
    p.add_argument("--recovery-delay-sec", type=int, default=86400)
    p.add_argument("--passphrase", default="")
    p.add_argument("--passphrase-env", default="DARWIN_WALLET_PASSPHRASE")
    p.add_argument("--out", default="darwin_wallet.json")

    # wallet show
    p = sub.add_parser("wallet-show", help="Show DARWIN wallet public metadata")
    p.add_argument("wallet_file")

    # wallet export
    p = sub.add_parser("wallet-export-public", help="Export public account material from a wallet")
    p.add_argument("wallet_file")
    p.add_argument("--out", default="darwin_account.json")

    # wallet request
    p = sub.add_parser("wallet-request", help="Build a shareable DRW transfer request URI for a wallet")
    p.add_argument("wallet_file")
    p.add_argument("--deployment-file")
    p.add_argument("--network")
    p.add_argument("--recipient", default="")
    p.add_argument("--amount", default="")
    p.add_argument("--out", default="")

    # deployment show
    p = sub.add_parser("deployment-show", help="Inspect a deployment artifact")
    p.add_argument("--deployment-file")
    p.add_argument("--network")

    # role audit
    p = sub.add_parser("role-audit", help="Audit live privileged roles for a deployment")
    p.add_argument("--deployment-file")
    p.add_argument("--network")
    p.add_argument("--rpc-url", default="")
    p.add_argument("--base-rpc-url", default="")
    p.add_argument("--json-out", default="")

    # config lint
    p = sub.add_parser("config-lint", help="Validate config")
    p.add_argument("config")

    # intent create
    p = sub.add_parser("intent-create", help="Create dual-envelope intent")
    p.add_argument("--pair", default="ETH_USDC")
    p.add_argument("--side", default="BUY")
    p.add_argument("--qty", type=float, default=1.0)
    p.add_argument("--price", type=float, default=3500.0)
    p.add_argument("--slippage", type=int, default=50)
    p.add_argument("--profile", default="BALANCED")
    p.add_argument("--chain-id", type=int)
    p.add_argument("--settlement-hub")
    p.add_argument("--wallet-file", default="")
    p.add_argument("--passphrase", default="")
    p.add_argument("--passphrase-env", default="DARWIN_WALLET_PASSPHRASE")
    p.add_argument("--deployment-file")
    p.add_argument("--network")
    p.add_argument("--out", default="intent.json")

    # intent verify
    p = sub.add_parser("intent-verify", help="Verify dual-envelope intent")
    p.add_argument("intent_file")
    p.add_argument("--deployment-file")
    p.add_argument("--network")

    # replay verify
    p = sub.add_parser("replay-verify", help="Watcher replay verification")
    p.add_argument("artifacts", help="Path to artifact directory")

    # replay fetch
    p = sub.add_parser("replay-fetch", help="Mirror an archive epoch and verify it")
    p.add_argument("--archive-url", required=True)
    p.add_argument("--epoch", default="latest")
    p.add_argument("--out", default="watcher_artifacts")

    # status check
    p = sub.add_parser("status-check", help="Check overlay/archive readiness")
    p.add_argument("--archive-url", default="http://127.0.0.1:9447")
    p.add_argument("--gateway-url", default="http://127.0.0.1:9443")
    p.add_argument("--router-url", default="http://127.0.0.1:9444")
    p.add_argument("--scorer-url", default="http://127.0.0.1:9445")
    p.add_argument("--watcher-url", default="http://127.0.0.1:9446")
    p.add_argument("--finalizer-url", default="http://127.0.0.1:9448")
    p.add_argument("--sentinel-url", default="http://127.0.0.1:9449")
    p.add_argument("--deployment-file")
    p.add_argument("--network")
    p.add_argument("--rpc-url", default="")
    p.add_argument("--base-rpc-url", default="")
    p.add_argument("--allow-cold-watcher", action="store_true")
    p.add_argument("--json-out", default="")
    p.add_argument("--markdown-out", default="")

    # wallet check
    p = sub.add_parser("wallet-check", help="Inspect deployer/testnet wallet balances")
    p.add_argument("--address")
    p.add_argument("--expect-address")
    p.add_argument("--base-rpc-url", default="")
    p.add_argument("--sepolia-rpc-url", default="")

    # sim run-e2
    p = sub.add_parser("sim-e2", help="Run E2 experiment")
    p.add_argument("--config", default="configs/baseline.yaml")
    p.add_argument("--data", default="data/raw/raw_swaps.csv")
    p.add_argument("--out", default="outputs/e2")

    # sim run-suite
    p = sub.add_parser("sim-suite", help="Run E1-E7 suite")
    p.add_argument("--config", default="configs/baseline.yaml")
    p.add_argument("--out", default="outputs/suite")
    p.add_argument("--n-swaps", type=int, default=10000)
    p.add_argument("--seed", type=int, default=2026)

    # sim sweep
    p = sub.add_parser("sim-sweep", help="Run parameter sweep")
    p.add_argument("--config", default="configs/baseline.yaml")
    p.add_argument("--out", default="outputs/sweep")
    p.add_argument("--n-swaps", type=int, default=10000)
    p.add_argument("--seed", type=int, default=2026)

    args = parser.parse_args()

    if args.command == "keys-gen":
        cmd_keys_gen(args)
    elif args.command == "wallet-init":
        cmd_wallet_init(args)
    elif args.command == "wallet-show":
        cmd_wallet_show(args)
    elif args.command == "wallet-export-public":
        cmd_wallet_export_public(args)
    elif args.command == "wallet-request":
        cmd_wallet_request(args)
    elif args.command == "deployment-show":
        cmd_deployment_show(args)
    elif args.command == "role-audit":
        cmd_role_audit(args)
    elif args.command == "config-lint":
        cmd_config_lint(args)
    elif args.command == "intent-create":
        cmd_intent_create(args)
    elif args.command == "intent-verify":
        cmd_intent_verify(args)
    elif args.command == "replay-verify":
        cmd_replay_verify(args)
    elif args.command == "replay-fetch":
        cmd_replay_fetch(args)
    elif args.command == "status-check":
        cmd_status_check(args)
    elif args.command == "wallet-check":
        cmd_wallet_check(args)
    elif args.command == "sim-e2":
        cmd_sim_e2(args)
    elif args.command == "sim-suite":
        cmd_sim_suite(args)
    elif args.command == "sim-sweep":
        cmd_sim_sweep(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
