# DARWIN Live Status

Last repo update: `2026-04-05`

## Current Truth

- The repo is real and reproducible locally.
- The public canary exists on Base Sepolia.
- The public canary is still the `WETH`-bond alpha, not the `DRW`-bond version.
- The DRW genesis path now exists in code and works locally.
- The next live on-chain step is the Base Sepolia DRW genesis broadcast.

## Verified Baseline

- Python self-check: `33/33` passing
- Solidity checks: `93` passing (`66` unit + `18` fuzz + `9` invariants)
- Overlay devnet: `7/7` services up locally
- Local DRW genesis smoke: passing
- Public Base Sepolia core artifact: [ops/deployments/base-sepolia.json](/path/to/darwin/ops/deployments/base-sepolia.json)

## What Is Live

- Base Sepolia core DARWIN deployment
- Gateway signature verification
- Deployment-pinned readiness checks
- External watcher bootstrap/export/intake flow
- Audit bundle export flow
- Local encrypted wallet flow
- Local and optional testnet DRW genesis scripts

## What Is Not Live Yet

- Public Base Sepolia DRW genesis
- Outside watcher evidence on the live canary
- Outside archive epoch through the live canary
- External audit / security review
- Mainnet or public-token-launch posture

## True Blockers

### Immediate blocker for public DRW deploy

- A funded Base Sepolia signer key must be loaded locally into `.env.base-sepolia`

### Real canary blockers after that

- first genuinely external watcher operator
- first genuinely external archive epoch through the live canary
- external audit / security review

## Exact Next Action

1. Fill in `DARWIN_DEPLOYER_PRIVATE_KEY` in [.env.base-sepolia](/path/to/darwin/.env.base-sepolia)
2. Run `./ops/deploy_public_drw.sh`

## What Remains After The Public DRW Deploy

- operate the canary with a real outside watcher
- run a real outside archive epoch through it
- hand the live artifact and evidence to an outside reviewer
- decide the legal/compliance structure before any real public token distribution
