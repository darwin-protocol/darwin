#!/usr/bin/env python3
"""Ingest and summarize an external DARWIN review response."""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ALLOWED_SEVERITIES = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNKNOWN")


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def normalize_findings(payload: object) -> list[dict]:
    if isinstance(payload, dict):
        raw_findings = payload.get("findings", [])
    elif isinstance(payload, list):
        raw_findings = payload
    else:
        raise ValueError("review JSON must be an object with `findings` or a list of findings")

    if not isinstance(raw_findings, list):
        raise ValueError("review findings payload must be a list")

    findings: list[dict] = []
    for idx, finding in enumerate(raw_findings, start=1):
        if not isinstance(finding, dict):
            raise ValueError(f"finding {idx} is not an object")
        title = str(finding.get("title", "")).strip() or f"Finding {idx}"
        severity = str(finding.get("severity", "UNKNOWN")).upper()
        if severity not in ALLOWED_SEVERITIES:
            severity = "UNKNOWN"
        status = str(finding.get("status", "open")).strip() or "open"
        affected_paths = finding.get("affected_paths", [])
        if isinstance(affected_paths, str):
            affected_paths = [affected_paths]
        if not isinstance(affected_paths, list):
            raise ValueError(f"finding {idx} has invalid affected_paths")
        findings.append({
            "title": title,
            "severity": severity,
            "status": status,
            "affected_paths": [str(path) for path in affected_paths if str(path).strip()],
            "notes": str(finding.get("notes", "")).strip(),
        })
    return findings


def severity_rank(severity: str) -> int:
    order = {
        "CRITICAL": 0,
        "HIGH": 1,
        "MEDIUM": 2,
        "LOW": 3,
        "INFO": 4,
        "UNKNOWN": 5,
    }
    return order.get(severity, 5)


def render_markdown(summary: dict) -> str:
    review = summary["review"]
    lines = [
        "# DARWIN External Review Intake",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Accepted: `{summary['accepted']}`",
        f"- Requires action: `{review['requires_action']}`",
        f"- Highest severity: `{review['highest_severity']}`",
        f"- Findings count: `{review['findings_count']}`",
        f"- Bundle network: `{summary['bundle']['network']}`",
        f"- Bundle chain ID: `{summary['bundle']['chain_id']}`",
        f"- Settlement hub: `{summary['bundle']['settlement_hub']}`",
        f"- Bond asset: `{summary['bundle']['bond_asset']}`",
        "",
        "## Checks",
        "",
    ]
    for key, check in summary["checks"].items():
        lines.append(f"- `{key}`: `{'OK' if check['ok'] else 'FAIL'}` {check['detail']}".rstrip())

    lines.extend(["", "## Severity Counts", ""])
    for severity in ALLOWED_SEVERITIES:
        count = review["severity_counts"].get(severity, 0)
        if count:
            lines.append(f"- `{severity}`: `{count}`")
    if not any(review["severity_counts"].values()):
        lines.append("- none")

    lines.extend(["", "## Findings", ""])
    if review["findings"]:
        for finding in review["findings"]:
            paths = ", ".join(finding["affected_paths"]) if finding["affected_paths"] else "none"
            lines.append(
                f"- `{finding['severity']}` `{finding['title']}` status=`{finding['status']}` paths=`{paths}`"
            )
    else:
        lines.append("- none")

    lines.extend(["", "## Blockers", ""])
    if summary["blockers"]:
        lines.extend(f"- {blocker}" for blocker in summary["blockers"])
    else:
        lines.append("- none")

    return "\n".join(lines) + "\n"


