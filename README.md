# DARWIN

A peer-to-peer system for evolving exchange microstructure.

## Abstract

Current decentralized exchanges hard-code one market design and ask all participants to accept its trade-offs permanently. DARWIN replaces this with bounded competition: multiple execution mechanisms run simultaneously, a scoring system measures their real outcomes against a control baseline, and flow shifts toward whichever mechanism actually works best. Governance sets boundaries. The protocol adapts within them.

The core idea is selection pressure applied to market structure, not governance votes about fee parameters.

## Running

```bash
cd sim && python -m venv .venv && source .venv/bin/activate
pip install pyyaml numpy pandas pyarrow zstandard dilithium-py
python -m pytest tests/ -v                                    # 33 tests
python -m darwin_sim.experiments.suite configs/baseline.yaml   # E1-E7
```

```bash
cd contracts && forge test                                     # 93 checks
```

```bash
python overlay/devnet.py                                       # 7 services
```

## Design

Intents are signed with both a post-quantum key (ML-DSA-65) and a classical EVM key, cryptographically bound. The PQ signature is verified by the overlay services. The EVM signature is verified on-chain. v2 drops the EVM leg.

Species are parameterized execution modules — batch auctions, RFQ solvers, adaptive curves. Each competes for order flow within the same pair. A control reservation (15% of flow) always goes to the baseline species so that scoring is counterfactual, not self-referential.

Fitness is measured as causal uplift: trader surplus, LP health, fill rate, and adverse selection, each compared to what the baseline would have produced on the same flow. Scores are published as Merkle roots. Watchers independently reconstruct them and challenge mismatches.

Settlement is on an EVM L2. The protocol does not run its own chain in v1.

## DRW

DRW is protocol stake. 1B fixed supply, minted once at genesis after activation gates pass. Not a currency.

Allocation: treasury 20%, insurance 20%, sponsor rewards 10%, staking 30%, community 20%.

Current supply: zero. The contracts exist but genesis has not been executed. Bonds in the current alpha are WETH.

## Status

| Component | State |
|---|---|
| Simulator | Working. 7 experiments pass on 50K swaps. |
| Contracts | 9 contracts deployed on Base Sepolia. 93 test checks passing. Not audited. |
| Overlay | 7 services run locally. Gateway admits real PQ-signed intents. |
| Watcher replay | Works. Independent score reconstruction matches. |
| DRW token | Contract written and tested. Not minted. |
| Audit | Not started. |
| Canary | Not started. |

## What remains

1. External watcher operators independently replay epochs.
2. Security audit of all contracts.
3. 90-day canary with real flow.
4. Legal entity.
5. DRW genesis after all gates pass.
6. Sovereign rollup (v1.5) and native PQ chain (v2) later.

## Repository

```
spec/        Protocol design
sim/         Simulator, SDK, CLI
contracts/   Solidity (Foundry)
overlay/     Gateway, router, scorer, watcher, archive, finalizer, sentinel
ops/         Deployment scripts and artifacts
docs/        Operator and security documentation
```

## License

MIT
