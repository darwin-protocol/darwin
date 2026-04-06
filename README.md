# DARWIN

A peer-to-peer system for evolving exchange microstructure.

## Start Here

- Current project status: [LIVE_STATUS.md](LIVE_STATUS.md)
- Public Base Sepolia artifact: [ops/deployments/base-sepolia.json](ops/deployments/base-sepolia.json)
- Operator flow: [docs/OPERATOR_QUICKSTART.md](docs/OPERATOR_QUICKSTART.md)
- Security posture: [docs/SECURITY.md](docs/SECURITY.md)
- Market bootstrap: [docs/MARKET_BOOTSTRAP.md](docs/MARKET_BOOTSTRAP.md)

## Status At A Glance

- The repo is reproducible locally.
- The public canary exists on Base Sepolia.
- The public canary is still `WETH`-bond, not `DRW`-bond.
- The Base Sepolia `DRW` token + staking layer is now live.
- The repo now ships a first-party reference-pool path for a `DRW/WETH` testnet market.
- The next live steps are outside-watcher operation, outside archive flow, and external review.

## Abstract

Current decentralized exchanges hard-code one market design and ask all participants to accept its trade-offs permanently. DARWIN replaces this with bounded competition: multiple execution mechanisms run simultaneously, a scoring system measures their real outcomes against a control baseline, and flow shifts toward whichever mechanism actually works best. Governance sets boundaries. The protocol adapts within them.

The core idea is selection pressure applied to market structure, not governance votes about fee parameters.

## Running

```bash
cd sim && python -m venv .venv && source .venv/bin/activate
pip install pyyaml numpy pandas pyarrow zstandard dilithium-py
python -m pytest tests/ -v
python -m darwin_sim.experiments.suite configs/baseline.yaml
```

```bash
cd contracts && forge test
```

```bash
python overlay/devnet.py
```

## Design

Intents are signed with both a post-quantum key (`ML-DSA-65`) and a classical EVM key, cryptographically bound. The PQ signature is verified by the overlay services. The EVM signature is verified on-chain. v2 drops the EVM leg.

Species are parameterized execution modules: batch auctions, RFQ solvers, adaptive curves. Each competes for order flow within the same pair. A control reservation always goes to the baseline species so that scoring is counterfactual, not self-referential.

Fitness is measured as causal uplift: trader surplus, LP health, fill rate, and adverse selection, each compared to what the baseline would have produced on the same flow. Scores are published as Merkle roots. Watchers independently reconstruct them and challenge mismatches.

Settlement is on an EVM L2. The protocol does not run its own chain in v1.

## DRW

DRW is protocol stake. It is not a general-purpose currency.

Reference alpha genesis split:

- treasury: `20%`
- insurance: `20%`
- sponsor rewards: `10%`
- staking reserve: `30%`
- community reserve: `20%`

Current truth:

- public Base Sepolia canary: `WETH`-bond alpha
- public Base Sepolia `DRW` token: live at `0x90519DFb5ed50fbd959Ed47BBcf7E4ae33750FF2`
- public Base Sepolia `DRW` staking: live at `0xC84090E74880a672C5273f6A454E208Fe114634e`
- public DRW total supply: `1,000,000,000`
- current live bond asset is still Base Sepolia `WETH9`, not `DRW`

The repo now includes:

- `contracts/src/DRWToken.sol`
- `contracts/src/DRWStaking.sol`
- `contracts/script/DeployDRWGenesis.s.sol`
- `ops/preflight_drw_genesis.sh`
- `ops/init_drw_genesis.sh`
- `ops/deploy_public_drw.sh`

## Wallets

DARWIN has a real local wallet path for trader identities.

- `wallet-init` creates an encrypted local wallet file
- `wallet-show` prints public wallet metadata
- `wallet-export-public` emits shareable public account material
- `intent-create --wallet-file ...` signs repeatable intents from the same account

Fast path:

```bash
./ops/init_demo_wallet.sh
```

## DRW Genesis

Local smoke path:

```bash
DARWIN_DEPLOY_DRW_GENESIS=1 ./ops/smoke_deploy_local.sh
darwinctl deployment-show --deployment-file ops/deployments/local-anvil.json
```

Public Base Sepolia path:

```bash
cp ops/base_sepolia.env.example .env.base-sepolia
# fill in DARWIN_DEPLOYER_PRIVATE_KEY and any optional DARWIN_DRW_* overrides

./ops/deploy_public_drw.sh
```

The Base Sepolia scripts auto-load `.env.base-sepolia` or the file named by `DARWIN_ENV_FILE`.

## Market Bootstrap

The honest next market step is a small `DRW/WETH` testnet pool, not self-swapping for optics.

Run the market preflight first:

```bash
./.venv/bin/python ops/preflight_market_bootstrap.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --wallet-address 0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d
```

That checks:

- gas on Base Sepolia
- live `DRW` balance
- live quote-token balance
- whether the pinned deployment is suitable for a `DRW/WETH` demo market

Current preflight result on the live governance wallet:

- `700,000,000 DRW`
- enough Base Sepolia ETH for gas
- `0 WETH`
- immediate blocker for a `DRW/WETH` demo pool: wrap ETH first

Exact next step:

```bash
./ops/wrap_base_sepolia_weth.sh --amount-eth 0.0005
```

From there, DARWIN now supports two venue paths:

1. A first-party artifact-backed reference pool:

```bash
./ops/init_reference_market.sh
export DARWIN_REFERENCE_MARKET_BASE_AMOUNT=1000000000000000000000
export DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT=500000000000000
./ops/seed_reference_market.sh

./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --venue darwin_reference_pool
```

2. A tracked third-party venue, only if its preflight passes on `84532`:

```bash
./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --venue uniswap_v4
```

Current market blockers are now:

- wrap ETH first
- deploy and seed the artifact-backed reference pool, or wait for a tracked third-party Base Sepolia venue

See [docs/MARKET_BOOTSTRAP.md](docs/MARKET_BOOTSTRAP.md) for the full runbook and risk framing.

## Status

| Component | State |
|---|---|
| Simulator | Working. `41/41` Python checks pass locally. |
| Contracts | `100` checks pass locally (`73` unit + `18` fuzz + `9` invariants). |
| Overlay | 7 services run locally. Gateway admits real PQ-signed intents. |
| Watcher replay | Works. Independent score reconstruction matches. |
| Base Sepolia core | Deployed. Artifact published. |
| DRW token | Live on Base Sepolia. Token + staking deployed; `status-check` now verifies live holder balances against the pinned allocation table. |
| Reference market | Local DRW + reference-pool smoke deploy passes; live Base Sepolia pool is not seeded yet. |
| Audit | Not started. |
| Canary | Not yet operated by genuine outside watchers. |

## What Remains

Real blockers now:

1. first outside watcher operator
2. first outside archive epoch through the live canary
3. external security review / audit
4. legal/compliance structure before any real public token distribution

If a public testnet market is desired before that, the exact market work left is:

1. wrap a small amount of Base Sepolia ETH into WETH
2. deploy and seed the artifact-backed `darwin_reference_pool`, or use a separately tracked third-party venue if one becomes available

The canonical tracker is [LIVE_STATUS.md](LIVE_STATUS.md).

## Repository

```text
spec/        Protocol design
sim/         Simulator, SDK, CLI
contracts/   Solidity (Foundry)
overlay/     Gateway, router, scorer, watcher, archive, finalizer, sentinel
ops/         Deployment scripts and artifacts
docs/        Operator and security documentation
```

## License

MIT
