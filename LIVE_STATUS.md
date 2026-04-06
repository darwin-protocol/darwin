# DARWIN Live Status

Last repo update: `2026-04-06`

## Current Truth

- The repo is real and reproducible locally.
- The public canary exists on Base Sepolia.
- The public canary is still the `WETH`-bond alpha, not the `DRW`-bond version.
- The Base Sepolia `DRW` token + staking layer is now live.
- The next real steps are outside-watcher operation, outside archive flow, and external review.

## Verified Baseline

- Python self-check: `33/33` passing
- Solidity checks: `93` passing (`66` unit + `18` fuzz + `9` invariants)
- Overlay devnet: `7/7` services up locally
- Local DRW genesis smoke: passing
- Public Base Sepolia core artifact: [ops/deployments/base-sepolia.json](/path/to/darwin/ops/deployments/base-sepolia.json)
- Public Base Sepolia DRW token: `0x90519DFb5ed50fbd959Ed47BBcf7E4ae33750FF2`
- Public Base Sepolia DRW staking: `0xC84090E74880a672C5273f6A454E208Fe114634e`

## What Is Live

- Base Sepolia core DARWIN deployment
- Base Sepolia DRW token + staking deployment
- Gateway signature verification
- Deployment-pinned readiness checks
- External watcher bootstrap/export/intake flow
- Audit bundle export flow
- Local encrypted wallet flow
- Local and optional testnet DRW genesis scripts

## What Is Not Live Yet

- A genuine outside watcher on the live canary
- Outside watcher evidence on the live canary
- Outside archive epoch through the live canary
- External audit / security review
- Mainnet or public-token-launch posture

## True Blockers

### Real canary blockers after that

- first genuinely external watcher operator
- first genuinely external archive epoch through the live canary
- external audit / security review

## Exact Next Action

1. Run the live canary with an outside watcher
2. Ingest a genuinely external archive epoch through that watcher path
3. Hand the live artifact and evidence to an outside reviewer

## What Remains After The Public DRW Deploy

- operate the canary with a real outside watcher
- run a real outside archive epoch through it
- hand the live artifact and evidence to an outside reviewer
- decide the legal/compliance structure before any real public token distribution
