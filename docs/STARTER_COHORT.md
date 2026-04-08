# Starter Cohort

The honest way to get `DRW` into circulation is to give it to real outside wallets, not to recycle project-controlled wallets through multiple pools.

## Goal

Use a small, real starter cohort to create the first outside holders on a Darwin lane, then route those recipients into the canonical tiny-swap path.

Good cohort size for the current alpha stage:

- `5-25` real outside wallets
- `100-250 DRW` each
- one canonical pool per lane

The public intake helper is:

- Base: `https://usedarwin.xyz/join/`
- Arbitrum: `https://usedarwin.xyz/join/?lane=arbitrum-sepolia`

That page is intentionally static and public-safe. It prepares a wallet row for operators to review; it does not submit anything automatically.

## Inputs

Start from the tracked template:

```bash
cp ops/community-starter-cohort.example.csv ops/state/base-sepolia-recovery-starter-cohort.csv
```

Replace the placeholder addresses with real outside wallet addresses. Do not include project-controlled wallets.

If you collect rough rows from the public intake helper or a spreadsheet, normalize them first:

```bash
python3 ops/normalize_starter_cohort.py \
  --intake-file ops/state/base-sepolia-recovery-starter-cohort-intake.csv \
  --out ops/state/base-sepolia-recovery-starter-cohort.csv
```

CSV format:

```text
account,amount,label
0x...,100000000000000000000,friend-1
0x...,100000000000000000000,friend-2
```

Amounts are in wei-style token units, so `100 DRW` is:

```text
100000000000000000000
```

## Build The Cohort Manifest

```bash
./ops/prepare_starter_cohort.sh
```

Defaults:

- network from the active Darwin env
- input CSV: `ops/state/<network>-starter-cohort.csv`
- output manifest: `ops/state/<network>-starter-cohort-merkle.json`
- deadline: `30 days` from build time

Override explicitly if needed:

```bash
DARWIN_NETWORK=arbitrum-sepolia \
DARWIN_STARTER_COHORT_FILE=ops/state/arbitrum-sepolia-starter-cohort.csv \
DARWIN_STARTER_COHORT_OUT=ops/state/arbitrum-sepolia-starter-cohort-merkle.json \
./ops/prepare_starter_cohort.sh
```

## Promote The Cohort

The current distributor root is fixed once deployed. That means a new outside cohort requires a new distributor manifest and a new deploy or promotion step before those wallets can claim.

Use the new cohort manifest as:

```bash
export DARWIN_VNEXT_DISTRIBUTION_FILE=ops/state/<network>-starter-cohort-merkle.json
./ops/preflight_vnext_governance.sh
./ops/deploy_vnext_governance.sh
./ops/preflight_vnext_promotion.sh
./ops/build_vnext_promotion_batch.sh
```

If the lane is already live with a previous distributor, treat the new cohort as the next distribution epoch, not as a hidden change to the old cohort.

## After Claim

Send recipients to the canonical pool only:

- Base tiny swap: `https://usedarwin.xyz/trade/?preset=tiny-sell`
- Arbitrum tiny swap: `https://usedarwin.xyz/trade/?preset=tiny-sell&lane=arbitrum-sepolia`

The trade portal also exposes a `Smart start` button on lanes where a live faucet exists. That path tries an atomic claim-plus-tiny-sell batch on wallets that support `wallet_sendCalls`, then falls back to the manual claim and tiny-sell flow.

Public proof:

- Base activity: `https://usedarwin.xyz/activity/`
- Arbitrum activity: `https://usedarwin.xyz/activity/?lane=arbitrum-sepolia`

## What Not To Do

- do not reuse project wallets and call them outside wallets
- do not spread thin liquidity across duplicate pools just to show more venues
- do not self-swap treasury against treasury to imply adoption

The Darwin rule stays the same:

- canonical first
- real outside holders next
- experimental and incentivized routes only after the canonical pool has real traction
