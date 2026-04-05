#!/usr/bin/env python3
"""Export a handoff packet for an outside DARWIN watcher operator."""

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


def render_env_template(deployment_filename: str, network: str, archive_url: str) -> str:
    lines = [
        "# DARWIN outside-watcher bootstrap",
        f"DARWIN_NETWORK={network}",
        f"DARWIN_DEPLOYMENT_FILE=./{deployment_filename}",
        f"DARWIN_WATCHER_ARCHIVE_URL={archive_url}",
        "DARWIN_WATCHER_PORT=9446",
        "DARWIN_WATCHER_POLL_SEC=60",
        "DARWIN_WATCHER_PRIME_LATEST=1",
        "DARWIN_WATCHER_STATE_ROOT=./state/external-watcher",
        "",
    ]
    return "\n".join(lines)


def render_handoff_markdown(summary: dict) -> str:
    deployment = summary["deployment"]
    status = summary["status"]
    files = summary["bundle_files"]
    lines = [
        "# DARWIN External Watcher Handoff",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Network: `{deployment['network']}`",
        f"- Chain ID: `{deployment['chain_id']}`",
        f"- Settlement hub: `{deployment['settlement_hub']}`",
        f"- Bond asset: `{deployment['bond_asset']}`",
        f"- Archive URL placeholder: `{summary['archive_url']}`",
        f"- Current watcher readiness: `{status['checks'].get('watcher_ready', {}).get('state', '')}` "
        f"{status['checks'].get('watcher_ready', {}).get('detail', '')}".rstrip(),
        f"- Current on-chain auth: `{status['checks'].get('onchain_auth', {}).get('state', '')}` "
        f"{status['checks'].get('onchain_auth', {}).get('detail', '')}".rstrip(),
        "",
        "## Included Files",
        "",
        f"- Deployment artifact: `{files['deployment']}`",
        f"- Status JSON: `{files['status_json']}`",
        f"- Status Markdown: `{files['status_markdown']}`" if files.get("status_markdown") else "- Status Markdown: none",
        f"- Operator quickstart: `{files['operator_quickstart']}`",
        f"- Audit readiness: `{files['audit_readiness']}`" if files.get("audit_readiness") else "- Audit readiness: none",
        f"- Threat model: `{files['threat_model']}`" if files.get("threat_model") else "- Threat model: none",
        f"- Env template: `{files['env_template']}`",
        "",
        "## Start Inside A Darwin Checkout",
        "",
        "```bash",
        "cp external-watcher.env.example .env.external-watcher",
        "# edit DARWIN_WATCHER_ARCHIVE_URL to your reachable archive",
        "source .env.external-watcher",
        "./ops/run_external_watcher.sh",
        "darwinctl status-check --allow-cold-watcher --deployment-file ./base-sepolia.json",
        "```",
        "",
        "## Role Snapshot",
        "",
        f"- Governance: `{deployment['roles']['governance']}`",
        f"- Epoch operator: `{deployment['roles']['epoch_operator']}`",
        f"- Batch operator: `{deployment['roles']['batch_operator']}`",
        f"- Safe mode authority: `{deployment['roles']['safe_mode_authority']}`",
        "",
        "## Current Blockers",
        "",
    ]
    blockers = status.get("blockers", [])
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none in the latest readiness report")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a DARWIN outside-watcher handoff bundle")
    parser.add_argument("--deployment-file", required=True)
    parser.add_argument("--status-json", required=True)
    parser.add_argument("--status-markdown", default="")
    parser.add_argument("--archive-url", default="http://archive-host:9447")
    parser.add_argument("--out-dir", default="ops/operator-bundles")
    args = parser.parse_args()

    deployment_path = Path(args.deployment_file).expanduser().resolve()
    status_json_path = Path(args.status_json).expanduser().resolve()
    status_markdown_path = Path(args.status_markdown).expanduser().resolve() if args.status_markdown else None
    repo_root = Path(__file__).resolve().parents[1]
    docs_dir = repo_root / "docs"

    deployment = read_json(deployment_path)
    status = read_json(status_json_path)
    generated_at = utc_now()

    bundle_dir = Path(args.out_dir).expanduser().resolve() / f"{deployment['network']}-watcher-{generated_at}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    deployment_copy = bundle_dir / deployment_path.name
    status_json_copy = bundle_dir / status_json_path.name
    shutil.copy2(deployment_path, deployment_copy)
    shutil.copy2(status_json_path, status_json_copy)

    markdown_copy = None
    if status_markdown_path and status_markdown_path.exists():
        markdown_copy = bundle_dir / status_markdown_path.name
        shutil.copy2(status_markdown_path, markdown_copy)

    operator_quickstart_path = docs_dir / "OPERATOR_QUICKSTART.md"
    operator_quickstart_copy = bundle_dir / operator_quickstart_path.name
    shutil.copy2(operator_quickstart_path, operator_quickstart_copy)

    audit_readiness_copy = None
    audit_readiness_path = docs_dir / "AUDIT_READINESS.md"
    if audit_readiness_path.exists():
        audit_readiness_copy = bundle_dir / audit_readiness_path.name
        shutil.copy2(audit_readiness_path, audit_readiness_copy)

    threat_model_copy = None
    threat_model_path = docs_dir / "THREAT_MODEL.md"
    if threat_model_path.exists():
        threat_model_copy = bundle_dir / threat_model_path.name
        shutil.copy2(threat_model_path, threat_model_copy)

    roles = dict(deployment.get("roles", {}))
    if "batch_operator" not in roles:
        roles["batch_operator"] = roles.get("epoch_operator", "")

    env_template = bundle_dir / "external-watcher.env.example"
    env_template.write_text(
        render_env_template(
            deployment_filename=deployment_copy.name,
            network=str(deployment["network"]),
            archive_url=args.archive_url,
        )
    )

    summary = {
        "generated_at": generated_at,
        "deployment": {
            "network": deployment["network"],
            "chain_id": deployment["chain_id"],
            "settlement_hub": deployment["contracts"]["settlement_hub"],
            "bond_asset": deployment["contracts"].get("bond_asset", ""),
            "contracts": deployment["contracts"],
            "roles": roles,
        },
        "status": status,
        "archive_url": args.archive_url,
        "bundle_files": {
            "deployment": deployment_copy.name,
            "status_json": status_json_copy.name,
            "status_markdown": markdown_copy.name if markdown_copy else "",
            "operator_quickstart": operator_quickstart_copy.name,
            "audit_readiness": audit_readiness_copy.name if audit_readiness_copy else "",
            "threat_model": threat_model_copy.name if threat_model_copy else "",
            "env_template": env_template.name,
        },
    }

    summary_json = bundle_dir / "external-watcher-summary.json"
    summary_md = bundle_dir / "EXTERNAL_WATCHER_HANDOFF.md"
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summary_md.write_text(render_handoff_markdown(summary))

    print(f"[external-watcher-bundle] Exported: {bundle_dir}")
    print(f"  Deployment:    {deployment_copy.name}")
    print(f"  Status JSON:   {status_json_copy.name}")
    if markdown_copy:
        print(f"  Status MD:     {markdown_copy.name}")
    print(f"  Quickstart:    {operator_quickstart_copy.name}")
    if audit_readiness_copy:
        print(f"  Audit doc:     {audit_readiness_copy.name}")
    if threat_model_copy:
        print(f"  Threat model:  {threat_model_copy.name}")
    print(f"  Env template:  {env_template.name}")
    print(f"  Summary JSON:  {summary_json.name}")
    print(f"  Handoff MD:    {summary_md.name}")


if __name__ == "__main__":
    main()
