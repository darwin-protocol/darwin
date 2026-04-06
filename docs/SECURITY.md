# Security

## Reporting Vulnerabilities

If you discover a security vulnerability in DARWIN, please report it privately. Do not open a public GitHub issue.

**Current status:** a dedicated security mailbox is not configured yet.
Before canary, replace this section with a monitored security contact or private reporting workflow.

## Scope

The following components are in scope for security reports:

- Smart contracts (`contracts/src/`)
- Overlay services (`overlay/`)
- SDK signing and verification (`sim/darwin_sim/sdk/`)
- Watcher replay logic (`sim/darwin_sim/watcher/`)

## Bug Bounty

A bug bounty program will be established before mainnet launch. Details will be published here.

## Current Security Status

| Component | Status |
|---|---|
| Contracts | Written, tested (`66` unit tests + `18` fuzz targets + `9` invariants), NOT audited |
| Overlay services | Alpha, local/devnet proven, with watcher auto-sync, finalizer auto-poll, and persisted router/sentinel/finalizer state snapshots; NOT production-hardened |
| Base Sepolia deployment | Live alpha artifact exists at `ops/deployments/base-sepolia.json`; current public deploy uses external Base Sepolia `WETH9`, and `./ops/run_base_sepolia_canary.sh` pins the overlay stack to that artifact while verifying on-chain contract code plus governance/operator wiring across settlement, bond, challenge, species, score, and optional DRW contracts when present |
| SDK crypto | Real ML-DSA-65 + real secp256k1 signatures |
| Gateway verification | Verifies both signature legs and payload binding off-chain; can pin admission to a deployment artifact |
| Watcher verification | Archive artifacts can be mirrored and replayed with hash checks before scoring verification; deployment-aware `darwinctl status-check` emits machine-readable readiness reports with on-chain auth checks plus DRW allocation verification, `./ops/run_external_watcher.sh` provides a dedicated outside-operator bootstrap path, `ops/export_external_watcher_bundle.py` packages a handoff packet for outside watchers, `ops/intake_external_watcher_report.py` verifies returned watcher evidence against the pinned deployment, and `ops/export_audit_bundle.py` packages the evidence plus `docs/AUDIT_READINESS.md` and `docs/THREAT_MODEL.md` for external review |
| Key management | Development only — encrypted local wallet files exist for trader identities via `darwinctl wallet-init`, but there is still no HSM or production custody integration |
| DRW genesis | Alpha DRW token + staking are now live on Base Sepolia via `DRWToken`, `DRWStaking`, and `./ops/deploy_public_drw.sh`; the public canary still uses Base Sepolia `WETH9` as its bond asset |
| Market bootstrap | `ops/preflight_market_bootstrap.py` checks whether a wallet can honestly seed a small `DRW/WETH` market, and `./ops/wrap_base_sepolia_weth.sh` handles the exact ETH→WETH prep step; these are readiness aids, not market-manipulation tools |
| External review prep | `ops/prepare_external_packets.py` emits sendable operator/reviewer tarballs, checksums, request templates, and `docs/EXTERNAL_CANARY_CHECKLIST.md`; `ops/intake_external_review.py` now logs returned reviewer findings into a fixed intake/triage path |

## Known Limitations

1. **v1 is an overlay, not a sovereign chain.** Settlement trust depends on the underlying EVM L2.
2. **v1 is PQ-hardened, not fully post-quantum.** The settlement chain and on-chain verification remain classical.
3. **The EVM envelope is verified off-chain in v1.** Gateway/operator flows can pin to a deployment artifact, but settlement verification is still classical and off-chain for the PQ leg.
4. **No formal audit has been conducted.**
5. **Meaningful Foundry fuzz and stateful invariant coverage exists, but deeper cross-contract and long-run adversarial testing are still pending.**
6. **Safe mode is triggered manually by an admin multisig in v1.**
7. **The current public Base Sepolia deployment is still alpha.** It now includes a live testnet DRW token + staking layer, but canary bonding still uses external Base Sepolia `WETH9`.

## Security Invariants

These invariants are tested in the contract test suite:

1. No intent settles above its remaining quantity (no overfill)
2. No batch submission or net settlement replay with the same batchId
3. Slashing is restricted to ChallengeEscrow role only
4. Safe mode blocks both new batch submission and net settlement, while preserving bond withdrawals
5. Epoch finalization requires challenge window expiry + all roots present
6. Bond withdrawal requires 7-day cooldown
7. Only governance can exit safe mode
8. Duplicate challenge IDs are rejected before funds move
9. Existing pair IDs cannot be recreated or overwritten
10. Fully slashed bonds are marked inactive instead of remaining logically live
11. BondVault token balances always match the sum of outstanding bonds under stateful action sequences
12. SharedPairVault token balances and LP share supply remain internally consistent under stateful action sequences
13. Epoch IDs cannot be reopened or overwritten after creation
14. Invalid epoch configs are rejected before lifecycle state is mutated
15. SettlementHub batch count always matches the set of submitted tracked batches under stateful action sequences
16. SettlementHub net settlement conserves tracked ERC-20 balances across randomized batch/safe-mode flows
17. Only governance-authorized batch operators can submit batches or cancel intents
18. Only the original batch submitter or governance can execute net settlement for a submitted batch
19. Missing species cannot be mutated or slashed into existence through governance/operator paths
20. Tracked species slots remain internally consistent under randomized propose/state/slash sequences
21. Epoch roots must be non-zero and can only be posted once the epoch is closed
22. Deployment-pinned readiness checks verify live governance/operator/bond wiring, not just bytecode presence
23. Zero-value LP actions and ghost pair weight updates are rejected before they can create meaningless vault state
24. Malformed batch headers and malformed net transfers are rejected before settlement state mutates
25. Score roots are single-use and zero-root publication is rejected before score state is written
