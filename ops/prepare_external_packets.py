#!/usr/bin/env python3
"""Create ready-to-send DARWIN operator and reviewer packet bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def run_export(script: Path, args: list[str]) -> Path:
    result = subprocess.run(
        [sys.executable, str(script), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    exported = ""
    for line in result.stdout.splitlines():
        if "Exported:" in line:
            exported = line.split("Exported:", 1)[1].strip()
            break
    if not exported:
        raise RuntimeError(f"could not determine exported bundle from {script.name}")
    return Path(exported)


def make_tarball(source_dir: Path, target: Path) -> Path:
    with tarfile.open(target, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)
    return target


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def render_operator_request(summary: dict) -> str:
    return "\n".join([
        "# DARWIN Outside Watcher Request",
        "",
        "Please run the attached DARWIN watcher packet against the included Base Sepolia deployment.",
        "",
        "## What To Do",
        "",
        f"1. Extract `{summary['artifacts']['operator_bundle_tar']}` inside a DARWIN checkout.",
        "2. Follow `EXTERNAL_CANARY_CHECKLIST.md`.",
        "3. Run the watcher until it has replayed at least one epoch successfully.",
        "4. Send back:",
        "   - `watcher-status.json`",
        "   - `watcher-status.md`",
        "",
        "## Integrity",
        "",
        f"- SHA-256: `{summary['checksums']['operator_bundle_tar']}`",
        "",
        "## Why This Matters",
        "",
        "We already have local canary evidence. What is missing is genuinely external replay evidence from outside this workstation.",
        "",
    ]) + "\n"


def render_reviewer_request(summary: dict) -> str:
    return "\n".join([
        "# DARWIN External Review Request",
        "",
        "Please review the attached DARWIN Base Sepolia audit packet.",
        "",
        "## Focus Areas",
        "",
        "- settlement authorization and replay invariants",
        "- epoch / score-root lifecycle correctness",
        "- watcher challengeability and archive trust assumptions",
        "- role concentration in the current alpha canary",
        "",
        "## Packet",
        "",
        f"- Archive: `{summary['artifacts']['audit_bundle_tar']}`",
        f"- SHA-256: `{summary['checksums']['audit_bundle_tar']}`",
        "",
        "## Requested Response",
        "",
        "- written findings with severity",
        "- affected paths / files",
        "- recommended fixes or follow-up review areas",
        "",
    ]) + "\n"


def render_markdown(summary: dict) -> str:
    lines = [
        "# DARWIN External Packet Prep",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Network: `{summary['deployment']['network']}`",
        f"- Chain ID: `{summary['deployment']['chain_id']}`",
        f"- Ready: `{summary['status']['ready']}`",
        f"- Operator bundle: `{summary['artifacts']['operator_bundle_dir']}`",
        f"- Operator tarball: `{summary['artifacts']['operator_bundle_tar']}`",
        f"- Audit bundle: `{summary['artifacts']['audit_bundle_dir']}`",
        f"- Audit tarball: `{summary['artifacts']['audit_bundle_tar']}`",
        "",
        "## Files To Send",
        "",
        f"- Outside watcher operator: `{summary['artifacts']['operator_bundle_tar']}`",
        f"- External reviewer: `{summary['artifacts']['audit_bundle_tar']}`",
        "",
        "## Acceptance Notes",
        "",
        "- outside watcher should return `watcher-status.json` and `watcher-status.md`",
        "- intake those files with `ops/intake_external_watcher_report.py`",
        "- external reviewer should respond against the bundled deployment, readiness report, audit-readiness doc, and threat model",
        "",
        "## Integrity",
        "",
        f"- Operator tar SHA-256: `{summary['checksums']['operator_bundle_tar']}`",
        f"- Audit tar SHA-256: `{summary['checksums']['audit_bundle_tar']}`",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare sendable DARWIN operator and reviewer packets")
    parser.add_argument("--deployment-file", required=True)
    parser.add_argument("--status-json", required=True)
    parser.add_argument("--status-markdown", default="")
    parser.add_argument("--archive-url", default="http://archive-host:9447")
    parser.add_argument("--out-dir", default="ops/handoffs")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    deployment_path = Path(args.deployment_file).expanduser().resolve()
    status_json_path = Path(args.status_json).expanduser().resolve()
    status_markdown_path = Path(args.status_markdown).expanduser().resolve() if args.status_markdown else None

    deployment = read_json(deployment_path)
    status = read_json(status_json_path)
    generated_at = utc_now()

    handoff_dir = Path(args.out_dir).expanduser().resolve() / f"{deployment['network']}-{generated_at}"
    handoff_dir.mkdir(parents=True, exist_ok=True)

    audit_base = handoff_dir / "audit-bundles"
    operator_base = handoff_dir / "operator-bundles"
    audit_base.mkdir(parents=True, exist_ok=True)
    operator_base.mkdir(parents=True, exist_ok=True)

    audit_bundle = run_export(
        root / "ops" / "export_audit_bundle.py",
        [
            "--deployment-file", str(deployment_path),
            "--status-json", str(status_json_path),
            "--status-markdown", str(status_markdown_path) if status_markdown_path else "",
            "--out-dir", str(audit_base),
        ],
    )
    operator_bundle = run_export(
        root / "ops" / "export_external_watcher_bundle.py",
        [
            "--deployment-file", str(deployment_path),
            "--status-json", str(status_json_path),
            "--status-markdown", str(status_markdown_path) if status_markdown_path else "",
            "--archive-url", args.archive_url,
            "--out-dir", str(operator_base),
        ],
    )

    audit_tar = make_tarball(audit_bundle, handoff_dir / f"{audit_bundle.name}.tar.gz")
    operator_tar = make_tarball(operator_bundle, handoff_dir / f"{operator_bundle.name}.tar.gz")
    audit_sha = sha256_file(audit_tar)
    operator_sha = sha256_file(operator_tar)

    checklist_path = root / "docs" / "EXTERNAL_CANARY_CHECKLIST.md"
    checklist_copy = None
    if checklist_path.exists():
        checklist_copy = handoff_dir / checklist_path.name
        shutil.copy2(checklist_path, checklist_copy)

    checksums_txt = handoff_dir / "CHECKSUMS.txt"
    checksums_txt.write_text(
        "\n".join([
            f"{operator_sha}  {operator_tar.name}",
            f"{audit_sha}  {audit_tar.name}",
            "",
        ])
    )

    summary = {
        "generated_at": generated_at,
        "deployment": {
            "network": deployment["network"],
            "chain_id": deployment["chain_id"],
        },
        "status": {
            "ready": bool(status.get("ready")),
        },
        "checksums": {
            "audit_bundle_tar": audit_sha,
            "operator_bundle_tar": operator_sha,
        },
        "artifacts": {
            "audit_bundle_dir": audit_bundle.name,
            "audit_bundle_tar": audit_tar.name,
            "operator_bundle_dir": operator_bundle.name,
            "operator_bundle_tar": operator_tar.name,
            "checklist": checklist_copy.name if checklist_copy else "",
            "checksums": checksums_txt.name,
            "operator_request": "WATCHER_OPERATOR_REQUEST.md",
            "reviewer_request": "EXTERNAL_REVIEW_REQUEST.md",
        },
    }

    summary_json = handoff_dir / "handoff-summary.json"
    summary_md = handoff_dir / "handoff-summary.md"
    operator_request = handoff_dir / "WATCHER_OPERATOR_REQUEST.md"
    reviewer_request = handoff_dir / "EXTERNAL_REVIEW_REQUEST.md"
    operator_request.write_text(render_operator_request(summary))
    reviewer_request.write_text(render_reviewer_request(summary))
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summary_md.write_text(render_markdown(summary))

    print(f"[handoff-packets] Exported: {handoff_dir}")
    print(f"  Operator tar:  {operator_tar.name}")
    print(f"  Audit tar:     {audit_tar.name}")
    if checklist_copy:
        print(f"  Checklist:     {checklist_copy.name}")
    print(f"  Checksums:     {checksums_txt.name}")
    print(f"  Operator req:  {operator_request.name}")
    print(f"  Reviewer req:  {reviewer_request.name}")
    print(f"  Summary JSON:  {summary_json.name}")
    print(f"  Summary MD:    {summary_md.name}")


if __name__ == "__main__":
    main()
