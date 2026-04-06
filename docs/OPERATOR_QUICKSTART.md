# DARWIN Operator Quickstart

Run a DARWIN overlay node. Start with **watcher** — the safest and most valuable first role.

## Prerequisites

- Python 3.12+
- Git
- Foundry (`forge`) for contract tests
- ~500 MB disk, 4 vCPU, 16 GB RAM (watcher profile)

## Step 1: Clone and verify

```bash
git clone https://github.com/darwin-protocol/darwin.git
cd darwin
```

## Step 2: Bootstrap the repo

```bash
./ops/bootstrap_dev.sh
source .venv/bin/activate
```

## Step 3: Run the self-check

```bash
cd sim
python -m pytest tests/test_end_to_end.py -v
```

All 41 tests must pass before proceeding.

## Local Wallet Suite

For repeatable trader-side testing, create a local encrypted wallet instead of generating a one-off account every time:

```bash
export DARWIN_WALLET_PASSPHRASE='change-me-local'
darwinctl wallet-init --chain-id 84532 --label alpha-trader
darwinctl wallet-show darwin_wallet.json
darwinctl wallet-export-public darwin_wallet.json --out darwin_account.json
```

Or use the default end-to-end helper:

```bash
./ops/init_demo_wallet.sh
```

To inspect the default local wallet after that helper runs:

```bash
darwinctl wallet-show ops/wallets/darwin-demo-trader.wallet.json
```

To sign a repeatable intent from that wallet:

```bash
darwinctl intent-create \
  --wallet-file darwin_wallet.json \
  --deployment-file ops/deployments/base-sepolia.json \
  --out intent.json
```

## Optional DRW Alpha Genesis

The public Base Sepolia artifact already includes the alpha DRW token + staking layer. To reproduce that deployment against an existing DARWIN deployment artifact, use the same untracked Base Sepolia env file and run:

```bash
cp ops/base_sepolia.env.example .env.base-sepolia
# fill in DARWIN_DEPLOYER_PRIVATE_KEY and optional DARWIN_DRW_* overrides once

./ops/deploy_public_drw.sh
```

For a pure local end-to-end smoke path:

```bash
DARWIN_DEPLOY_DRW_GENESIS=1 ./ops/smoke_deploy_local.sh
```

That writes the DRW section directly into the emitted deployment artifact, including:

- `drw_token`
- `drw_staking`
- total supply
- staking duration
- fixed genesis allocation buckets

`./ops/preflight_base_sepolia.sh`, `./ops/deploy_base_sepolia.sh`, `./ops/preflight_drw_genesis.sh`, `./ops/init_drw_genesis.sh`, and `./ops/deploy_public_drw.sh` auto-load `.env.base-sepolia` or the file pointed to by `DARWIN_ENV_FILE`.

## Optional DRW Market Bootstrap

If you want to seed a small testnet `DRW/WETH` market, start with the readiness check:

```bash
./.venv/bin/python ops/preflight_market_bootstrap.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --wallet-address 0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d
```

Use this only as a preflight. It does not create a pool or execute swaps.

The correct operator claim is "a testnet market exists and third parties can trade it", not "we created activity by swapping ourselves."

The current public Base Sepolia market is already seeded at:

- `0x9E1fb3eb0Ca3b06038d2A4d6b6e5D18183E6B891`
- reserves: `1000 DRW` + `0.0005 WETH`

The repo now also ships a first-party browser portal in `site/`, published through `.github/workflows/pages.yml`, so outside users do not need to start with shell scripts if they just want to connect a wallet and trade on Base Sepolia.

Then confirm the venue path is real on the same network:

```bash
./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --venue uniswap_v4
```

If you want a DARWIN-owned testnet venue on Base Sepolia right now, use the artifact-backed reference pool instead:

```bash
./ops/init_reference_market.sh
export DARWIN_REFERENCE_MARKET_BASE_AMOUNT=1000000000000000000000
export DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT=500000000000000
./ops/seed_reference_market.sh

./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --venue darwin_reference_pool
```

