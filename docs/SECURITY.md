# Security

## Reporting

If you believe you found a security issue in DARWIN, do not open a public issue with exploit detail.

Use the repository contact path first while a dedicated security mailbox is being finalized.

## Public Status

- DARWIN is public testnet alpha infrastructure.
- The public deployment is on Base Sepolia.
- The system has not undergone a formal external audit.
- Operators can locally verify live privileged-role bindings with `darwinctl role-audit --deployment-file ops/deployments/base-sepolia.json`.
- Fresh local recovery wallets can be prepared with `./ops/init_recovery_wallets.sh`.
- Local recovery env and redeploy preflight are available via `./ops/prepare_recovery_env.sh` and `./ops/preflight_recovery_redeploy.sh`.
- The public deployment artifact is redacted by default; local overlays in `~/.config/darwin/deployments/` restore operator-only fields.
- The first vNext governance layer deploys to a separate public-safe sidecar artifact; see `docs/VNEXT_DEPLOYMENT.md`.

## Scope

Security reports may cover:

- smart contracts in `contracts/`
- overlay services in `overlay/`
- SDK and signing flows in `sim/`
- public web surface in `web/`

## Note

This public file intentionally omits private operator and internal review workflow detail.
See `docs/GOVERNANCE_RECOVERY.md` for the public-safe recovery boundary and wallet bootstrap path.
