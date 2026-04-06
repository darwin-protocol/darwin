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
- The current governance wallet has `DRW` and Base Sepolia ETH, but the latest preflight shows `0 WETH`, so ETH must be wrapped first.
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

If the quote token is `WETH` and the wallet only has native ETH, wrap ETH first.

On the current live wallet, that is the immediate blocker:

- gas is present
- `DRW` is present
- `WETH` is not

## Demo Market Path

1. Start with Base Sepolia, not mainnet.
2. Seed a small `DRW/WETH` pool.
3. Publish the pool address and exact network.
4. Tell users it is a testnet market.
5. Wait for third-party swaps and liquidity, not just project-controlled flow.

If your chosen interface does not support Base Sepolia, treat the market bootstrap as a separate venue-selection task rather than pretending the pool path is already solved.

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
