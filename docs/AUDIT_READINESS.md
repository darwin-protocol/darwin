# DARWIN Audit Readiness

## Snapshot

- Public repo: `github.com/darwin-protocol/darwin`
- Current public testnet deployment: Base Sepolia `84532`
- Current settlement hub: `0x556d75f4455cf3f0D7c5F9c6e7ea49447f66D8d2`
- Current bond asset: Base Sepolia `WETH9` `0x4200000000000000000000000000000000000006`
- Current live roles:
  - governance: `0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d`
  - epoch operator: `0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d`
  - batch operator: `0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d`
  - safe mode authority: `0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d`

## Scope

This document is the reviewer-facing entry point for the current alpha-canary system. It covers:

- smart-contract trust boundaries
- overlay/operator trust boundaries
- current machine-checked evidence
- known residual risks before outside canary and audit

It does not claim mainnet readiness.

## Trust Boundaries

### 1. Wallet / intent boundary

Assets:
- trader intent authenticity
- trader chain / settlement-hub binding

Current controls:
- ML-DSA-65 and secp256k1 dual-envelope signing
- gateway-side verification of both signature legs
- deployment-aware binding to the pinned chain and settlement hub

Residual risk:
- verification is still off-chain in v1

### 2. Gateway / router boundary

Assets:
- route admission policy
- deployment pinning
- species selection correctness

Current controls:
- gateway config endpoint is checked in `darwinctl status-check`
- canary reports verify chain / settlement hub match the pinned artifact

Residual risk:
- gateway and router remain overlay services, not on-chain enforcement points

### 3. Archive / watcher boundary

Assets:
- published epoch artifacts
- replay integrity
- independent mismatch detection

Current controls:
- archive mirroring with hash checks
- watcher replay verification
- cold-start vs warm readiness made explicit
- standalone outside-watcher bootstrap path

Residual risk:
- first genuinely external watcher is still pending
- current live canary epochs are still operator-seeded rather than independently sourced

### 4. Contract boundary

Assets:
- settlement authorization
- bond accounting
- epoch lifecycle correctness
- root publication integrity
- species lifecycle integrity

Current controls:
- malformed batch headers rejected
- malformed net transfers rejected
- net settlement restricted to original batch submitter or governance
- safe mode halts submission and settlement
- epoch roots must be non-zero and can only be posted after close
- score roots are single-use and non-zero
- missing species cannot be mutated into existence
- zero-value LP actions and ghost pair weight updates are rejected

Residual risk:
- broader cross-contract invariants and long-run adversarial campaigns are still pending

### 5. Governance / admin boundary

Assets:
- emergency safe mode
- batch operator authorization
- epoch operator privileges

Current controls:
- live canary readiness now verifies on-chain governance / operator / bond wiring against the pinned artifact
- audit bundle exports the current artifact and live readiness evidence together

Residual risk:
- the current public alpha uses one address for all live roles
- safe mode is still an explicit admin control in v1

## Current Machine-Checked Evidence

- Python end-to-end self-check
- Foundry unit tests
- Foundry fuzz coverage
- Foundry stateful invariants
- deployment-aware canary readiness reports
- on-chain code and auth verification against the live Base Sepolia artifact
- reviewer bundle export via `ops/export_audit_bundle.py`
- repo-grounded threat model in `docs/THREAT_MODEL.md`
- outside-watcher evidence intake via `ops/intake_external_watcher_report.py`
- sendable operator/reviewer packet prep via `ops/prepare_external_packets.py`, including checksums and request templates

## Audit-Relevant Questions

Reviewers should focus on:

1. settlement authorization and replay invariants across `SettlementHub`, `BondVault`, and `SharedPairVault`
2. epoch and score-root lifecycle correctness across `EpochManager` and `ScoreRegistry`
3. challenge economics and accounting consistency in `ChallengeEscrow`
4. overlay trust assumptions around gateway verification and watcher challengeability
5. single-operator role concentration in the current alpha canary

## Remaining Gaps Before Live Claim

- first external watcher operator
- first genuinely external archive epoch through the live canary path
- independent external security review / audit
- broader adversarial and cross-contract coverage beyond the current local baseline

## Evidence Paths

- deployment artifact: `ops/deployments/base-sepolia.json`
- canary readiness report: `ops/state/base-sepolia-canary/reports/status-report.json`
- canary markdown summary: `ops/state/base-sepolia-canary/reports/status-report.md`
- reviewer bundle export: `ops/audit-bundles/`
- threat model: `docs/THREAT_MODEL.md`
- external watcher intake: `ops/external-intake/`
- sendable handoff packets: `ops/handoffs/`
