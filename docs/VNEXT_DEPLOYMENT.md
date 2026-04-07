# vNext Deployment

This is the first deployable vNext governance path:

- `DarwinTimelock`
- `DRWMerkleDistributor`

It intentionally writes a **public-safe sidecar artifact** instead of mutating the tracked main deployment artifact.

## Inputs

Prepare a JSON claim list:

```json
[
  {"account": "0x1111111111111111111111111111111111111111", "amount": "100000000000000000000"},
  {"account": "0x2222222222222222222222222222222222222222", "amount": "200000000000000000000"}
]
```

Build the Merkle manifest:

```bash
python3 ops/build_drw_merkle_distribution.py \
  --claims-file ops/state/base-sepolia-claims.json \
  --out ops/state/base-sepolia-drw-merkle.json \
  --network base-sepolia \
  --claim-deadline 1777777777
```

CSV exports are also supported for spreadsheet-driven claim prep:

```bash
python3 ops/build_drw_merkle_distribution.py \
  --claims-file ops/state/base-sepolia-claims.csv \
  --out ops/state/base-sepolia-drw-merkle.json \
  --claim-deadline 1777777777
```

The output manifest contains:

- `merkle_root`
- `claims_count`
- `total_amount`
- per-claim proofs

## Preflight

Set the constitutional operators locally:

```bash
export DARWIN_VNEXT_COUNCIL="0x..."
export DARWIN_VNEXT_GUARDIAN="0x..."
export DARWIN_VNEXT_CLAIM_DEADLINE="1777777777"
export DARWIN_VNEXT_DISTRIBUTION_FILE="ops/state/base-sepolia-drw-merkle.json"
```

Then run:

```bash
./ops/preflight_vnext_governance.sh
```

## Deploy

When preflight reports `ready_to_deploy: yes`, run:

```bash
./ops/deploy_vnext_governance.sh
```

That writes:

```text
ops/deployments/<network>.vnext.json
```

The sidecar artifact is public-safe and includes:

- deployed timelock address
- deployed distributor address
- timelock delay/grace configuration
- token address
- claim deadline
- Merkle root
- claim count and total amount

It does **not** publish local operator-only wallet metadata.

## Promote Mutable DRW Governance

After deployment, build the timelock promotion batch:

```bash
./ops/preflight_vnext_promotion.sh
./ops/build_vnext_promotion_batch.sh
```

See [`docs/VNEXT_PROMOTION.md`](./VNEXT_PROMOTION.md) for the full handoff path.

## Current Boundary

This deploy path is the first operational vNext layer. It does not yet replace the immutable-governance alpha core.

That means:

- mutable future distribution can be timelocked
- future claims can be rule-based instead of wallet-led
- the existing alpha core still requires a future core version for fully rotatable governance
