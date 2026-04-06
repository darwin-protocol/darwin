#!/usr/bin/env python3
"""Export a reviewer-facing bundle from a deployment artifact and status report."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def render_markdown(summary: dict) -> str:
    deployment = summary["deployment"]
    status = summary["status"]
    bundle_files = summary["bundle_files"]
    lines = [
        "# DARWIN Audit Bundle",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Network: `{deployment['network']}`",
        f"- Chain ID: `{deployment['chain_id']}`",
        f"- Ready: `{status['ready']}`",
        f"- Settlement hub: `{deployment['settlement_hub']}`",
        f"- Bond asset: `{deployment['bond_asset']}`",
        f"- Governance: `{deployment['roles']['governance']}`",
        f"- Epoch operator: `{deployment['roles']['epoch_operator']}`",
        f"- Batch operator: `{deployment['roles']['batch_operator']}`",
        f"- Safe mode authority: `{deployment['roles']['safe_mode_authority']}`",
    ]
    drw = deployment.get("drw") or {}
    if drw:
        contracts = drw.get("contracts", {})
        lines.extend([
            f"- DRW token: `{contracts.get('drw_token', '')}`",
            f"- DRW staking: `{contracts.get('drw_staking', '')}`",
            f"- DRW total supply: `{drw.get('total_supply', '')}`",
            f"- DRW duration: `{drw.get('staking_duration', '')}`",
        ])

    lines.extend([
        "",
        "## Readiness",
        "",
        f"- Watcher ready: `{status['checks'].get('watcher_ready', {}).get('state', '')}` "
        f"{status['checks'].get('watcher_ready', {}).get('detail', '')}".rstrip(),
        f"- On-chain code: `{status['checks'].get('onchain', {}).get('state', '')}` "
        f"{status['checks'].get('onchain', {}).get('detail', '')}".rstrip(),
        f"- On-chain auth: `{status['checks'].get('onchain_auth', {}).get('state', '')}` "
        f"{status['checks'].get('onchain_auth', {}).get('detail', '')}".rstrip(),
    ])
    if status["checks"].get("onchain_drw"):
        lines.append(
            f"- On-chain DRW: `{status['checks'].get('onchain_drw', {}).get('state', '')}` "
            f"{status['checks'].get('onchain_drw', {}).get('detail', '')}".rstrip()
        )

    lines.extend(["", "## Contracts", ""])

    for name, address in deployment["contracts"].items():
        lines.append(f"- `{name}`: `{address}`")

    lines.extend(["", "## Auth Components", ""])
    auth_components = status.get("onchain_auth", {}).get("components", {})
    if auth_components:
        for name, component in auth_components.items():
            lines.append(f"- `{name}`: `{'OK' if component.get('ok') else 'FAIL'}` {component.get('summary', '')}".rstrip())
    else:
        lines.append("- none")

    onchain_drw = status.get("onchain_drw", {})
    if onchain_drw:
        lines.extend(["", "## DRW State", ""])
        lines.append(
            f"- Tracked holders: `{len(onchain_drw.get('holders', {}))}` "
            f"tracked_supply=`{onchain_drw.get('tracked_total', 0)}`/"
            f"`{onchain_drw.get('expected_total_supply', 0)}`"
        )
        for holder, detail in sorted(onchain_drw.get("holders", {}).items()):
            lines.append(
                f"- `{holder}`: expected=`{detail.get('expected', 0)}` "
                f"observed=`{detail.get('observed', 0)}`"
            )

    lines.extend(["", "## Blockers", ""])
    blockers = status.get("blockers", [])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")

    lines.extend(["", "## Included Docs", ""])
    if bundle_files.get("audit_readiness"):
        lines.append(f"- Audit readiness: `{bundle_files['audit_readiness']}`")
    if bundle_files.get("threat_model"):
        lines.append(f"- Threat model: `{bundle_files['threat_model']}`")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a DARWIN audit/readiness bundle")
    parser.add_argument("--deployment-file", required=True)
    parser.add_argument("--status-json", required=True)
    parser.add_argument("--status-markdown", default="")
    parser.add_argument("--out-dir", default="ops/audit-bundles")
    args = parser.parse_args()

    deployment_path = Path(args.deployment_file).expanduser().resolve()
    status_json_path = Path(args.status_json).expanduser().resolve()
    status_markdown_path = Path(args.status_markdown).expanduser().resolve() if args.status_markdown else None
    docs_dir = (Path(__file__).resolve().parents[1] / "docs").resolve()
    audit_readiness_path = docs_dir / "AUDIT_READINESS.md"
    threat_model_path = docs_dir / "THREAT_MODEL.md"

    deployment = read_json(deployment_path)
    status = read_json(status_json_path)
    generated_at = utc_now()
    bundle_dir = Path(args.out_dir).expanduser().resolve() / f"{deployment['network']}-{generated_at}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    deployment_copy = bundle_dir / deployment_path.name
    status_json_copy = bundle_dir / status_json_path.name
    shutil.copy2(deployment_path, deployment_copy)
    shutil.copy2(status_json_path, status_json_copy)

    markdown_copy = None
    if status_markdown_path and status_markdown_path.exists():
        markdown_copy = bundle_dir / status_markdown_path.name
        shutil.copy2(status_markdown_path, markdown_copy)

    audit_readiness_copy = None
    if audit_readiness_path.exists():
        audit_readiness_copy = bundle_dir / audit_readiness_path.name
        shutil.copy2(audit_readiness_path, audit_readiness_copy)

    threat_model_copy = None
    if threat_model_path.exists():
        threat_model_copy = bundle_dir / threat_model_path.name
        shutil.copy2(threat_model_path, threat_model_copy)

    roles = dict(deployment.get("roles", {}))
    if "batch_operator" not in roles:
        roles["batch_operator"] = roles.get("epoch_operator", "")

    summary = {
        "generated_at": generated_at,
        "deployment": {
            "network": deployment["network"],
            "chain_id": deployment["chain_id"],
            "settlement_hub": deployment["contracts"]["settlement_hub"],
            "bond_asset": deployment["contracts"].get("bond_asset", ""),
            "contracts": deployment["contracts"],
            "roles": roles,
            "drw": deployment.get("drw"),
        },
        "status": status,
        "bundle_files": {
            "deployment": deployment_copy.name,
            "status_json": status_json_copy.name,
            "status_markdown": markdown_copy.name if markdown_copy else "",
            "audit_readiness": audit_readiness_copy.name if audit_readiness_copy else "",
            "threat_model": threat_model_copy.name if threat_model_copy else "",
        },
    }

    summary_json = bundle_dir / "audit-summary.json"
    summary_md = bundle_dir / "audit-summary.md"
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summary_md.write_text(render_markdown(summary))

    print(f"[audit-bundle] Exported: {bundle_dir}")
    print(f"  Deployment:    {deployment_copy.name}")
    print(f"  Status JSON:   {status_json_copy.name}")
    if markdown_copy:
        print(f"  Status MD:     {markdown_copy.name}")
    if audit_readiness_copy:
        print(f"  Audit doc:     {audit_readiness_copy.name}")
    if threat_model_copy:
        print(f"  Threat model:  {threat_model_copy.name}")
    print(f"  Summary JSON:  {summary_json.name}")
    print(f"  Summary MD:    {summary_md.name}")


if __name__ == "__main__":
    main()
