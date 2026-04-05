# DARWIN

**An evolutionary intent-centric exchange protocol**
**with a post-quantum hardened trust model**

DARWIN is a DEX architecture that lets multiple bounded market mechanisms compete for flow instead of forcing every order through one permanent design. Users sign intents, the router selects among execution species, the settlement hub enforces constraints, watchers verify the metrics, and future flow shifts toward the species that actually perform best.

The repository is an alpha implementation that works end to end locally today and is now deployed on Base Sepolia testnet. It is not audited and not canary-live.

## What Is Live Now

- Python self-check: `33/33` passing
- Solidity contracts: `93` passing checks (`66` unit tests + `18` fuzz targets + `9` invariants)
- Overlay devnet: `7/7` services up, watcher archive replay passing, epoch finalizing
- Local Anvil deployment smoke: deploy script writes a complete artifact
- Base Sepolia deployment: public testnet artifact emitted at `ops/deployments/base-sepolia.json` with explicit `bond_asset_mode`
- Gateway admission: real ML-DSA-65 + real secp256k1 verification, with optional deployment pinning
- Watcher operators: real archive mirror + replay path via `darwinctl replay-fetch`, watcher `poll-once`, deployment-aware `darwinctl status-check`, and a one-command canary launcher via `./ops/run_base_sepolia_canary.sh`
- External watcher bootstrap: `./ops/run_external_watcher.sh` boots a single watcher against any archive URL, primes the latest replay, can load a saved `.env.external-watcher` / `DARWIN_WATCHER_ENV_FILE`, and writes watcher reports under `ops/state/external-watcher/reports/`
- Canary reporting: `darwinctl status-check` emits durable JSON/Markdown readiness reports, verifies on-chain auth and bond wiring across five pinned contracts, and `./ops/run_base_sepolia_canary.sh` writes those reports automatically under `ops/state/base-sepolia-canary/reports/`
- Canary data flow: `./ops/publish_canary_epoch.sh <epoch_id> <source_dir>` ingests a new epoch into the running archive, triggers watcher replay, and refreshes readiness reports in one command
- Audit export: `python ops/export_audit_bundle.py ...` packages the pinned deployment artifact, readiness evidence, audit-readiness doc, and threat model into a reviewer-facing bundle under `ops/audit-bundles/`
- External watcher handoff: `python ops/export_external_watcher_bundle.py ...` packages the same pinned deployment plus operator-facing handoff docs and an env template under `ops/operator-bundles/`
- External watcher intake: `python ops/intake_external_watcher_report.py ...` verifies a returned watcher report against the handoff bundle and pinned deployment artifact, then writes a standardized intake summary under `ops/external-intake/`
- Handoff packet prep: `python ops/prepare_external_packets.py ...` creates ready-to-send operator and reviewer tarballs plus checksums, request templates, and a summary/checklist under `ops/handoffs/`
- Overlay recovery: router, sentinel, and finalizer persist JSON state snapshots and recover across restarts
- Finalizer automation: background auto-polling can finalize registered epochs as soon as the challenge window expires
- Wallet readiness: `darwinctl wallet-check` inspects deployer balances on Base Sepolia and Ethereum Sepolia
- Wallet suite: `wallet-init`, `wallet-show`, `wallet-export-public`, and `intent-create --wallet-file` provide an encrypted local trader wallet path instead of one-off ephemeral accounts
- DRW alpha genesis stack: the repo now includes `DRWToken`, `DRWStaking`, `./ops/preflight_drw_genesis.sh`, `./ops/init_drw_genesis.sh`, and `./ops/deploy_drw_genesis.sh` so a local or testnet deployment can produce a fixed DRW genesis and staking reserve artifact
- Contract hardening: duplicate challenge IDs rejected, pair recreation blocked, safe mode halts settlement, batch submission and intent cancellation are operator-gated, malformed batch headers and malformed net transfers are rejected, net settlement is restricted to the batch submitter or governance, epoch IDs are immutable, epoch roots must be non-zero and only post after close, score roots are single-use and non-zero, missing species can no longer be mutated, zero-value LP actions and ghost pair weight updates are rejected, full root gating on epoch finalization, stateful invariants passing
- GitHub Actions workflow: bootstrap + Python + Foundry + devnet + deployment smoke

## What DRW Is

DRW is the protocol stake asset in the DARWIN design. It is **not** meant to be a general-purpose currency claim.

In the DARWIN spec, DRW exists for:

- species bonds
- solver bonds
- watcher and reporter bonds
- constitutional governance
- fee-directed protocol incentives

