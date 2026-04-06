# Contributing to DARWIN

## Where to Start

1. Run `./ops/bootstrap_dev.sh`
2. Read `docs/OPERATOR_QUICKSTART.md`
3. Run the Python self-check: `source .venv/bin/activate && cd sim && python -m pytest tests/test_end_to_end.py -v`
4. Run the contract tests: `source .venv/bin/activate && cd contracts && forge test --summary`
5. Run the devnet: `source .venv/bin/activate && python overlay/devnet.py`
6. Run the deployment smoke test: `./ops/smoke_deploy_local.sh` and confirm `ops/deployments/local-anvil.json` is emitted
7. Inspect the emitted deployment artifact: `source .venv/bin/activate && darwinctl deployment-show --deployment-file ops/deployments/local-anvil.json`
8. Inspect the current Base Sepolia artifact first: `source .venv/bin/activate && darwinctl deployment-show --deployment-file ops/deployments/base-sepolia.json`
9. Boot the deployment-pinned canary stack locally when working on operator paths: `./ops/run_base_sepolia_canary.sh`
10. For watcher-specific operator work, use the standalone bootstrap path: `DARWIN_WATCHER_ARCHIVE_URL=http://archive-host:9447 ./ops/run_external_watcher.sh`
11. To exercise the canary data path after boot, publish a local epoch through the running stack: `./ops/publish_canary_epoch.sh canary-2 "$PWD/sim/outputs/test_e2"`
12. If you need to reproduce the testnet deploy, start from `ops/base_sepolia.env.example`, choose either `DARWIN_DEPLOY_BOND_ASSET_MOCK=1` or a real `DARWIN_BOND_ASSET`, and run `./ops/preflight_base_sepolia.sh`
13. If you need to reproduce the DRW alpha genesis flow, use `.env.base-sepolia` plus `./ops/deploy_public_drw.sh`
14. If you open a PR, expect GitHub Actions to run bootstrap, the Python self-check, the Foundry suite, the devnet flow, and the local deployment smoke flow.

## Code Style

- Python: ruff, line length 120, Python 3.12+
- Solidity: 0.8.24, optimizer enabled

## Pull Requests

- One concern per PR
- Tests must pass
- Contract changes require test coverage for all state transitions
- Overlay service changes require devnet integration test

## What We Need

Priority contributions (in order):

1. **External canary operations** — first outside watcher, first outside archive epoch, and real operator feedback against the live Base Sepolia artifact
2. **DRW canary integration** — operate the live DRW-enabled Base Sepolia artifact honestly, expose live token/staking state in ops evidence, and decide if or when bond economics should migrate away from the current WETH-bond alpha
3. **Audit prep** — deepen cross-contract invariants, adversarial testing, and reviewer-facing threat/model evidence beyond the current auth + lifecycle coverage; use `ops/export_audit_bundle.py` to package the live artifact, readiness evidence, `docs/AUDIT_READINESS.md`, and `docs/THREAT_MODEL.md`
4. **Watcher improvements** — more granular replay checks, better error reporting, long-run auto-sync recovery under real archive churn, better operator handoff material via `ops/export_external_watcher_bundle.py`, and cleaner incoming evidence verification via `ops/intake_external_watcher_report.py`
5. **Canary data flow** — automate archive ingest, replay promotion, and external watcher onboarding around the live Base Sepolia artifact plus `run_external_watcher.sh`, `publish_canary_epoch.sh`, the operator bundle export, and the watcher-intake path
6. **Documentation, handoff packets, and wallet ergonomics** — operator runbooks, API docs, audit-readiness materials, sendable outside-review packets, and safer local wallet workflows

## What We Don't Need Yet

- Chain client forks (v1 is an overlay)
- Mainnet DRW distribution and exchange-listing work
- Marketing materials
- Governance UI
