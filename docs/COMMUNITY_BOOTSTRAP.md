# Community Bootstrap

The right way to start outside DARWIN activity is simple:

1. get outside wallets onto Base Sepolia
2. point them at the public tiny-swap link
3. keep public activity visible
4. measure genuine outside usage locally

Do not manufacture volume with project bots or self-generated optics. That creates noise, not adoption.

## Public Surface

- Site: `https://usedarwin.xyz/`
- Tiny swap: `https://usedarwin.xyz/trade/?preset=tiny-sell`
- Activity portal: `https://usedarwin.xyz/activity/`

## Best Current Distribution Path

For real outside onboarding, use:

1. a short public message with the tiny-swap link
2. the activity page as proof of recent DARWIN usage
3. a clear note that this is Base Sepolia testnet alpha

The public portal now exposes:

- a shareable tiny-swap preset
- live DARWIN contract activity
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

That report is the honest operator view of whether any activity is genuinely third-party.

## Farcaster and Base App

The repo now emits page-level Farcaster embed metadata on the main public pages so shared DARWIN links can launch the web app cleanly in Farcaster-compatible clients.

The current Base path is no longer centered on old Farcaster manifests. Base documents that after **April 9, 2026**, apps in Base App are standard web apps managed through Base.dev metadata rather than Farcaster mini-app manifests.

That means the next promotion path is:

1. keep the public site working as a normal web app
2. keep page-level embeds on the shareable URLs
3. register the app in Base.dev when you are ready for Base App distribution

## Useful Official References

- Farcaster Mini Apps getting started:
  `https://miniapps.farcaster.xyz/docs/getting-started`
- Farcaster page embeds and sharing:
  `https://miniapps.farcaster.xyz/docs/guides/sharing`
- Base App manifest transition:
  `https://docs.base.org/mini-apps/core-concepts/manifest`
- Base network information:
  `https://docs.base.org/base-chain/network-information`