The important current reality is simpler:

- **the public Base Sepolia canary is still the WETH-bond alpha**
- **DRW is still not activated for the public canary economics**
- **there is still no live DRW earning path on the public canary today**

Today, the live alpha uses WETH-style bonding and rewards for challenge flows. See `contracts/src/BondVault.sol` and `contracts/src/ChallengeEscrow.sol`.

What changed in this repo is that the missing DRW genesis path is now implemented for local and optional testnet deployment:

- `contracts/src/DRWToken.sol`
- `contracts/src/DRWStaking.sol`
- `contracts/script/DeployDRWGenesis.s.sol`
- `ops/init_drw_genesis.sh`
- `ops/deploy_drw_genesis.sh`

That means DARWIN can now produce a fixed-supply alpha DRW genesis artifact and staking reserve when you explicitly deploy that layer against an existing DARWIN deployment artifact.

## Wallet Suite

DARWIN now has a real local wallet path for trader identities.

- `wallet-init` creates an encrypted local wallet file with PQ hot/cold keys plus the bound EVM signing key
- `wallet-show` inspects the wallet's public metadata without exposing secrets
- `wallet-export-public` writes the public account policy material you can share with gateway/operator flows
- `intent-create --wallet-file ...` signs repeatable intents from the same account instead of creating a fresh ephemeral keypair each time

The wallet file is local-only and encrypted with `AES-256-GCM` using an `scrypt`-derived key. It is a developer/operator wallet, not an HSM or production custody system.

For the default local trader identity and demo intent:

```bash
./ops/init_demo_wallet.sh
```

That creates or refreshes:

- `ops/wallets/darwin-demo-trader.wallet.json`
- `ops/wallets/darwin-demo-trader.account.json`
- `ops/wallets/darwin-demo-trader.passphrase`
- `sim/intent-base-sepolia.json`

Manual wallet path:

```bash
export DARWIN_WALLET_PASSPHRASE='change-me-local'
darwinctl wallet-init --deployment-file ops/deployments/base-sepolia.json --label alpha-trader --out darwin_wallet.json
darwinctl wallet-show darwin_wallet.json
darwinctl wallet-export-public darwin_wallet.json --out darwin_account.json
```

## How To Produce DRW Genesis

There are now two concrete ways to do it.

Local one-command smoke path:

```bash
DARWIN_DEPLOY_DRW_GENESIS=1 ./ops/smoke_deploy_local.sh
darwinctl deployment-show --deployment-file ops/deployments/local-anvil.json
```

That deploys the core DARWIN contracts, deploys `DRWToken` + `DRWStaking`, mints a fixed genesis allocation, schedules the initial staking rewards, and merges the DRW section into `ops/deployments/local-anvil.json`.

Existing deployment artifact path:

```bash
cp ops/base_sepolia.env.example .env.base-sepolia
# fill in DARWIN_DEPLOYER_PRIVATE_KEY and any optional DRW recipient overrides once

./ops/preflight_drw_genesis.sh
./ops/init_drw_genesis.sh
darwinctl deployment-show --deployment-file ops/deployments/base-sepolia.json
```

Default alpha genesis parameters:

- total supply: `1,000,000,000 DRW`
- treasury: `20%`
- insurance: `20%`
- sponsor rewards: `10%`
- staking reserve: `30%`
- community reserve: `20%`
- staking duration: `31536000` seconds (`365 days`)

`./ops/preflight_base_sepolia.sh`, `./ops/deploy_base_sepolia.sh`, `./ops/preflight_drw_genesis.sh`, and `./ops/init_drw_genesis.sh` now auto-load `.env.base-sepolia` or the file pointed to by `DARWIN_ENV_FILE`.

All of those can be overridden with `DARWIN_DRW_*` env vars in [ops/base_sepolia.env.example](/path/to/darwin/ops/base_sepolia.env.example).

## How You Earn In The DARWIN Design

### What is actually earnable today

- A watcher that opens an upheld challenge can earn a WETH reward in the current contract model.
- A public finalizer can finalize epochs permissionlessly after the challenge window; this is a utility role, not a DRW reward path.
- Researchers and operators can contribute species, replay verification, and deployment hardening, but that is contribution work, not live token farming.

### What is intended after DRW activation

According to the canonical spec:

- DRW stakers receive a share of protocol take.
- Species sponsors receive sponsor rewards when their species serves flow well.
- Solvers and watchers post DRW stake and are slashable for misconduct.
- Governance uses DRW for constitutional decisions, not daily fee tweaking.

