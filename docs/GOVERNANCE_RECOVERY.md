# Governance Recovery

This file describes the practical recovery boundary for the live Base Sepolia DARWIN alpha.

## Current Security Boundary

- The old deployment signer can be retired for future deployments.
- The live governance wallet remains the root of trust for the current public deployment.
- `darwinctl role-audit --deployment-file ops/deployments/base-sepolia.json` is the source of truth for this status.

## What Can Be Rotated

These contracts expose governance or operator mutation hooks and can be moved to a fresh wallet if the current governance wallet is still trusted and responsive:

- `drw_token`
- `drw_staking`
- `drw_faucet`
- `reference_pool`

## What Cannot Be Rotated In Place

These contracts currently hard-wire governance in the constructor and do not expose a governance-transfer function:

- `bond_vault`
- `challenge_escrow`
- `epoch_manager`
- `score_registry`
- `settlement_hub`
- `shared_pair_vault`
- `species_registry`

If the live governance wallet is compromised, the safe recovery path is a full core redeploy to a fresh governance wallet.

## Incident Classes

### Old Deployer Key Exposed

- Stop using that wallet for future deployments.
- Run `darwinctl role-audit` to confirm `Deployer retire ready: yes`.
- Move all future broadcasts to a fresh deployer wallet.

### Tunnel Token Exposed

- Rotate the Cloudflare tunnel token.
- Update the token in the Pi service environment.
- Restart the tunnel connector.

### Governance Wallet Exposed

- Treat the current core DARWIN deployment as unrecoverable in place.
- Do not assume DRW-side contract rotation is sufficient.
- Prepare fresh governance and deployer wallets.
- Redeploy the core DARWIN stack and any dependent DRW/faucet/market contracts.
- Update the public deployment artifact and portal configuration to the new stack.

## Fresh Wallet Path

Create local replacement wallets with:

```bash
./ops/init_recovery_wallets.sh
```

That emits two local-only, gitignored wallets under `ops/wallets/`:

- `darwin-future-governance`
- `darwin-future-deployer`

## Deployment Posture

- Fund the future-deployer wallet with Base Sepolia ETH before any new deployment.
- Keep the future-governance wallet offline until it is needed.
- Before any future migration or redeploy, rerun:

```bash
darwinctl role-audit --deployment-file ops/deployments/base-sepolia.json
```

This file intentionally avoids private infrastructure detail.
