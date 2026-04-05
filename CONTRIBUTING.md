# Contributing to DARWIN

## Where to Start

1. Read `docs/OPERATOR_QUICKSTART.md`
2. Run the test suite: `cd sim && python -m pytest tests/ -v`
3. Run the contract tests: `cd contracts && forge test -vv`
4. Run the devnet: `python overlay/devnet.py`

## Code Style

- Python: ruff, line length 120, Python 3.12+
- Solidity: 0.8.24, optimizer enabled

## Pull Requests

- One concern per PR
- Tests must pass
- Contract changes require test coverage for all state transitions
- Overlay service changes require devnet integration test

## What We Need

Priority contributions (in order):

1. **Watcher improvements** — more granular replay checks, better error reporting
2. **Real PQ crypto integration** — replace HMAC stand-ins with liboqs ML-DSA-65
3. **Contract fuzzing** — Foundry fuzz tests for invariants
4. **Data adapters** — real Uniswap V3 subgraph / RPC adapter
5. **Documentation** — operator runbooks, API docs

## What We Don't Need Yet

- Chain client forks (v1 is an overlay)
- DRW token contracts (activation gates not passed)
- Marketing materials
- Governance UI
