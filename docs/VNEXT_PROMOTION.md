# vNext Promotion

After the first vNext layer is deployed, the mutable DRW-era contracts still need to be promoted to the timelock.

That promotion path now has two operator helpers:

- `./ops/preflight_vnext_promotion.sh`
- `./ops/build_vnext_promotion_batch.sh`

The output batch is designed for a Safe Transaction Builder import.

## What It Promotes

When present in the pinned deployment, the batch includes:

- funding the `DRWMerkleDistributor` with the total Merkle allocation
- `DRWToken.setGovernance(timelock)`
- `DRWStaking.setGovernance(timelock)`
- `DRWFaucet.setGovernance(timelock)`
- `ReferenceMarketPool.setGovernance(timelock)`

Optionally:

- `ReferenceMarketPool.setMarketOperator(newOperator)`

## Inputs

The promotion helpers expect:

- a merged local deployment artifact, including the private overlay with the current governance address
- a deployed vNext sidecar artifact
- a funded governance wallet or Safe that can sign the batch

Optional env:

```bash
export DARWIN_VNEXT_MARKET_OPERATOR="0x..."
export DARWIN_VNEXT_SAFE_ADDRESS="0x..."
export DARWIN_VNEXT_PROMOTION_FILE="ops/state/base-sepolia-vnext-safe-batch.json"
```

## Preflight

```bash
./ops/preflight_vnext_promotion.sh
```

The preflight checks:

- current governance is available locally
- vNext timelock/distributor are deployed
- mutable DRW contracts still point at the current governance
- the current governance holds enough `DRW` to fund the distributor

## Build Batch

```bash
./ops/build_vnext_promotion_batch.sh
```

That writes a Safe-ready batch JSON under:

```text
ops/state/<network>-vnext-safe-batch.json
```

## Current Boundary

This promotion path only covers the mutable DRW-era layer.

It does not fix the immutable-governance alpha core. Those contracts still require a future core version rather than an operational handoff.
