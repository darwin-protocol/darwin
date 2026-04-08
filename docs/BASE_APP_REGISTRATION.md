# Base App Registration

The Darwin portal is now registered on `https://base.dev/`, and the live Base lane is publishing Base Builder Code attribution.

## What Is Already Ready

- public site: `https://usedarwin.xyz/`
- starter cohort intake: `https://usedarwin.xyz/join/`
- canonical tiny swap: `https://usedarwin.xyz/trade/?preset=tiny-sell`
- public proof: `https://usedarwin.xyz/activity/`
- web manifest: `https://usedarwin.xyz/manifest.webmanifest`

The repo can now export a registration summary:

```bash
python3 ops/export_base_app_registration.py
```

Default output:

```text
ops/state/base-app-registration.json
```

## Builder Code Hook

The publish path auto-loads:

```text
~/.config/darwin/site.env
```

Tracked template:

```text
ops/site.env.example
```

Relevant entries:

```bash
export DARWIN_BASE_APP_ID="your-base-app-id"
export DARWIN_BASE_BUILDER_CODE="your-base-builder-code"
export DARWIN_ARBITRUM_BUILDER_CODE="your-arbitrum-builder-code"
export DARWIN_BASE_PAYMASTER_SERVICE_URL="https://..."
export DARWIN_ARBITRUM_PAYMASTER_SERVICE_URL="https://..."
```

Once those are filled, republish:

```bash
./ops/pi/publish_static_site.sh 192.168.86.214 sim
```

## Current Live State

Completed:

1. `https://usedarwin.xyz/` is registered on `base.dev`.
2. The site homepage publishes the required `<meta name="base:app_id" ...>` tag from `DARWIN_BASE_APP_ID`.
3. The public site now exposes Base App-compatible assets:
   - `https://usedarwin.xyz/base-app/icon.png`
   - `https://usedarwin.xyz/.well-known/farcaster.json`
   - `https://usedarwin.xyz/base-app/screenshot-home.png`
   - `https://usedarwin.xyz/base-app/screenshot-trade.png`
   - `https://usedarwin.xyz/base-app/screenshot-activity.png`
4. `https://usedarwin.xyz/market-config.json` now reports Builder Code attribution instead of `direct`.

Remaining boundary:

- the legacy `Enable Mini App Analytics` modal on `base.dev` no longer fails on missing site artifacts; it now fails server-side with a generic Base.dev error after manifest discovery. The standard web-app and Builder Code path is already live.