Reference design from the spec:

- Insurance vault: 40% of protocol take
- DRW stakers: 30%
- Treasury: 20%
- Species sponsor reward: 10%

These are protocol-design targets. The repo now has an alpha DRW genesis/staking implementation, but the public Base Sepolia canary has not been switched over to DRW-bond economics yet.

## What DARWIN Is Not

- not a live DRW token launch
- not a mainnet-ready exchange
- not a sovereign chain
- not fully post-quantum end to end
- not audited

The honest label for v1 is:

> PQ-hardened intent layer on classical EVM settlement.

## Architecture

DARWIN has six operational layers:

1. **Intent layer**: users sign structured intents with real ML-DSA-65 and secp256k1 bindings.
2. **Router**: chooses between species according to context and bounded canary rules.
3. **Species**: different execution mechanisms such as baseline, batch auction, and RFQ.
4. **Settlement hub**: enforces accounting, replay protection, and batch settlement semantics.
5. **Scoring and watchers**: publish and independently replay epoch outcomes.
6. **Evolution loop**: uses measured outcomes to shift future flow within approved bounds.

```text
Trader / Wallet
    |
    v
Signed Intent
    |
    v
Gateway -> Router -> Species
    |                 |
    |                 v
    |          candidate fills
    |                 |
    +------------> SettlementHub
                         |
                         v
                 on-chain accounting
                         |
          +--------------+--------------+
          |                             |
          v                             v
   Score / roots                    Archive
          |                             |
          v                             v
       Watchers -----------------> challenges
          |
          v
   future flow allocation
```

### Core Components

| Layer | Responsibility |
|---|---|
| `sim/` | Simulator, SDK, CLI, experiment suite, datasets, replay logic |
| `overlay/` | Gateway, router, scorer, watcher, archive, finalizer, sentinel |
| `contracts/` | Settlement, bonding, scoring, registry, vault, and epoch contracts |
| `ops/` | Bootstrap, deployment scripts, preflight checks, artifacts |
| `spec/` | Canonical protocol and economic design |

## Trust Model

### v1 trust boundary

- settlement finality comes from a classical EVM chain
- PQ crypto hardens user authentication and transport
- gateway verification is off-chain
- watcher challengeability is part of the trust story
- safe mode remains admin-controlled in v1

### What this means operationally

- the interesting part of DARWIN is the market structure and verification loop
- the trust bottleneck is still classical settlement
- DRW activation is gated behind canary and security work, not marketing milestones

## Current Verified Status

| Component | Status |
|---|---|
| Python self-check | Verified locally (`33/33` passing) |
| Solidity contracts | Verified locally (`66` unit tests + `18` fuzz targets + `9` invariants) |
| Gateway verification | Real signature verification plus optional deployment pinning |
| Overlay services | Verified locally (`7/7` services up), including watcher archive replay, readiness after archive ingest, auto-sync status reporting, persisted state snapshots, finalizer auto-poll, and deployment-pinned on-chain auth checks |
| Local deployment | Working on Anvil with emitted artifact |
| Base Sepolia deploy | Live on chain `84532` with emitted artifact at `ops/deployments/base-sepolia.json` (`bond_asset_mode=external`) |
| Audit bundle | Exportable from the live artifact, readiness report, audit-readiness doc, and threat model via `ops/export_audit_bundle.py` |
| External watcher handoff | Exportable as an operator packet via `ops/export_external_watcher_bundle.py` |
| External watcher intake | Verifiable against the pinned deployment and bundle via `ops/intake_external_watcher_report.py` |
| External packet prep | Sendable operator/reviewer tarballs via `ops/prepare_external_packets.py` |
| DRW activation | Optional alpha genesis path implemented locally/testnet; not live on the public canary |
| Wallet suite | Encrypted local wallet files plus repeatable intent signing via `darwinctl wallet-*` |

## Quick Start

