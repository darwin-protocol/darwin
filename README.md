# DARWIN

A peer-to-peer system for evolving exchange microstructure.

## Start Here

- Current project status: [LIVE_STATUS.md](/path/to/darwin/LIVE_STATUS.md)
- Public Base Sepolia artifact: [ops/deployments/base-sepolia.json](/path/to/darwin/ops/deployments/base-sepolia.json)
- Operator flow: [docs/OPERATOR_QUICKSTART.md](/path/to/darwin/docs/OPERATOR_QUICKSTART.md)
- Security posture: [docs/SECURITY.md](/path/to/darwin/docs/SECURITY.md)

## Status At A Glance

- The repo is reproducible locally.
- The public canary exists on Base Sepolia.
- The public canary is still `WETH`-bond, not `DRW`-bond.
- The DRW genesis path is implemented and verified locally.
- The next live on-chain step is the Base Sepolia DRW genesis broadcast.

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
- public DRW supply: zero
- DRW contracts exist and test pass
- DRW genesis deploy path exists but has not been broadcast publicly yet

The repo now includes:

- `contracts/src/DRWToken.sol`
- `contracts/src/DRWStaking.sol`
- `contracts/script/DeployDRWGenesis.s.sol`
- `ops/preflight_drw_genesis.sh`
- `ops/init_drw_genesis.sh`

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

./ops/preflight_drw_genesis.sh
./ops/init_drw_genesis.sh
darwinctl deployment-show --deployment-file ops/deployments/base-sepolia.json
```

The Base Sepolia scripts auto-load `.env.base-sepolia` or the file named by `DARWIN_ENV_FILE`.

## Status

| Component | State |
|---|---|
| Simulator | Working. `33/33` Python checks pass locally. |
| Contracts | `93` checks pass locally (`66` unit + `18` fuzz + `9` invariants). |
| Overlay | 7 services run locally. Gateway admits real PQ-signed intents. |
| Watcher replay | Works. Independent score reconstruction matches. |
| Base Sepolia core | Deployed. Artifact published. |
| DRW token | Contracts written and tested. Public genesis not yet broadcast. |
| Audit | Not started. |
| Canary | Not yet operated by genuine outside watchers. |

## What Remains

Immediate next step:

1. load the Base Sepolia signer key into `.env.base-sepolia`
2. run `./ops/preflight_drw_genesis.sh`
3. run `./ops/init_drw_genesis.sh`

Real blockers after that:

1. first outside watcher operator
2. first outside archive epoch through the live canary
3. external security review / audit
4. legal/compliance structure before any real public token distribution

The canonical tracker is [LIVE_STATUS.md](/path/to/darwin/LIVE_STATUS.md).

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
