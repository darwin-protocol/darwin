# Arbitrum Sepolia

DARWIN can run on Arbitrum Sepolia as a separate deployment lane from Base
Sepolia.

## Local-Only Env

Create a private operator env from the existing recovery wallets:

```bash
./ops/prepare_arbitrum_sepolia_env.sh
```

That writes a local-only file at `~/.config/darwin/arbitrum-sepolia.env`.

## Preflight

```bash
./ops/preflight_arbitrum_sepolia.sh
```

The preflight checks:

- Arbitrum Sepolia RPC connectivity
- chain id `421614`
- deployer identity
- deployer Arbitrum Sepolia ETH balance
- Sepolia ETH balance, so the report can tell you whether a bridge top-up is
  possible

## Deploy

```bash
./ops/deploy_arbitrum_sepolia.sh
```

The first Arbitrum Sepolia DARWIN core deployment defaults to
`DARWIN_DEPLOY_BOND_ASSET_MOCK=1`, so it does not require a pre-existing bond
asset on that chain.

Expected artifact:

- `ops/deployments/arbitrum-sepolia.json`

The deploy wrapper immediately splits private operator fields back into the
local overlay path:

- `~/.config/darwin/deployments/arbitrum-sepolia.private.json`

## Run The Node

```bash
./ops/run_arbitrum_sepolia_node.sh
```

That starts the generic DARWIN overlay node against the Arbitrum Sepolia
deployment artifact.

The Arbitrum lane defaults to its own overlay ports so it can run in parallel
with the Base recovery node:

- `9543-9549`

## Bootstrap DRW

Once the core Arbitrum Sepolia lane exists and the deployer has gas, you can
bootstrap the DRW market surface end to end:

```bash
./ops/bootstrap_arbitrum_sepolia_drw.sh
```

That flow:

- deploys DRW genesis
- mints mock quote liquidity into the Arbitrum mock bond asset
- deploys and seeds the reference market
- deploys and funds the DRW faucet
- builds a Merkle claim manifest
- deploys vNext governance and promotes the mutable DRW surface to the timelock

## Live State

The repo now supports a full Arbitrum Sepolia DARWIN lane:

- core deployment artifact: `ops/deployments/arbitrum-sepolia.json`
- detached overlay node: `./ops/run_arbitrum_sepolia_node.sh`
- DRW market bootstrap: `./ops/bootstrap_arbitrum_sepolia_drw.sh`
- public portal config: `web/public/market-config-arbitrum-sepolia.json`

The public portal stays Base-first by default, but the Arbitrum lane is exposed
through the same pages with `?lane=arbitrum-sepolia`, for example:

- `https://usedarwin.xyz/trade/?preset=tiny-sell&lane=arbitrum-sepolia`
- `https://usedarwin.xyz/activity/?lane=arbitrum-sepolia`
- `https://usedarwin.xyz/epoch/?lane=arbitrum-sepolia`
