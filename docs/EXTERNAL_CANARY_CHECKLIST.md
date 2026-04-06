# DARWIN External Canary Checklist

## Outside Watcher Operator

1. Receive the operator packet tarball produced by `ops/prepare_external_packets.py`.
2. Extract it inside a DARWIN checkout.
3. Copy `external-watcher.env.example` to `.env.external-watcher` and set a reachable archive URL.
4. Run `./ops/run_external_watcher.sh`.
5. Wait for a successful replay and return:
   - `watcher-status.json`
   - `watcher-status.md`

The maintainer should then verify the returned files with:

```bash
python ops/intake_external_watcher_report.py \
  --bundle-dir ops/operator-bundles/<bundle-dir> \
  --report-json watcher-status.json \
  --report-markdown watcher-status.md
```

## External Reviewer

1. Receive the audit packet tarball produced by `ops/prepare_external_packets.py`.
2. Review the pinned deployment artifact, readiness report, audit-readiness doc, and threat model together.
3. Focus on settlement authorization, lifecycle correctness, and watcher/challenge assumptions.
4. Return `review-findings.md` with severity, affected paths, and recommended fixes.
5. Optionally return `review-findings.json` using `findings: [{severity, title, affected_paths, status, notes}]`.

The maintainer should then verify and log the review with:

```bash
python ops/intake_external_review.py \
  --bundle-dir ops/audit-bundles/<bundle-dir> \
  --review-markdown review-findings.md \
  --review-json review-findings.json
```

## Acceptance Criteria

- watcher report is accepted by `ops/intake_external_watcher_report.py`
- watcher report shows `ready: true`
- latest mirrored epoch passes with zero mismatches
- reviewer findings are documented and triaged before any stronger live-ready claim
