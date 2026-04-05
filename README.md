# DARWIN

**An Evolutionary Intent-Centric Exchange Protocol with Post-Quantum Hardened Trust**

DARWIN is a decentralized exchange protocol where multiple bounded market mechanisms — called *species* — compete for order flow, are measured on trader and LP outcomes, and receive more or less flow based on observed fitness. The protocol evolves market structure instead of assuming one AMM design is always best.

## Repository Structure

```
darwin/
  spec/             Frozen protocol specs, schemas, test vectors
  sim/              Simulator — proves the evolutionary thesis
  sdk/python/       Python SDK (accounts, dual-envelope intents)
  cli/              darwinctl operator CLI
  overlay/          Overlay services (gateway, watcher, archive, ...)
  contracts/        Solidity settlement contracts
  ops/              Deployment configs, docker-compose, manifests
  docs/             Operator manual, runbooks
```

## Status

| Component | Status |
|---|---|
| Simulator (3 species, E1-E7 suite) | Working |
| SDK (PQ + EVM dual-envelope) | Working |
| darwinctl CLI | Working |
| Gateway service | Working |
| Watcher replay verifier | Working |
| Solidity contracts (7) | Written, untested |
| Watcher service | Next |
| Archive / Finalizer services | Planned |

## Quick Start

```bash
cd sim
python -m venv .venv && source .venv/bin/activate
pip install pyyaml numpy pandas pyarrow zstandard
python -m darwin_sim.experiments.suite configs/baseline.yaml
```

## Trust Model

v1 is a **PQ-hardened intent layer on classical EVM settlement**. Not a sovereign chain. Not fully post-quantum. The honest label:

> Post-quantum hardened under current assumptions.

See `spec/` for the full versioned trust model (v1 overlay → v1.5 sovereign rollup → v2 native PQ chain).

## License

MIT
