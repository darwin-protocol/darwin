# DARWIN Market Bootstrap

This is the honest path for putting `DRW` in front of users without faking market activity.

## What To Avoid

- Do not self-swap for optics.
- Do not claim price discovery from project-controlled volume.
- Do not imply that a thin testnet pool is a real market.
- Do not scatter the same DRW lane across multiple equivalent pools before real traction exists.

## Pool Taxonomy

For each Darwin lane, the right structure is:

- `Canonical`
  - one live public pool
  - default route for first claims, tiny swaps, and public proof
- `Experimental`
  - reserved for future alternate quote assets or descendant Darwin experiments
  - not live until the canonical route has traction
- `Incentivized`
  - reserved for later rewards once outside demand is real
  - not live until the canonical route has traction

Current public unlock target for non-canonical routes:

- `25` outside wallets
- `40` outside swaps

Until that threshold is reached, the site should keep routing everyone to the canonical pool.

## Current Reality

- `DRW` token + staking are live on Base Sepolia.
- The canary still uses Base Sepolia `WETH9` as its bond asset.
- The simplest demo market is `DRW/WETH`.
- DARWIN now ships a first-party `ReferenceMarketPool` deployment path for Base Sepolia and local smoke tests.
- The current public recovery pool is seeded at `1000 DRW` and `0.0005 WETH`.
- A first-party Next.js portal now exists in `web/` for direct wallet-driven pool trading.
- A first-party faucet contract + portal claim path now exists for transparent third-party DRW distribution.
- Current live faucet funding is `100,000 DRW` + `0.0004 ETH`.
- Uniswap Labs' interface currently lists `Sepolia` and `Unichain` as supported testnets, not `Base Sepolia`, so venue support must be confirmed before assuming a UI-driven testnet pool path.

## Preflight

Run:

```bash
./.venv/bin/python ops/preflight_market_bootstrap.py \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --wallet-address <wallet-address> \
  --json-out ops/state/market-bootstrap/preflight.json \
  --markdown-out ops/state/market-bootstrap/preflight.md
```

This checks:

- Base Sepolia RPC / chain ID
- gas balance
- live `DRW` balance
- live quote-token balance
- recommended pair from the pinned deployment

If the quote token is `WETH` and the wallet only has native ETH, wrap ETH first:

```bash
./ops/wrap_base_sepolia_weth.sh --amount-eth 0.0005
```

Then confirm that your chosen venue is actually tracked for the deployment network:

```bash
./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --venue uniswap_v4 \
  --json-out ops/state/market-bootstrap/venue.json \
  --markdown-out ops/state/market-bootstrap/venue.md
```

On the current live artifact, the market path is already active:

- the artifact includes a seeded `market` section
- the reference pool is deployed and funded
- venue preflight for `darwin_reference_pool` should now pass
- the governance wallet no longer holds spare `WETH` because it was used to seed the pool

That wrap helper auto-loads `~/.config/darwin/base-sepolia.env` unless `DARWIN_ENV_FILE` is set, uses the pinned deployment artifact bond asset as the WETH address, and can run in `--dry-run` mode if you only want the exact calldata / readiness output first.

## Recommended Base Sepolia Path

If you want a DARWIN-owned testnet venue on Base Sepolia today, use the artifact-backed reference pool instead of waiting on third-party venue support.

Deploy the reference pool:

```bash
./ops/init_reference_market.sh
```

Seed it with small testnet amounts:

```bash
export DARWIN_REFERENCE_MARKET_BASE_AMOUNT=1000000000000000000000
export DARWIN_REFERENCE_MARKET_QUOTE_AMOUNT=500000000000000
./ops/seed_reference_market.sh
```

Then verify the artifact-backed venue path:

```bash
./.venv/bin/python ops/preflight_market_venue.py \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --venue darwin_reference_pool \
  --json-out ops/state/market-bootstrap/reference-venue.json \
  --markdown-out ops/state/market-bootstrap/reference-venue.md
```

Those example amounts are `1000 DRW` and `0.0005 WETH`. That is the current live Base Sepolia seed.

To quote a contract-level swap against the live pool without broadcasting:

```bash
DARWIN_DEPLOYER_ADDRESS=<wallet-address> \
./ops/swap_reference_market.sh --token-in base --amount 1 --dry-run
```

That helper reads the seeded market from the artifact, calls `quoteExactInput`, and prints the slippage-guarded minimum output. A live swap uses the same command without `--dry-run`, but it requires `DARWIN_DEPLOYER_PRIVATE_KEY` and should only be used for genuine testnet trading, not self-generated optics.

## Browser Portal

The repo now ships a static market portal in `web/` that connects directly to the live Base Sepolia reference pool.

- source: `web/`
- config: `web/public/market-config.json`
- exporter: `ops/export_market_portal_config.py`
- public site: `https://usedarwin.xyz/`

The portal supports:

