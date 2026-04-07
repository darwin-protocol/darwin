# DARWIN

DARWIN is a peer-to-peer market experiment built around live testnet infrastructure on Base Sepolia.

## Public Surface

- Site: `https://usedarwin.xyz/`
- Epoch: `https://usedarwin.xyz/epoch/`
- Market: `https://usedarwin.xyz/trade/`
- Activity: `https://usedarwin.xyz/activity/`
- Community share bundle: `https://usedarwin.xyz/community-share.json`
- Public status: [LIVE_STATUS.md](LIVE_STATUS.md)
- Market runbook: [docs/MARKET_BOOTSTRAP.md](docs/MARKET_BOOTSTRAP.md)
- Community bootstrap: [docs/COMMUNITY_BOOTSTRAP.md](docs/COMMUNITY_BOOTSTRAP.md)
- Darwin node: [docs/DARWIN_NODE.md](docs/DARWIN_NODE.md)
- Arbitrum Sepolia lane: [docs/ARBITRUM_SEPOLIA.md](docs/ARBITRUM_SEPOLIA.md)
- Security reporting: [docs/SECURITY.md](docs/SECURITY.md)
- Recovery runbook: [docs/GOVERNANCE_RECOVERY.md](docs/GOVERNANCE_RECOVERY.md)
- vNext governance: [docs/VNEXT_GOVERNANCE.md](docs/VNEXT_GOVERNANCE.md)
- vNext deployment: [docs/VNEXT_DEPLOYMENT.md](docs/VNEXT_DEPLOYMENT.md)
- vNext promotion: [docs/VNEXT_PROMOTION.md](docs/VNEXT_PROMOTION.md)

## What Is Live

- `DRW` token on Base Sepolia
- Public `DRW` faucet
- Public `DRW / WETH` reference pool
- Public browser trade portal
- Public activity feed
- Public epoch landing page

## Public Notes

- DARWIN is currently public testnet alpha infrastructure.
- The current public market is on Base Sepolia, not mainnet.
- Use small amounts and expect testnet conditions.
- Operators can locally re-audit live privileged roles with `darwinctl role-audit --deployment-file ops/deployments/base-sepolia-recovery.json`.
- Operators can bootstrap fresh local recovery wallets with `./ops/init_recovery_wallets.sh`.
- Operators can derive a local-only recovery env with `./ops/prepare_recovery_env.sh` and preflight it with `./ops/preflight_recovery_redeploy.sh`.
- Shared deployment artifacts are kept public-safe; local operator roles and deployer identity live in `~/.config/darwin/deployments/`.
- Operators can build a local activity allowlist with `python3 ops/build_project_wallet_allowlist.py` before running `ops/report_external_activity.py`.
- The public site now exposes a public-safe outside-activity snapshot while keeping the operator allowlist and full classification local.
- The vNext promotion path now supports both Safe batch export and direct EOA execution for mutable DRW-era handoff.
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
