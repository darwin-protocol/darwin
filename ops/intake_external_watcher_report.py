#!/usr/bin/env python3
"""Ingest and verify an outside DARWIN watcher report against a handoff bundle."""

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


def latest_epoch_id(report: dict) -> str:
    epochs = report.get("epochs", {})
    if not epochs:
        return ""

    def epoch_key(value: str) -> tuple[int, int | str]:
        try:
            return (0, int(value))
        except ValueError:
            return (1, value)

    return sorted(epochs.keys(), key=epoch_key)[-1]


def render_markdown(summary: dict) -> str:
    lines = [
        "# DARWIN External Watcher Intake",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Accepted: `{summary['accepted']}`",
        f"- Bundle network: `{summary['bundle']['network']}`",
        f"- Bundle chain ID: `{summary['bundle']['chain_id']}`",
        f"- Archive URL: `{summary['bundle']['archive_url']}`",
        f"- Watcher ready: `{summary['watcher']['ready']}`",
        f"- Epochs replayed: `{summary['watcher']['epochs_replayed']}`",
        f"- Last mirrored epoch: `{summary['watcher']['last_mirrored_epoch']}`",
        f"- Latest epoch passed: `{summary['watcher']['latest_epoch_passed']}`",
        "",
        "## Checks",
        "",
    ]
    for key, check in summary["checks"].items():
        lines.append(f"- `{key}`: `{'OK' if check['ok'] else 'FAIL'}` {check['detail']}".rstrip())

    lines.extend(["", "## Blockers", ""])
    if summary["blockers"]:
        lines.extend(f"- {blocker}" for blocker in summary["blockers"])
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify an outside DARWIN watcher report")
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--report-markdown", default="")
    parser.add_argument("--reference-deployment-file", default="ops/deployments/base-sepolia.json")
    parser.add_argument("--out-dir", default="ops/external-intake")
    args = parser.parse_args()

    bundle_dir = Path(args.bundle_dir).expanduser().resolve()
    report_json_path = Path(args.report_json).expanduser().resolve()
    report_markdown_path = Path(args.report_markdown).expanduser().resolve() if args.report_markdown else None
    reference_deployment_path = Path(args.reference_deployment_file).expanduser().resolve()

    bundle_summary_path = bundle_dir / "external-watcher-summary.json"
    if not bundle_summary_path.exists():
        raise SystemExit(f"missing bundle summary: {bundle_summary_path}")

    bundle_summary = read_json(bundle_summary_path)
    deployment_filename = bundle_summary["bundle_files"]["deployment"]
    deployment_path = bundle_dir / deployment_filename
    if not deployment_path.exists():
        raise SystemExit(f"missing deployment artifact in bundle: {deployment_path}")

    deployment = read_json(deployment_path)
    reference_deployment = read_json(reference_deployment_path) if reference_deployment_path.exists() else {}
    watcher_report = read_json(report_json_path)

    checks: dict[str, dict] = {}
    blockers: list[str] = []

    required_bundle_files = [
        deployment_filename,
        bundle_summary["bundle_files"]["operator_quickstart"],
        bundle_summary["bundle_files"]["env_template"],
    ]
    if bundle_summary["bundle_files"].get("audit_readiness"):
        required_bundle_files.append(bundle_summary["bundle_files"]["audit_readiness"])
    if bundle_summary["bundle_files"].get("threat_model"):
        required_bundle_files.append(bundle_summary["bundle_files"]["threat_model"])

    missing_bundle_files = [name for name in required_bundle_files if not (bundle_dir / name).exists()]
    checks["bundle_files"] = {
        "ok": not missing_bundle_files,
        "detail": "all required files present" if not missing_bundle_files else f"missing={','.join(missing_bundle_files)}",
    }
    if missing_bundle_files:
        blockers.append("bundle_missing_required_files")

    deployment_matches = True
    deployment_detail = "no reference deployment available"
    if reference_deployment:
        same_network = deployment.get("network") == reference_deployment.get("network")
        same_chain = int(deployment.get("chain_id", 0)) == int(reference_deployment.get("chain_id", 0))
        same_hub = deployment.get("contracts", {}).get("settlement_hub", "").lower() == reference_deployment.get("contracts", {}).get("settlement_hub", "").lower()
        same_bond = deployment.get("contracts", {}).get("bond_asset", "").lower() == reference_deployment.get("contracts", {}).get("bond_asset", "").lower()
        deployment_matches = same_network and same_chain and same_hub and same_bond
        deployment_detail = f"network={same_network} chain_id={same_chain} settlement_hub={same_hub} bond_asset={same_bond}"
    checks["deployment_match"] = {"ok": deployment_matches, "detail": deployment_detail}
    if not deployment_matches:
        blockers.append("bundle_deployment_mismatch")

    health = watcher_report.get("health", {})
    ready = bool(health.get("ready"))
    epochs_replayed = int(health.get("epochs_replayed", 0))
    last_mirrored = str(health.get("last_mirrored_epoch", ""))
    checks["watcher_ready"] = {
        "ok": ready and epochs_replayed > 0,
        "detail": f"ready={ready} epochs_replayed={epochs_replayed} last_mirrored_epoch={last_mirrored}",
    }
    if not checks["watcher_ready"]["ok"]:
        blockers.append("watcher_not_ready")

    latest_epoch = latest_epoch_id(watcher_report)
    latest_epoch_row = watcher_report.get("epochs", {}).get(latest_epoch, {}) if latest_epoch else {}
    latest_epoch_passed = bool(latest_epoch_row.get("passed")) and int(latest_epoch_row.get("mismatches", 0)) == 0
    coerced_non_numeric_epoch = latest_epoch == "0" and last_mirrored not in {"", "0"}
    checks["latest_epoch"] = {
        "ok": bool(latest_epoch) and latest_epoch_passed,
        "detail": (
            f"epoch={latest_epoch or 'none'} passed={latest_epoch_row.get('passed', False)} "
            f"mismatches={latest_epoch_row.get('mismatches', 0)}"
        ),
    }
    if not checks["latest_epoch"]["ok"]:
        blockers.append("latest_epoch_not_clean")

    if last_mirrored and latest_epoch:
        mirrored_ok = last_mirrored == latest_epoch or coerced_non_numeric_epoch
        checks["mirrored_epoch_alignment"] = {
            "ok": mirrored_ok,
            "detail": (
                f"last_mirrored_epoch={last_mirrored} latest_epoch={latest_epoch} "
                f"coerced_non_numeric_epoch={coerced_non_numeric_epoch}"
            ),
        }
        if not mirrored_ok:
            blockers.append("mirrored_epoch_mismatch")
    else:
        checks["mirrored_epoch_alignment"] = {
            "ok": False,
            "detail": "last mirrored epoch or latest epoch missing",
        }
        blockers.append("mirrored_epoch_mismatch")

    generated_at = utc_now()
    intake_dir = Path(args.out_dir).expanduser().resolve() / f"{deployment['network']}-watcher-intake-{generated_at}"
    intake_dir.mkdir(parents=True, exist_ok=True)

    report_json_copy = intake_dir / report_json_path.name
    shutil.copy2(report_json_path, report_json_copy)
    report_markdown_copy = None
    if report_markdown_path and report_markdown_path.exists():
        report_markdown_copy = intake_dir / report_markdown_path.name
        shutil.copy2(report_markdown_path, report_markdown_copy)

    shutil.copy2(bundle_summary_path, intake_dir / bundle_summary_path.name)
    shutil.copy2(deployment_path, intake_dir / deployment_path.name)

    accepted = not blockers
    summary = {
        "generated_at": generated_at,
        "accepted": accepted,
        "bundle": {
            "network": deployment["network"],
            "chain_id": deployment["chain_id"],
            "settlement_hub": deployment.get("contracts", {}).get("settlement_hub", ""),
            "bond_asset": deployment.get("contracts", {}).get("bond_asset", ""),
            "archive_url": bundle_summary.get("archive_url", ""),
        },
        "watcher": {
            "ready": ready,
            "epochs_replayed": epochs_replayed,
            "last_mirrored_epoch": last_mirrored,
            "latest_epoch": latest_epoch,
            "latest_epoch_passed": latest_epoch_passed,
        },
        "checks": checks,
        "blockers": blockers,
        "files": {
            "bundle_summary": bundle_summary_path.name,
            "deployment": deployment_path.name,
            "report_json": report_json_copy.name,
            "report_markdown": report_markdown_copy.name if report_markdown_copy else "",
        },
    }

    summary_json = intake_dir / "external-watcher-intake.json"
    summary_md = intake_dir / "external-watcher-intake.md"
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summary_md.write_text(render_markdown(summary))

    print(f"[external-watcher-intake] Exported: {intake_dir}")
    print(f"  Accepted:      {'yes' if accepted else 'no'}")
    print(f"  Report JSON:   {report_json_copy.name}")
    if report_markdown_copy:
        print(f"  Report MD:     {report_markdown_copy.name}")
    print(f"  Summary JSON:  {summary_json.name}")
    print(f"  Summary MD:    {summary_md.name}")


if __name__ == "__main__":
    main()
