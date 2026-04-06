# DARWIN Market Bootstrap

This is the honest path for putting `DRW` in front of users without faking market activity.

## What To Avoid

- Do not self-swap for optics.
- Do not claim price discovery from project-controlled volume.
- Do not imply that a thin testnet pool is a real market.

## Current Reality

- `DRW` token + staking are live on Base Sepolia.
- The canary still uses Base Sepolia `WETH9` as its bond asset.
- The simplest demo market is `DRW/WETH`.
- DARWIN now ships a first-party `ReferenceMarketPool` deployment path for Base Sepolia and local smoke tests.
- The live reference pool is `0x9E1fb3eb0Ca3b06038d2A4d6b6e5D18183E6B891`.
- The live seeded reserves are `1000 DRW` and `0.0005 WETH`.
- Uniswap Labs' interface currently lists `Sepolia` and `Unichain` as supported testnets, not `Base Sepolia`, so venue support must be confirmed before assuming a UI-driven testnet pool path.

## Preflight

Run:

```bash
./.venv/bin/python ops/preflight_market_bootstrap.py \
  --deployment-file ops/deployments/base-sepolia.json \
  --wallet-address 0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d \
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
  --deployment-file ops/deployments/base-sepolia.json \
  --venue uniswap_v4 \
  --json-out ops/state/market-bootstrap/venue.json \
  --markdown-out ops/state/market-bootstrap/venue.md
```

On the current live artifact, the market path is already active:

- the artifact includes a seeded `market` section
- the reference pool is deployed and funded
- venue preflight for `darwin_reference_pool` should now pass
- the governance wallet no longer holds spare `WETH` because it was used to seed the pool

That wrap helper auto-loads `.env.base-sepolia`, uses the pinned deployment artifact bond asset as the WETH address, and can run in `--dry-run` mode if you only want the exact calldata / readiness output first.

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
  --deployment-file ops/deployments/base-sepolia.json \
  --venue darwin_reference_pool \
  --json-out ops/state/market-bootstrap/reference-venue.json \
  --markdown-out ops/state/market-bootstrap/reference-venue.md
```

Those example amounts are `1000 DRW` and `0.0005 WETH`. That is the current live Base Sepolia seed.

To quote a contract-level swap against the live pool without broadcasting:

```bash
DARWIN_DEPLOYER_ADDRESS=0xC50f7A6ddDBBfe85af8b47B9bDf1A6B525746A9d \
./ops/swap_reference_market.sh --token-in base --amount 1 --dry-run
```

That helper reads the seeded market from the artifact, calls `quoteExactInput`, and prints the slippage-guarded minimum output. A live swap uses the same command without `--dry-run`, but it requires `DARWIN_DEPLOYER_PRIVATE_KEY` and should only be used for genuine testnet trading, not self-generated optics.

## Demo Market Path

1. Start with Base Sepolia, not mainnet.
2. Prefer the seeded DARWIN reference pool on Base Sepolia unless a third-party venue is explicitly tracked for `84532`.
3. Run a venue preflight against the exact deployment network.
4. Publish the pool address and exact network.
5. Tell users it is a testnet market.
6. Wait for third-party swaps and liquidity, not just project-controlled flow.

Current DARWIN-tracked venue state:

- `darwin_reference_pool` is tracked from the pinned deployment artifact itself
- the current public Base Sepolia artifact now has that pool deployed and seeded
- `uniswap_v4` is tracked from the current Uniswap deployment docs
- Base mainnet (`8453`) is listed there
- Base Sepolia (`84532`) is not listed there

So the current viable Base Sepolia path is:

1. use the seeded DARWIN reference pool
2. rerun the artifact-backed venue preflight
3. point third parties at the pool and wait for real usage

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
