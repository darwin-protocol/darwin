# DARWIN Live Status

Last repo update: `2026-04-06`

## Current Truth

- The repo is real and reproducible locally.
- The public canary exists on Base Sepolia.
- The public canary is still the `WETH`-bond alpha, not the `DRW`-bond version.
- The Base Sepolia `DRW` token + staking layer is now live.
- A seeded Base Sepolia `DRW/WETH` reference pool is now live.
- A first-party browser swap portal now exists in `site/` and deploys through GitHub Pages.
- The next real steps are outside-watcher operation, outside archive flow, and external review.

## Verified Baseline

- Python self-check: `41/41` passing
- Solidity checks: `100` passing (`73` unit + `18` fuzz + `9` invariants)
- Overlay devnet: `7/7` services up locally
- Local DRW genesis smoke: passing
- Local DRW + reference-pool smoke: passing
- Public Base Sepolia core artifact: [ops/deployments/base-sepolia.json](ops/deployments/base-sepolia.json)
- Public Base Sepolia DRW token: `0x90519DFb5ed50fbd959Ed47BBcf7E4ae33750FF2`
- Public Base Sepolia DRW staking: `0xC84090E74880a672C5273f6A454E208Fe114634e`
- Latest warm canary report: `ready: true`, `onchain_drw: OK`, `tracked_supply: 1000000000000000000000000000/1000000000000000000000000000`
- Market bootstrap preflight path exists for a `DRW/WETH` Base Sepolia demo market
- Reference-pool deploy/seed path exists for a DARWIN-owned Base Sepolia demo market
- Live reference pool: `0x9E1fb3eb0Ca3b06038d2A4d6b6e5D18183E6B891`
- Live seeded reserves: `1000 DRW` + `0.0005 WETH`
- Initial DARWIN-controlled demo trades have now executed against the live reference pool
- Current post-demo reserves are approximately `985.384919987 DRW` and `0.000507483787963681 WETH`
- Governance + staking still directly hold `999,998,950 DRW`; the remaining `1,050 DRW` sit in the reference pool and DARWIN-controlled demo traders
- The governance wallet no longer holds spare `WETH` because it was used to seed the live pool
- The repo now ships a first-party swap portal for the seeded pool
- A dedicated `./.venv/bin/python ops/preflight_market_venue.py --venue darwin_reference_pool` check now exists for the artifact-backed venue path, and `uniswap_v4` remains tracked separately

## What Is Live

- Base Sepolia core DARWIN deployment
- Base Sepolia DRW token + staking deployment
- Gateway signature verification
- Deployment-pinned readiness checks
- Market bootstrap preflight for `DRW/WETH`
- Artifact-backed reference-pool deployment path for `DRW/WETH`
- Seeded artifact-backed Base Sepolia reference pool for `DRW/WETH`
- First-party browser portal for the seeded Base Sepolia market
- External watcher bootstrap/export/intake flow
- Audit bundle export flow
- Local encrypted wallet flow
- Local and optional testnet DRW genesis scripts

## What Is Not Live Yet

- A genuine outside watcher on the live canary
- Outside watcher evidence on the live canary
- Outside archive epoch through the live canary
- External audit / security review
- A tracked third-party Base Sepolia venue for `DRW/WETH`, if you want something other than the DARWIN reference pool
- Mainnet or public-token-launch posture

## True Blockers

- first genuinely external watcher operator
- first genuinely external archive epoch through the live canary
- external audit / security review

## Exact Next Action

1. Run the live canary with an outside watcher
2. Ingest a genuinely external archive epoch through that watcher path
3. Hand the live artifact and evidence to an outside reviewer
4. Point outside users at the live Base Sepolia reference pool and Pages portal
5. Point outside users at the simple swap runbook in `docs/MARKET_BOOTSTRAP.md`
6. Wait for real third-party interaction instead of project-controlled swaps

## What Remains After The Public DRW Deploy

- operate the canary with a real outside watcher
- run a real outside archive epoch through it
- hand the live artifact and evidence to an outside reviewer
- capture real third-party activity against the seeded Base Sepolia market
- decide the legal/compliance structure before any real public token distribution