```bash
git clone https://github.com/darwin-protocol/darwin.git
cd darwin
./ops/bootstrap_dev.sh
source .venv/bin/activate
export DARWIN_WALLET_PASSPHRASE='change-me-local'

cd sim
python -m pytest tests/test_end_to_end.py -v
cd ../contracts
forge test --summary
cd ..

./ops/init_demo_wallet.sh
darwinctl wallet-show ops/wallets/darwin-demo-trader.wallet.json
python overlay/devnet.py
./ops/smoke_deploy_local.sh
DARWIN_DEPLOY_DRW_GENESIS=1 ./ops/smoke_deploy_local.sh
darwinctl deployment-show --deployment-file ops/deployments/local-anvil.json
darwinctl intent-create --wallet-file ops/wallets/darwin-demo-trader.wallet.json --deployment-file ops/deployments/local-anvil.json
darwinctl intent-verify intent.json --deployment-file ops/deployments/local-anvil.json
darwinctl replay-fetch --archive-url http://localhost:9447 --out watcher_artifacts
darwinctl status-check
darwinctl status-check --json-out status.json --markdown-out status.md
darwinctl wallet-check --address 0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d
python ops/export_audit_bundle.py --deployment-file ops/deployments/base-sepolia.json --status-json ops/state/base-sepolia-canary/reports/status-report.json --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
python ops/export_external_watcher_bundle.py --deployment-file ops/deployments/base-sepolia.json --status-json ops/state/base-sepolia-canary/reports/status-report.json --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
python ops/intake_external_watcher_report.py --bundle-dir ops/operator-bundles/<bundle> --report-json watcher-status.json --report-markdown watcher-status.md
python ops/prepare_external_packets.py --deployment-file ops/deployments/base-sepolia.json --status-json ops/state/base-sepolia-canary/reports/status-report.json --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
```

## Base Sepolia Preflight And Deploy

Before trying to deploy, run the explicit preflight:

```bash
export ALCHEMY_API_KEY=...
export BASE_SEPOLIA_RPC_URL=...
export DARWIN_DEPLOYER_PRIVATE_KEY=...
export DARWIN_GOVERNANCE=0x...
export DARWIN_EPOCH_OPERATOR=0x...
export DARWIN_SAFE_MODE_AUTHORITY=0x...
export DARWIN_BOND_ASSET=0x4200000000000000000000000000000000000006

./ops/preflight_base_sepolia.sh
```

There is also a starter env template in `ops/base_sepolia.env.example`.
If `ALCHEMY_API_KEY` is set, the preflight and deploy scripts can derive Base Sepolia and Ethereum Sepolia RPC URLs automatically.
`./ops/preflight_base_sepolia.sh`, `./ops/deploy_base_sepolia.sh`, `./ops/preflight_drw_genesis.sh`, and `./ops/init_drw_genesis.sh` auto-load `.env.base-sepolia` or the file pointed to by `DARWIN_ENV_FILE`.

What preflight checks:

- Base Sepolia RPC reachability and chain id
- deployer address derivation
- current Base Sepolia ETH balance
- current Ethereum Sepolia ETH balance
- required deployment env vars
- whether the deployment is actually ready to send

You can inspect a wallet directly before preflight:

```bash
darwinctl wallet-check --address 0xD4C2E5225a69E6947F6B95479e3e4E5D28EAEF04
darwinctl wallet-check --address 0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d
```

For DRW specifically, the shortest path is now:

```bash
cp ops/base_sepolia.env.example .env.base-sepolia
# fill in DARWIN_DEPLOYER_PRIVATE_KEY and any optional DARWIN_DRW_* overrides

./ops/preflight_drw_genesis.sh
./ops/init_drw_genesis.sh
```

If preflight passes:

```bash
./ops/deploy_base_sepolia.sh
darwinctl deployment-show --deployment-file ops/deployments/base-sepolia.json
```

Artifacts are written to `ops/deployments/<network>.json` by default.

Boot a deployment-pinned canary stack locally:

```bash
./ops/run_base_sepolia_canary.sh
```

This starts gateway, router, scorer, archive, watcher, finalizer, and sentinel pinned to the Base Sepolia artifact. On first boot the watcher is expected to report `COLD` until it mirrors and replays at least one archive epoch.

Each run also writes:

- `ops/state/base-sepolia-canary/reports/status-report.json`
- `ops/state/base-sepolia-canary/reports/status-report.md`

To hand the current deployment and readiness state to an outside watcher operator:

```bash
python ops/export_external_watcher_bundle.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --status-json ops/state/base-sepolia-canary/reports/status-report.json \
  --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
```

This writes an operator packet under `ops/operator-bundles/` with:

- the pinned deployment artifact
- the latest readiness evidence
- `docs/OPERATOR_QUICKSTART.md`
- `docs/AUDIT_READINESS.md`
- `docs/THREAT_MODEL.md`
- a generated `external-watcher.env.example`

When an outside operator sends back their watcher report, verify it against the same bundle and the pinned deployment artifact:

