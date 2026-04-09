# DARWIN Node

DARWIN's fundamental operator surface is the overlay node, not the website. The
overlay node is the seven-service runtime that accepts intents, routes them,
scores epochs, publishes archive artifacts, replays watcher proofs, and tracks
finalization/safe-mode state.

## Services

- `gateway` on `9443`
- `router` on `9444`
- `scorer` on `9445`
- `watcher` on `9446`
- `archive` on `9447`
- `finalizer` on `9448`
- `sentinel` on `9449`

## Start The Node

For the current live recovery deployment:

```bash
cd /path/to/darwin
DARWIN_DEPLOYMENT_FILE=ops/deployments/base-sepolia-recovery.json \
DARWIN_RPC_URL=https://sepolia.base.org \
./ops/run_darwin_node.sh
```

The runner writes:

- logs under `ops/state/<network>-node/logs/`
- readiness and status reports under `ops/state/<network>-node/reports/`
- a pid file at `ops/state/<network>-node/darwin-node.pid`

## Fleet View

The next Darwin step is not another one-off lane. It is operating the overlay as
a small fleet.

Export one multi-lane snapshot for Base recovery, the proving canary, and
Arbitrum:

```bash
cd /path/to/darwin
./ops/check_darwin_fleet.sh
```

That wrapper writes `ops/state/darwin-fleet-status.json` and prints a concise
operator summary. The public publish flow also exports an aggregate-only copy at
`web/public/node-fleet.json`.

Lane states intentionally distinguish:

- `Live` — services are healthy and watcher readiness is green
- `Warming` — services are healthy but watcher replay is not ready yet
- `Staged` — deployment artifacts and reports exist, but the lane is not the live local overlay right now
- `Degraded` — the lane matched a live local overlay, but one or more services failed health

The public website only receives aggregate availability counts. Detailed lane
state stays in local operator artifacts under `ops/state/`.

## Network Exposure

- The overlay now binds to `127.0.0.1` by default via `DARWIN_BIND_HOST`.
- If you intentionally expose it off-host, set both:
  - `DARWIN_BIND_HOST=<public-or-lan-ip>`
  - `DARWIN_ADMIN_TOKEN=<long-random-secret>`
- Mutating overlay endpoints use that admin token via `Authorization: Bearer ...` or `X-Darwin-Token`.
- The admin-surface services (`router`, `scorer`, `watcher`, `archive`, `finalizer`, `sentinel`) now refuse non-loopback startup unless `DARWIN_ADMIN_TOKEN` is set.
- `run_darwin_node.sh` also blocks whole-node off-host startup without that token.
- Operator scripts such as `ops/publish_canary_epoch.sh` forward the token automatically when `DARWIN_ADMIN_TOKEN` is exported.

For containerized local devnet runs, `ops/docker-compose.devnet.yml` binds published ports to host loopback and uses a fixed local token:

```bash
export DARWIN_ADMIN_TOKEN=darwin-devnet-admin-token
docker compose -f ops/docker-compose.devnet.yml up
```

## Smoke An Intent Path

After the node is up, run one signed intent through gateway admission and router
selection:

```bash
cd /path/to/darwin
./ops/smoke_intent_path.sh
```

That script:

- creates or reuses a local demo wallet
- signs a fresh intent with a unique nonce
- submits it to `gateway`
- routes it through `router`
- writes JSON artifacts under `ops/state/<network>/reports/`

If `DARWIN_ADMIN_TOKEN` is exported, the script forwards it automatically for
the router POST.

## Preflight Only

```bash
cd /path/to/darwin
./.venv/bin/python ops/preflight_darwin_node.py \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --rpc-url https://sepolia.base.org \
  --json-out ops/state/base-sepolia-recovery-node/reports/node-preflight.json \
  --markdown-out ops/state/base-sepolia-recovery-node/reports/node-preflight.md
```

## Status Check

```bash
cd /path/to/darwin
PYTHONPATH="$PWD:$PWD/sim" ./.venv/bin/python -m darwin_sim.cli.darwinctl status-check \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --rpc-url https://sepolia.base.org
```

## Seed A Watcher Replay

If you already have a publishable epoch artifact directory, seed the watcher on
boot:

```bash
DARWIN_NODE_SEED_DIR=/abs/path/to/epoch-artifacts \
DARWIN_NODE_SEED_EPOCH_ID=epoch-1 \
./ops/run_darwin_node.sh
```

Without a seed, the node can still boot in cold-watcher mode and become fully
ready after the first archive replay.

## Arbitrum Path

The generic node runner can target Arbitrum once a DARWIN deployment artifact
exists for that chain.

Arbitrum Sepolia example:

```bash
DARWIN_DEPLOYMENT_FILE=ops/deployments/arbitrum-sepolia.json \
DARWIN_RPC_URL=https://sepolia-rollup.arbitrum.io/rpc \
./ops/run_darwin_node.sh
```

Arbitrum One operator example, using the local Nitro node as transport:

```bash
DARWIN_DEPLOYMENT_FILE=ops/deployments/arbitrum.json \
DARWIN_RPC_URL=http://127.0.0.1:8547 \
./ops/run_darwin_node.sh
```

The runner pins the gateway to the deployment artifact's `chain_id` and
`settlement_hub`, so the RPC transport and the DARWIN artifact must match.

If `DARWIN_FINALIZER_PRIVATE_KEY` is set together with `DARWIN_RPC_URL` and a
deployment artifact that includes `epoch_manager`, the finalizer can submit
`finalizeEpoch(uint64)` on-chain instead of only recording local finalization
state.

If `DARWIN_EPOCH_OPERATOR_PRIVATE_KEY` is also set, the same finalizer can:

- close a registered on-chain epoch when `manifest_root` is provided
- post `score_root`, `weight_root`, and `rebalance_root` before finalization
- fail closed on on-chain root mismatches instead of silently finalizing local-only state

That makes the node capable of driving the close -> post roots -> finalize loop
for epochs that are already opened on-chain.

## Reward Manifests

The proof-based reward path now has two layers:

- a published reward manifest in `ops/state/<network>-epoch-rewards.json`
- an optional live site copy at `web/public/reward-claims*.json`

Build a fresh epoch reward manifest from the outside-activity snapshot:

```bash
cd /path/to/darwin
./ops/build_epoch_reward_distribution.sh
```

If an epoch distributor is live, configure it on-chain:

```bash
cd /path/to/darwin
export DARWIN_EPOCH_REWARD_DISTRIBUTOR=0x...
export DARWIN_EPOCH_REWARD_GOVERNANCE_PRIVATE_KEY=0x...
./ops/configure_drw_epoch_distribution.sh
```

For an Arbitrum Sepolia-specific deploy and node wrapper, see
[ARBITRUM_SEPOLIA.md](ARBITRUM_SEPOLIA.md).
