# Community Bootstrap

The right way to start outside DARWIN activity is simple:

1. get outside wallets onto a live Darwin lane
2. point them at the public tiny-swap link
3. keep public activity visible
4. measure genuine outside usage locally

Do not manufacture volume with project bots or self-generated optics. That creates noise, not adoption.

## Pool Strategy

The public site should present three Darwin pool states, but only one of them should be routed by default:

- `Canonical`
  - live now
  - one pool per lane
  - default public route for claims, tiny swaps, and public proof
- `Experimental`
  - visible, but locked
  - reserved for alternate quote assets, descendant Darwin markets, or other opt-in tests
- `Incentivized`
  - visible, but locked
  - reserved for later rewards or liquidity programs once outside demand is real

Current unlock rule for non-canonical routes:

- at least `25` outside wallets
- at least `40` outside swaps

Until those gates are met, adding duplicate pools is more likely to fragment thin testnet liquidity than to help adoption.

## Public Surface

- Site: `https://usedarwin.xyz/`
- Epoch: `https://usedarwin.xyz/epoch/`
- Join starter cohort: `https://usedarwin.xyz/join/`
- Tiny swap: `https://usedarwin.xyz/trade/?preset=tiny-sell`
- Activity portal: `https://usedarwin.xyz/activity/`
- Share bundle: `https://usedarwin.xyz/community-share.json`

Additional lane:

- Arbitrum epoch: `https://usedarwin.xyz/epoch/?lane=arbitrum-sepolia`
- Arbitrum starter cohort: `https://usedarwin.xyz/join/?lane=arbitrum-sepolia`
- Arbitrum tiny swap: `https://usedarwin.xyz/trade/?preset=tiny-sell&lane=arbitrum-sepolia`
- Arbitrum activity: `https://usedarwin.xyz/activity/?lane=arbitrum-sepolia`
- Arbitrum share bundle: `https://usedarwin.xyz/community-share-arbitrum-sepolia.json`

## Best Current Distribution Path

For real outside onboarding, use:

1. a short public message with the tiny-swap link
2. the activity page as proof of recent DARWIN usage
3. a clear note that this is Darwin testnet alpha on the selected lane
4. a real starter cohort of outside wallets, not project wallets

The tracked cohort template and runbook are now in:

- [`ops/community-starter-cohort.example.csv`](../ops/community-starter-cohort.example.csv)
- [`ops/normalize_starter_cohort.py`](../ops/normalize_starter_cohort.py)
- [`ops/prepare_starter_cohort.sh`](../ops/prepare_starter_cohort.sh)
- [`docs/STARTER_COHORT.md`](./STARTER_COHORT.md)

The public intake helper is now:

- `https://usedarwin.xyz/join/`

It does not submit wallets anywhere. It prepares a clean cohort row that can be copied into the local starter cohort flow.

The public portal now exposes:

- a shareable epoch landing page
- a shareable starter-cohort intake page
- a shareable tiny-swap preset
- live DARWIN contract activity
- a canonical / experimental / incentivized pool map
- a public-safe outside-activity counter
- public contract explorer links for token, pool, faucet, distributor, and timelock

## Tracking Real Outside Activity

Public pages should stay simple. Outside-vs-project classification should stay local.

Build the local project-wallet allowlist:

```bash
python3 ops/build_project_wallet_allowlist.py
```

Then generate the local outside-activity report:

```bash
./.venv/bin/python ops/report_external_activity.py \
  --deployment-file ops/deployments/base-sepolia-recovery.json \
  --json-out ops/state/activity/external-activity.json \
  --markdown-out ops/state/activity/external-activity.md
```

Arbitrum lane:

```bash
./.venv/bin/python ops/report_external_activity.py \
  --deployment-file ops/deployments/arbitrum-sepolia.json \
  --rpc-url https://arbitrum-sepolia-rpc.publicnode.com \
  --json-out ops/state/activity/external-activity-arbitrum-sepolia.json \
  --markdown-out ops/state/activity/external-activity-arbitrum-sepolia.md
```

That report is the honest operator view of whether any activity is genuinely third-party.

The publish path now also exports public-safe lane summaries:

- `web/public/activity-summary.json`
- `web/public/activity-summary-arbitrum-sepolia.json`

It also exports public-safe outreach bundles:

- `web/public/community-share.json`
- `web/public/community-share-arbitrum-sepolia.json`

Those bundles include the current epoch, public links, and honest invite text derived from the live outside-activity snapshot. They are safe for operators or external agents to consume because they contain only public campaign data and public URLs.

## Farcaster and Base App

The repo now emits page-level Farcaster embed metadata on the main public pages so shared DARWIN links can launch the web app cleanly in Farcaster-compatible clients.

The current Base path is no longer centered on old Farcaster manifests. Base documents that after **April 9, 2026**, apps in Base App are standard web apps managed through Base.dev metadata rather than Farcaster mini-app manifests.

That means the next promotion path is:

1. keep the public site working as a normal web app
2. keep page-level embeds on the shareable URLs
3. keep the standard web app manifest live
4. register the app in Base.dev when you are ready for Base App distribution

## Useful Official References

- Farcaster Mini Apps getting started:
  `https://miniapps.farcaster.xyz/docs/getting-started`
- Farcaster page embeds and sharing:
  `https://miniapps.farcaster.xyz/docs/guides/sharing`
- Base App manifest transition:
  `https://docs.base.org/mini-apps/core-concepts/manifest`
- Base network information:
  `https://docs.base.org/base-chain/network-information`
