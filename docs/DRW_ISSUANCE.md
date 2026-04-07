# DRW Issuance

`DRW` should not become a proof-of-work or generic inflation token.

That would cut directly against the Darwin spec:

- `DRW` is genomic stake, not money
- the point is governance, bonding, watcher discipline, and controlled market evolution
- fake "mining" would reward compute theater, not useful market behavior

## Recommendation

Use a **fixed-supply, earned-distribution hybrid**.

That means:

- keep total `DRW` supply fixed at genesis
- keep constitutional reserves fixed and visible
- make a defined share of supply *earned by epoch* rather than manually wallet-sent

This is the clean Darwin-native answer to "should it be mined?"

- not mined by hashpower
- earned by contribution, staking, and epoch participation

## Recommended Split

The current live allocation already points toward a strong `50/50` structure:

- `50%` constitutional/genesis reserve
  - treasury `20%`
  - insurance `20%`
  - sponsor rewards reserve `10%`
- `50%` earned reserve
  - staking reserve `30%`
  - epoch/community reserve `20%`

So the best move is not "replace genesis with mining."

The best move is:

- keep the fixed-supply genesis
- formalize the earned half

## What "Earned" Means In Darwin

`DRW` emissions should follow Darwin epochs, not generic liquidity mining.

Good earned paths:

- stakers securing the system
- watchers/reporters participating in honest challenge flow
- species sponsors with bounded reward logic
- outside users receiving transparent epoch claim allocations

Bad earned paths:

- raw trading volume rewards
- wash-trade incentives
- generic hashpower mining
- perpetual inflation detached from protocol utility

## vNext Primitive

The repo now has the right primitive for this path:

- [`DRWEpochDistributor.sol`](../contracts/src/DRWEpochDistributor.sol)

That contract:

- uses a pre-minted reserve, not new inflation
- configures claim roots per epoch
- lets users claim directly to their own wallet
- supports sweeping leftovers after the claim deadline

This should be used for the `20%` community/epoch reserve.

The `30%` staking reserve is already handled separately by:

- [`DRWStaking.sol`](../contracts/src/DRWStaking.sol)

## Recommended Positioning

Say this publicly:

- `DRW` is fixed-supply genomic stake
- half of supply is constitutional reserve
- half of supply is earned over time through staking and epoch distributions

Do not say:

- `DRW` is mined like a base-layer coin
- `DRW` has open-ended inflation

## Next Operational Move

1. Keep the fixed-supply token design.
2. Keep staking emissions as the first earned lane.
3. Move the community reserve onto epoch-based Merkle distributions.
4. Tie epoch claims to outside participation and public proof surfaces.
5. Avoid any reward scheme that can be farmed by fake internal volume.