Those example seed amounts are `1000 DRW` and `0.0005 WETH`. That is the current live Base Sepolia seed, and the pool should already be reflected in `ops/deployments/base-sepolia.json`.

To quote a swap against the live pool without sending a transaction:

```bash
DARWIN_DEPLOYER_ADDRESS=0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d \
./ops/swap_reference_market.sh --token-in base --amount 1 --dry-run
```

## Step 4: Run the E1-E7 experiment suite

```bash
python -m darwin_sim.experiments.suite configs/baseline.yaml 10000 2026
```

Expected: all 7 experiments PASS.

## Step 5: Verify watcher replay

```bash
# Run an experiment to produce artifacts
python -m darwin_sim.experiments.runner configs/baseline.yaml data/raw/raw_swaps.csv ../outputs/e2

# Replay and verify independently
python -m darwin_sim.watcher.replay ../outputs/e2
```

Expected: `REPLAY PASSED — all metrics match`

If you have an archive service instead of a local artifact directory:

```bash
darwinctl replay-fetch --archive-url http://archive-host:9447 --out /var/lib/darwin/watcher
```

Expected: `Archive replay: PASS`

---

## Running the Overlay Services

### Watcher (first role for outside operators)

Fastest path:

```bash
export DARWIN_WATCHER_ARCHIVE_URL=http://archive-host:9447
./ops/run_external_watcher.sh
```

If you received a watcher handoff bundle, you can also save its generated env template as `.env.external-watcher` and run the same command without exporting vars manually:

```bash
cp external-watcher.env.example .env.external-watcher
./ops/run_external_watcher.sh
```

This boots a single watcher, primes the latest replay if the archive is reachable, and writes:

- `ops/state/external-watcher/reports/watcher-status.json`
- `ops/state/external-watcher/reports/watcher-status.md`

Manual path:

```bash
cd darwin
export PYTHONPATH="$PWD/sim"
python overlay/watcher/service.py 9446 /var/lib/darwin/watcher http://archive-host:9447
```

To keep the watcher synced automatically instead of replaying ad hoc:

```bash
export DARWIN_WATCHER_POLL_SEC=60
python overlay/watcher/service.py 9446 /var/lib/darwin/watcher http://archive-host:9447
```

**What it does:**
- Mirrors epoch artifacts from the archive
- Recomputes all scores independently
- Detects mismatches and emits challenge candidates
- Optionally polls the archive for new epochs automatically
- Serves replay status via HTTP

**Endpoints:**
- `GET /healthz` — health check
- `GET /readyz` — readiness (has it replayed at least one epoch?)
- `GET /v1/archive/epochs` — inspect epochs visible from the archive
- `GET /v1/status` — all replay results
- `GET /v1/epochs/:id` — single epoch detail
- `GET /v1/challenges/open` — detected mismatches
- `POST /v1/replay/local` — replay from local artifacts
- `POST /v1/replay/archive` — mirror one archive epoch and replay it
- `POST /v1/replay/latest` — mirror the latest archive epoch and replay it
- `POST /v1/replay/poll-once` — replay only if the archive has advanced

**Success condition:** Your watcher produces `passed: true` on the latest epoch.

### Archive mirror

```bash
python overlay/archive/service.py 9447 /var/lib/darwin/archive
```

**What it does:**
- Stores epoch artifacts with SHA-256 verification
- Serves them to watchers via HTTP

**Endpoints:**
- `GET /v1/epochs` — list available epochs
- `GET /v1/epochs/:id` — epoch manifest with file hashes
- `GET /v1/epochs/:id/:filename` — download artifact
- `POST /v1/ingest` — ingest new epoch

### Public finalizer

```bash
export DARWIN_FINALIZER_POLL_SEC=60
python overlay/finalizer/service.py 9448 1800 /var/lib/darwin/finalizer/state.json
```

