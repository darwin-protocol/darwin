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
cd /Users/simchagrieve/workspace/darwin
DARWIN_DEPLOYMENT_FILE=ops/deployments/base-sepolia-recovery.json \
DARWIN_RPC_URL=https://sepolia.base.org \
./ops/run_darwin_node.sh
```

The runner writes:

- logs under `ops/state/<network>-node/logs/`
- readiness and status reports under `ops/state/<network>-node/reports/`
- a pid file at `ops/state/<network>-node/darwin-node.pid`

## Preflight Only

```bash
cd /Users/simchagrieve/workspace/darwin
./.venv/bin/python ops/preflight_darwin_node.py \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --rpc-url https://sepolia.base.org \
  --json-out ops/state/base-sepolia-recovery-node/reports/node-preflight.json \
  --markdown-out ops/state/base-sepolia-recovery-node/reports/node-preflight.md
```

## Status Check

```bash
cd /Users/simchagrieve/workspace/darwin
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