- wallet connect
- Base Sepolia network switch/add
- DRW wallet import
- optional DRW faucet claim when the pinned artifact enables a funded faucet
- live reserve reads
- direct `WETH -> DRW` and `DRW -> WETH` swaps
- direct `ETH -> WETH` wrapping for the quote side
- tiny-swap presets and shareable `?preset=` links for community onboarding
- a `Smart start` button that tries an atomic claim-plus-tiny-sell batch on supporting wallets
- public `/activity` view for recent DARWIN onchain events
- public pool-role cards showing `Canonical`, `Experimental`, and `Incentivized`

## Tiny Swap Path

The best public first action is a tiny swap, not a project-controlled large trade.

Recommended first path for outside users:

1. connect a Base Sepolia wallet
2. claim `100 DRW` from the faucet
3. use the `tiny sell 10 DRW` preset in the portal

If the wallet supports `wallet_sendCalls`, the trade page can also attempt `Smart start`, which batches:

1. `claim()`
2. `approve()`
3. `swapExactInput()`

Shareable community link:

```text
https://usedarwin.xyz/trade/?preset=tiny-sell
```

That path works better than `tiny buy` because faucet claimants already receive DRW and a small native gas drip. `tiny buy` is still available for users who already hold extra Base Sepolia ETH and want to wrap a minimal amount into WETH.

## Activity Tracking

Public community surface:

- `https://usedarwin.xyz/activity/`

That page shows recent DARWIN-related Base Sepolia events:

- reference-pool swaps
- faucet claims
- Merkle distributor claims

Operator-side external tracking should stay local, not public. Use:

```bash
python3 ops/build_project_wallet_allowlist.py
./.venv/bin/python ops/report_external_activity.py \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --json-out ops/state/activity/external-activity.json \
  --markdown-out ops/state/activity/external-activity.md
```

The allowlist generator builds the local project-wallet classification from gitignored wallet bundles
and local deployment overlays. The allowlist itself lives outside the repo in:

```text
~/.config/darwin/project-wallets.json
```

That file should remain local-only.

## Transparent Distribution

The right way to get outside wallets into the system is distribution, not project-controlled volume.

The repo now includes:

- `contracts/src/DRWFaucet.sol`
- `contracts/script/DeployDRWFaucet.s.sol`
- `ops/init_drw_faucet.sh`
- `ops/fund_drw_faucet.sh`

Suggested Base Sepolia defaults:

- claim amount: `100 DRW`
- native drip: `0.00001 ETH`
- cooldown: `86400` seconds
- initial funding: `100000 DRW` + `0.0002 ETH`

Current live Base Sepolia faucet defaults:

- claim amount: `100 DRW`
- native drip: `0.00001 ETH`
- cooldown: `86400` seconds
- initial funding: `100000 DRW` + `0.0004 ETH`

Redeploy path once a signer is loaded locally:

```bash
./ops/init_drw_faucet.sh
python -m darwin_sim.cli.darwinctl deployment-show --deployment-file ops/deployments/base-sepolia-recovery.json
python ops/export_market_portal_config.py --deployment-file ops/deployments/base-sepolia-recovery.json --out web/public/market-config.json
```

If the token holder differs from the deployer, set a separate funder key locally before running the faucet init:

```bash
export DARWIN_DRW_FAUCET_FUNDER_PRIVATE_KEY="0x..."
```

## Initial Claim Activity

The current public recovery stack has already processed first-party claimant tests through the live Merkle distributor. Those claims prove the vNext promotion and claim path are working end to end. They do not count as third-party adoption.

## Demo Market Path

1. Start with Base Sepolia, not mainnet.
2. Prefer the seeded DARWIN reference pool on Base Sepolia unless a third-party venue is explicitly tracked for `84532`.
3. Run a venue preflight against the exact deployment network.
4. Publish the pool address, faucet address, and exact network.
5. Tell users it is a testnet market.
6. Wait for third-party swaps and liquidity, not just project-controlled flow.

Current DARWIN-tracked venue state:

- `darwin_reference_pool` is tracked from the pinned deployment artifact itself
- the current public Base Sepolia artifact now has that pool deployed and seeded
- the current public Base Sepolia artifact is now backed by successful DARWIN-controlled demo trades
- the repo now includes a browser portal for the same pool
- `uniswap_v4` is tracked from the current Uniswap deployment docs
- Base mainnet (`8453`) is listed there
- Base Sepolia (`84532`) is not listed there

So the current viable Base Sepolia path is:

1. use the seeded DARWIN reference pool
2. use the live transparent DRW faucet
3. rerun the artifact-backed venue preflight
4. point third parties at the pool, faucet, and browser portal
5. wait for real usage

Third-party Base Sepolia venue support remains optional and unconfirmed in the tracked registry.

## Why This Matters

Permissionless listing is easy. Credible market evidence is not.

The right claim is:

- `DRW is live on Base Sepolia`
- `A testnet pool exists`
- `Third parties can swap it`

The wrong claim is:

- `we created demand by swapping ourselves`

## After A Testnet Pool Exists

- capture the pool address in the repo
- add a simple swap/liquidity runbook
- track third-party activity separately from project-controlled actions
- decide whether a real market bootstrap is worth doing on Base mainnet
