# DARWIN

DARWIN is a peer-to-peer market experiment built around live testnet infrastructure on Base Sepolia.

## Public Surface

- Site: `https://usedarwin.xyz/`
- Market: `https://usedarwin.xyz/trade/`
- Public status: [LIVE_STATUS.md](LIVE_STATUS.md)
- Market runbook: [docs/MARKET_BOOTSTRAP.md](docs/MARKET_BOOTSTRAP.md)
- Security reporting: [docs/SECURITY.md](docs/SECURITY.md)

## What Is Live

- `DRW` token on Base Sepolia
- Public `DRW` faucet
- Public `DRW / WETH` reference pool
- Public browser trade portal

## Public Notes

- DARWIN is currently public testnet alpha infrastructure.
- The current public market is on Base Sepolia, not mainnet.
- Use small amounts and expect testnet conditions.
- Operators can locally re-audit live privileged roles with `darwinctl role-audit --deployment-file ops/deployments/base-sepolia.json`.
- This repository intentionally keeps public-facing documentation lightweight and does not publish private operator workflow detail.

## Repository Layout

```text
web/        Public site and market portal
contracts/  Solidity contracts
sim/        Simulator, SDK, and CLI
overlay/    Overlay services
ops/        Scripts and deployment helpers
docs/       Public documentation
spec/       Protocol design material
```

## Local Development

```bash
./ops/bootstrap_dev.sh
source .venv/bin/activate
cd sim && python -m pytest tests/test_end_to_end.py -v
cd ../contracts && forge test --summary
```

## License

MIT
