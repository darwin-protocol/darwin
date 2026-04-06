# DARWIN

A peer-to-peer system for evolving exchange microstructure.

## Start Here

- Current project status: [LIVE_STATUS.md](LIVE_STATUS.md)
- Public site: `http://usedarwin.xyz/` for now, with HTTPS provisioning in progress
- Public web source: [web/](web/)
- Public Base Sepolia artifact: [ops/deployments/base-sepolia.json](ops/deployments/base-sepolia.json)
- Operator flow: [docs/OPERATOR_QUICKSTART.md](docs/OPERATOR_QUICKSTART.md)
- Security posture: [docs/SECURITY.md](docs/SECURITY.md)
- Market bootstrap: [docs/MARKET_BOOTSTRAP.md](docs/MARKET_BOOTSTRAP.md)
- Hosting plan: [docs/HOSTING_ARCHITECTURE.md](docs/HOSTING_ARCHITECTURE.md)
- Custom domain setup: [docs/CUSTOM_DOMAIN_SETUP.md](docs/CUSTOM_DOMAIN_SETUP.md)

## Status At A Glance

- The repo is reproducible locally.
- The public canary exists on Base Sepolia.
- The public canary is still `WETH`-bond, not `DRW`-bond.
- The Base Sepolia `DRW` token + staking layer is now live.
- A seeded `DRW/WETH` reference pool now exists on Base Sepolia.
- A first-party Next.js static-export site now exists in `web/` and deploys through GitHub Pages.
- A transparent Base Sepolia `DRW` faucet is now live for third-party onboarding.
- The next live steps are third-party distribution, outside-watcher operation, outside archive flow, and external review.

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
- governance + staking still directly hold `999,998,950 DRW`
- the remaining `1,050 DRW` are in the seeded reference pool and DARWIN-controlled demo traders
- public Base Sepolia `DRW` faucet: live at `0x3DAa29B6b497a830AA5C3e4eE881ad2fFe2FbAe0`
- live faucet funding: `100,000 DRW` + `0.0002 ETH`

The repo now includes:

- `contracts/src/DRWToken.sol`
- `contracts/src/DRWStaking.sol`
- `contracts/script/DeployDRWGenesis.s.sol`
- `ops/preflight_drw_genesis.sh`
- `ops/init_drw_genesis.sh`
- `ops/deploy_public_drw.sh`
- `contracts/src/DRWFaucet.sol`
- `contracts/script/DeployDRWFaucet.s.sol`
- `ops/init_drw_faucet.sh`
- `ops/fund_drw_faucet.sh`

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

The honest next distribution step is a small public testnet faucet, not pretending project-controlled flow is adoption.

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

Current live market state:

- reference pool: `0x9E1fb3eb0Ca3b06038d2A4d6b6e5D18183E6B891`
- initial reserves: `1000 DRW` and `0.0005 WETH`
- initial DARWIN-controlled demo trades have now executed against the live pool
- current reserves are approximately `985.384919987 DRW` and `0.000507483787963681 WETH`
- venue preflight now keys off the seeded artifact-backed pool
- the governance wallet no longer holds spare `WETH` because it was used to seed the pool
- the repo now includes a first-party browser portal in `web/` for direct pool trading on Base Sepolia
- the repo now includes a live public `DRW` faucet at `0x3DAa29B6b497a830AA5C3e4eE881ad2fFe2FbAe0`

From there, DARWIN now supports two venue paths:

1. The live first-party artifact-backed reference pool:

```bash
./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --venue darwin_reference_pool
```

For a contract-level quote without broadcasting:

```bash
DARWIN_DEPLOYER_ADDRESS=0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d \
./ops/swap_reference_market.sh --token-in base --amount 1 --dry-run
```

For a browser-wallet path, the Pages deployment publishes the static site from `web/`.
Current public project-site URL:

```text
http://usedarwin.xyz/
```

Recommended next step:

- wait for GitHub Pages certificate issuance, then enforce HTTPS on `usedarwin.xyz`
- keep the spare `usedarwin.*` domains as redirects to the canonical host

When the certificate is ready:

```bash
./ops/enforce_pages_https.sh usedarwin.xyz
```

One-command GitHub-side setup:

```bash
./ops/configure_pages_domain.sh example.com
```

2. A tracked third-party venue, only if its preflight passes on `84532`:

```bash
./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --venue uniswap_v4
```

Current market blockers are now:

- no third-party Base Sepolia venue is tracked yet
- the live pool activity is still DARWIN-controlled demo flow, not independent market activity

See [docs/MARKET_BOOTSTRAP.md](docs/MARKET_BOOTSTRAP.md) for the full runbook and risk framing.

## Status

| Component | State |
|---|---|
| Simulator | Working. `46/46` Python checks pass locally. |
| Contracts | `106` checks pass locally (`79` unit + `18` fuzz + `9` invariants). |
| Overlay | 7 services run locally. Gateway admits real PQ-signed intents. |
| Watcher replay | Works. Independent score reconstruction matches. |
| Base Sepolia core | Deployed. Artifact published. |
| DRW token | Live on Base Sepolia. Token + staking deployed; `status-check` now verifies live holder balances against the pinned allocation table. |
| Reference market | Local DRW + reference-pool smoke deploy passes; live Base Sepolia pool is seeded at `0x9E1fb3eb0Ca3b06038d2A4d6b6e5D18183E6B891`, has seen initial DARWIN-controlled demo trades, and now has a first-party browser portal in `web/`. |
| DRW faucet | Live on Base Sepolia at `0x3DAa29B6b497a830AA5C3e4eE881ad2fFe2FbAe0`; funded with `100,000 DRW` + `0.0002 ETH`, and exposed through the portal claim UI. |
| Audit | Not started. |
| Canary | Not yet operated by genuine outside watchers. |

## What Remains

Real blockers now:

1. first outside watcher operator
2. first outside archive epoch through the live canary
3. external security review / audit
4. legal/compliance structure before any real public token distribution
5. real outside wallets claiming from the public Base Sepolia faucet and using the live pool

If a public testnet market is desired before that, the exact market work left is:

1. point outside users at the seeded Base Sepolia reference pool and Pages portal
2. point outside users at the live Base Sepolia faucet
3. get real third-party swaps against the seeded pool
4. wait for third-party liquidity instead of project-controlled flow

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