**What it does:**
- Monitors epoch state
- Finalizes epochs permissionlessly after the challenge window (1800s = 30 min)
- Persists registered/finalized epoch state across restarts
- Can poll automatically instead of waiting for manual finalize calls
- No bond required — just gas

**Endpoints:**
- `GET /v1/status` — current finalizer state
- `GET /v1/check/:epoch_id` — is it finalizable?
- `POST /v1/finalize/:epoch_id` — finalize it
- `POST /v1/poll-once` — finalize all ready epochs once

---

## Running the Full Devnet

Start all 7 services and run the integration test:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD/sim"
python overlay/devnet.py
```

Expected output: 7/7 services UP, E2 PASS, watcher PASS through archive replay, epoch finalized.

Inspect overlay readiness from one command:

```bash
darwinctl status-check
darwinctl status-check --json-out status.json --markdown-out status.md
```

If you are booting a fresh watcher with no mirrored epochs yet, allow the expected cold-start state:

```bash
darwinctl status-check --allow-cold-watcher
```

The JSON report is intended for automation; the Markdown report is the operator-facing canary summary. When you pin `--deployment-file`, `status-check` also verifies on-chain bytecode, governance/operator wiring, settlement batch authorization, bond-asset linkage, and optional DRW token/staking wiring plus live DRW holder balances against the artifact.

To package the current deployment artifact plus readiness evidence for an outside reviewer:

```bash
python ops/export_audit_bundle.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --status-json ops/state/base-sepolia-canary/reports/status-report.json \
  --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
```

To package the same pinned deployment plus operator-facing handoff material for an outside watcher:

```bash
python ops/export_external_watcher_bundle.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --status-json ops/state/base-sepolia-canary/reports/status-report.json \
  --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
```

This writes a watcher handoff packet under `ops/operator-bundles/` with the pinned deployment artifact, latest readiness evidence, operator quickstart, audit-readiness doc, threat model, and a generated `external-watcher.env.example`.

When the outside operator sends back `watcher-status.json` and `watcher-status.md`, verify them against the bundle and pinned deployment:

```bash
python ops/intake_external_watcher_report.py \
  --bundle-dir ops/operator-bundles/<bundle-dir> \
  --report-json watcher-status.json \
  --report-markdown watcher-status.md
```

This writes an intake summary under `ops/external-intake/` and tells you whether the external replay is clean enough to count toward canary evidence.

To produce ready-to-send operator and reviewer tarballs plus checksums, request templates, and a checklist in one command:

```bash
python ops/prepare_external_packets.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --status-json ops/state/base-sepolia-canary/reports/status-report.json \
  --status-markdown ops/state/base-sepolia-canary/reports/status-report.md