```bash
python ops/intake_external_watcher_report.py \
  --bundle-dir ops/operator-bundles/<bundle-dir> \
  --report-json watcher-status.json \
  --report-markdown watcher-status.md
```

This writes a normalized intake packet under `ops/external-intake/` and marks whether the returned watcher replay is acceptable.

To prepare the actual sendable tarballs for an outside watcher and external reviewer in one step:

```bash
python ops/prepare_external_packets.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --status-json ops/state/base-sepolia-canary/reports/status-report.json \
  --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
```

This writes:

- fresh operator and reviewer bundle directories
- `.tar.gz` archives for each
- `CHECKSUMS.txt`
- `WATCHER_OPERATOR_REQUEST.md`
- `EXTERNAL_REVIEW_REQUEST.md`
- `handoff-summary.json`
- `handoff-summary.md`
- `docs/EXTERNAL_CANARY_CHECKLIST.md`

To seed the stack from the local published E2 artifacts and force watcher readiness immediately:

```bash
DARWIN_CANARY_SEED_DIR="$PWD/sim/outputs/test_e2" \
DARWIN_CANARY_SEED_EPOCH_ID="seed-1" \
./ops/run_base_sepolia_canary.sh
```

The seeded run overwrites the same report paths with the warm status and keeps phase-specific snapshots in the same directory.

To feed a new epoch through a running canary stack:

```bash
./ops/publish_canary_epoch.sh canary-2 "$PWD/sim/outputs/test_e2"
```

This writes:

- `ops/state/base-sepolia-canary/reports/publish-canary-2-summary.json`
- `ops/state/base-sepolia-canary/reports/publish-canary-2-summary.md`
- `ops/state/base-sepolia-canary/reports/status-after-canary-2.json`
- `ops/state/base-sepolia-canary/reports/status-after-canary-2.md`

Current public testnet artifact:

- network: `base-sepolia`
- chain id: `84532`
- deployer: `0xBFf27f141250C1323431eDB1BfCbB7D550a168f6`
- bond asset mode: `external`
- bond asset: `0x4200000000000000000000000000000000000006`
- governance / epoch operator / safe mode: `0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d`
- batch operator: `0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d`
- settlement hub: `0x556d75f4455cf3f0D7c5F9c6e7ea49447f66D8d2`

## How To Participate Today

### Operators

- run a watcher and verify epochs independently
- bootstrap a standalone watcher with `DARWIN_WATCHER_ARCHIVE_URL=http://archive-host:9447 ./ops/run_external_watcher.sh`
- mirror the latest archive epoch with `darwinctl replay-fetch --archive-url ...`
- run an archive mirror
- run a public finalizer
- help canary the deployment-pinned gateway and operator stack

### Researchers

- run the E1-E7 experiment suite
- improve species logic
- improve replay and scoring verification
- deepen adversarial testing and invariants

### Contributors

- harden contracts and off-chain verification
- improve deployment tooling
- improve docs and operator ergonomics

## Remaining Blockers Before Canary

- recruit the first external watcher operator
- feed the first external archive epoch through the Base Sepolia canary stack
- continue invariant and adversarial test expansion
- complete external security review or audit
- pass the DRW activation gates

## DRW Activation Gates

DRW should only activate after:

1. testnet deployment is live and stable
   current status: deployed on Base Sepolia, but not yet canary-operated by outside watchers
2. external watchers replay independently
3. contract and off-chain invariants are stronger
4. audit work is complete
5. canary operations run cleanly for the required window

Until then, DRW is specified protocol stake, not a live public token.

## Deep Docs

- Operator guide: [docs/OPERATOR_QUICKSTART.md](docs/OPERATOR_QUICKSTART.md)
- Security notes: [docs/SECURITY.md](docs/SECURITY.md)
- Threat model: [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md)
- External canary checklist: [docs/EXTERNAL_CANARY_CHECKLIST.md](docs/EXTERNAL_CANARY_CHECKLIST.md)
- Canonical spec: [spec/DARWIN_v0.2_Canonical_Spec.md](spec/DARWIN_v0.2_Canonical_Spec.md)
- Contribution guide: [CONTRIBUTING.md](CONTRIBUTING.md)

## Repository Layout

```text
darwin/
  spec/        Canonical protocol and economic design
  sim/         Simulator, SDK, CLI, configs, tests, datasets
  overlay/     Gateway and overlay services
  contracts/   Solidity contracts
  ops/         Bootstrap, deploy, preflight, artifacts
  docs/        Operator and security docs
```

## License

MIT