def render_triage_markdown(summary: dict) -> str:
    lines = [
        "# DARWIN External Review Triage",
        "",
        f"- Generated at: `{summary['generated_at']}`",
        f"- Bundle network: `{summary['bundle']['network']}`",
        f"- Highest severity: `{summary['review']['highest_severity']}`",
        "",
        "## Triage Tasks",
        "",
    ]
    findings = summary["review"]["findings"]
    if findings:
        for finding in findings:
            paths = ", ".join(finding["affected_paths"]) if finding["affected_paths"] else "none"
            lines.extend([
                f"- [ ] {finding['severity']}: {finding['title']}",
                f"  Status: {finding['status']}",
                f"  Paths: {paths}",
            ])
            if finding["notes"]:
                lines.append(f"  Notes: {finding['notes']}")
    else:
        lines.append("- [ ] Review received and logged")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify and log an external DARWIN review response")
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--review-markdown", required=True)
    parser.add_argument("--review-json", default="")
    parser.add_argument("--out-dir", default="ops/external-review-intake")
    args = parser.parse_args()

    bundle_dir = Path(args.bundle_dir).expanduser().resolve()
    review_markdown_path = Path(args.review_markdown).expanduser().resolve()
    review_json_path = Path(args.review_json).expanduser().resolve() if args.review_json else None

    bundle_summary_path = bundle_dir / "audit-summary.json"
    if not bundle_summary_path.exists():
        raise SystemExit(f"missing audit bundle summary: {bundle_summary_path}")

    bundle_summary = read_json(bundle_summary_path)
    deployment_filename = bundle_summary["bundle_files"]["deployment"]
    deployment_path = bundle_dir / deployment_filename
    if not deployment_path.exists():
        raise SystemExit(f"missing deployment artifact in bundle: {deployment_path}")

    deployment = read_json(deployment_path)
    checks: dict[str, dict] = {}
    blockers: list[str] = []

    required_bundle_files = [
        deployment_filename,
        bundle_summary["bundle_files"]["status_json"],
    ]
    if bundle_summary["bundle_files"].get("status_markdown"):
        required_bundle_files.append(bundle_summary["bundle_files"]["status_markdown"])
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

    review_text = review_markdown_path.read_text().strip() if review_markdown_path.exists() else ""
    checks["review_markdown"] = {
        "ok": bool(review_text),
        "detail": "review markdown received" if review_text else "review markdown missing or empty",
    }
    if not review_text:
        blockers.append("review_markdown_missing")

    findings: list[dict] = []
    if review_json_path:
        try:
            findings = normalize_findings(read_json(review_json_path))
            checks["review_json"] = {
                "ok": True,
                "detail": f"structured findings={len(findings)}",
            }
        except Exception as exc:  # noqa: BLE001
            checks["review_json"] = {
                "ok": False,
                "detail": str(exc),
            }
            blockers.append("review_json_invalid")
    else:
        checks["review_json"] = {
            "ok": True,
            "detail": "not provided",
        }

    severity_counts = {severity: 0 for severity in ALLOWED_SEVERITIES}
    for finding in findings:
        severity_counts[finding["severity"]] += 1

    highest_severity = "NONE"
    if findings:
        highest_severity = sorted((finding["severity"] for finding in findings), key=severity_rank)[0]
    requires_action = any(severity_counts[severity] > 0 for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW"))

    generated_at = utc_now()
    intake_dir = Path(args.out_dir).expanduser().resolve() / f"{deployment['network']}-review-intake-{generated_at}"
    intake_dir.mkdir(parents=True, exist_ok=True)

    review_markdown_copy = intake_dir / review_markdown_path.name
    shutil.copy2(review_markdown_path, review_markdown_copy)
    review_json_copy = None
    if review_json_path and review_json_path.exists():
        review_json_copy = intake_dir / review_json_path.name
        shutil.copy2(review_json_path, review_json_copy)

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
        },
        "review": {
            "requires_action": requires_action,
            "highest_severity": highest_severity,
            "findings_count": len(findings),
            "severity_counts": severity_counts,
            "findings": findings,
        },
        "checks": checks,
        "blockers": blockers,
        "files": {
            "bundle_summary": bundle_summary_path.name,
            "deployment": deployment_path.name,
            "review_markdown": review_markdown_copy.name,
            "review_json": review_json_copy.name if review_json_copy else "",
        },
    }

    summary_json = intake_dir / "external-review-intake.json"
    summary_md = intake_dir / "external-review-intake.md"
    triage_md = intake_dir / "external-review-triage.md"
    summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    summary_md.write_text(render_markdown(summary))
    triage_md.write_text(render_triage_markdown(summary))

    print(f"[external-review-intake] Exported: {intake_dir}")
    print(f"  Accepted:      {'yes' if accepted else 'no'}")
    print(f"  Requires action: {'yes' if requires_action else 'no'}")
    print(f"  Highest severity: {highest_severity}")
    print(f"  Review MD:     {review_markdown_copy.name}")
    if review_json_copy:
        print(f"  Review JSON:   {review_json_copy.name}")
    print(f"  Summary JSON:  {summary_json.name}")
    print(f"  Summary MD:    {summary_md.name}")
    print(f"  Triage MD:     {triage_md.name}")


if __name__ == "__main__":
    main()