```

Inspect a deployer wallet before trying Base Sepolia preflight:

```bash
darwinctl wallet-check --address 0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d
```

---

## Role Onboarding Order

1. **Watcher** — verify epoch scores independently
2. **Archive mirror** — store and serve artifacts
3. **Public finalizer** — finalize epochs after challenge window
4. **Gateway** — accept intents (requires 2 WETH bond)
5. **Solver** — quote for RFQ species

---

## Trust Model (Honest)

v1 is a **PQ-hardened intent layer on classical EVM settlement**.

- Settlement trust: classical chain (machine-enforced)
- Intent authenticity: gateway/service-level verification of ML-DSA-65 + secp256k1 in v1
- Score correctness: challengeable (watcher-verified)
- Emergency intervention: admin multisig (explicitly centralized in v1)

Do NOT call these "validator nodes." They are overlay service nodes.

---

## Contract Tests

```bash
cd contracts
forge test --summary
```

Expected: `forge test --summary` passes cleanly.
Current baseline: `87` passing checks (`60` unit tests + `18` fuzz targets + `9` invariants).
The current suite includes stateful invariants for settlement auth and species lifecycle consistency, plus fuzz coverage for missing-species rejection, malformed settlement inputs, score-root single-use, zero-value LP actions, and permissionless epoch finalization.

If you skipped `./ops/bootstrap_dev.sh`, install the Foundry test dependency first:

```bash
forge install --no-git --shallow foundry-rs/forge-std
```

## Deployment

Local deployment smoke test:

```bash
./ops/smoke_deploy_local.sh
```

Expected artifact: `ops/deployments/local-anvil.json`

Base Sepolia deployment:

```bash
cp ops/base_sepolia.env.example .env.base-sepolia
source .env.base-sepolia
export DARWIN_DEPLOYER_PRIVATE_KEY=...
export DARWIN_GOVERNANCE=0x...
export DARWIN_EPOCH_OPERATOR=0x...
export DARWIN_SAFE_MODE_AUTHORITY=0x...
export DARWIN_BOND_ASSET=0x4200000000000000000000000000000000000006
./ops/preflight_base_sepolia.sh
./ops/deploy_base_sepolia.sh
```

If `ALCHEMY_API_KEY` is exported, `./ops/preflight_base_sepolia.sh` and `./ops/deploy_base_sepolia.sh` can derive the Base Sepolia RPC URL automatically.

Expected artifact: `ops/deployments/base-sepolia.json`

The repo already contains a public Base Sepolia artifact emitted on 2026-04-05:

```bash
source .venv/bin/activate
darwinctl deployment-show --deployment-file ops/deployments/base-sepolia.json
```

The emitted artifact currently reports `bond_asset_mode=external` and points at Base Sepolia `WETH9`.
The current public artifact also records `batch_operator`, which is the address allowed to submit batches and cancel intents on the live `SettlementHub`.

Inspect the artifact and create deployment-bound intents:

```bash
darwinctl deployment-show --deployment-file ops/deployments/base-sepolia.json
darwinctl intent-create --deployment-file ops/deployments/base-sepolia.json
darwinctl intent-verify intent.json --deployment-file ops/deployments/base-sepolia.json
```

If you run a live gateway, pin admission to that deployment:

```bash
export DARWIN_DEPLOYMENT_FILE="$PWD/ops/deployments/base-sepolia.json"
python overlay/gateway/server.py 9443 /var/lib/darwin/gateway
```

If you want the full deployment-pinned alpha stack locally, use the canary launcher:

```bash
./ops/run_base_sepolia_canary.sh
```

This starts the full overlay against `ops/deployments/base-sepolia.json`, runs an initial deployment-aware status check, and allows the watcher to remain `COLD` until its first archive replay.

It also writes:

- `ops/state/base-sepolia-canary/reports/status-cold.json`
- `ops/state/base-sepolia-canary/reports/status-cold.md`
- `ops/state/base-sepolia-canary/reports/status-report.json`
- `ops/state/base-sepolia-canary/reports/status-report.md`

To seed the archive and watcher from the local published E2 artifacts during bootstrap:

```bash
DARWIN_CANARY_SEED_DIR="$PWD/sim/outputs/test_e2" \
DARWIN_CANARY_SEED_EPOCH_ID="seed-1" \
./ops/run_base_sepolia_canary.sh
```

When the seed replay succeeds, the launcher refreshes `status-report.{json,md}` and also leaves a warm snapshot beside it.

To publish another epoch into a running canary stack after boot:

```bash
./ops/publish_canary_epoch.sh canary-2 "$PWD/sim/outputs/test_e2"
```

This ingests the source directory into the running archive, asks the watcher to replay that exact epoch, and refreshes both:

- `publish-canary-2-summary.{json,md}`
- `status-after-canary-2.{json,md}`

---

## Questions

- **How do I know if my replay is correct?** Compare your `recomputed_uplift` against the published `uplift` in the epoch report. If they match within 0.5 bps, you're good.
- **What if I find a mismatch?** That's the point. Open a challenge via the ChallengeEscrow contract. Material challenges require 0.25 WETH bond. If upheld, you get your bond back + 25% of the slash.
- **Do I need a bond to run a watcher?** Optional standing bond of 1 WETH. You can run without one, but bonded watchers get priority in the challenge queue.
