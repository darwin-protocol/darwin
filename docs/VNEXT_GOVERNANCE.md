# vNext Governance

DARWIN's current public alpha is honest about its trust model, but it is not yet structurally decentralized.

The protocol philosophy is already correct:

- governance should be constitutional, not operational
- market selection should be measured, not hand-tuned
- token distribution should support accountability, not wallet theater

The current implementation still has one central weakness:

- several core contracts hard-wire governance in the constructor and require redeploy on governance compromise

## What vNext Changes

### 1. Progressive decentralization instead of vague democratization

DARWIN should talk about **progressive decentralization**, not generic democratization.

That means reducing concentrated control in code and operations over time:

- move from one hot governance wallet to multisig + timelock
- separate emergency pause power from treasury/governance power
- separate operational roles from constitutional roles
- distribute DRW through rule-based claim flows instead of manual wallet sends
- measure outside participation before making stronger decentralization claims

### 2. Timelocked governance

vNext adds a minimal timelock primitive:

- [`DarwinTimelock.sol`](../contracts/src/governance/DarwinTimelock.sol)

Properties:

- governance schedules actions with a minimum delay
- guardian can cancel queued actions
- delay changes must be executed by the timelock itself
- execution is bounded by a grace window

This is the right place for:

- treasury transfers
- rotatable role changes
- governance handoffs
- non-emergency parameter changes

### 3. Rotatable governance for mutable contracts

vNext adds a reusable two-step governance primitive:

- [`Governable2Step.sol`](../contracts/src/governance/Governable2Step.sol)

Properties:

- current governance nominates a successor
- successor must explicitly accept
- removes one-transaction governance flips

Any new mutable DARWIN contract should inherit or replicate this pattern.

### 4. Rule-based DRW distribution

vNext adds a Merkle-claim distribution primitive:

- [`DRWMerkleDistributor.sol`](../contracts/src/DRWMerkleDistributor.sol)

Properties:

- claim lists are precommitted with a Merkle root
- users claim directly to their own wallet
- governance can only sweep leftovers after expiry

This is a better public distribution path than:

- manual wallet sends
- opaque spreadsheet allocations
- ad hoc faucet-only growth

## Recommended vNext Architecture

### Constitutional layer

- multisig governance council
- timelock executor
- emergency guardian

### Operational layer

- epoch operator
- batch operator
- watcher/reporter set

### Economic layer

- DRW staking
- species bonding
- watcher challenge bonds
- rule-based claim distributions

## Migration Path

### Near-term

1. Keep the current alpha honest about its trust model.
2. Move public language toward progressive decentralization.
3. Use the recovery deployment as the clean base for future promotion if needed.
4. Stop increasing discretionary wallet-based control.

### Before any stronger public decentralization claim

1. Put governance behind multisig.
2. Put mutable role changes behind timelock.
3. Ship rule-based distribution instead of wallet-led distribution.
4. Get real outside watchers and outside users.
5. Publish decentralization metrics:
   - outside holder count
   - outside claim count
   - outside swap count
   - watcher count
   - project-controlled supply percentage

## What Still Needs a Future Core Version

The current alpha core contracts still contain immutable governance roots in several places. Those should be replaced in a future core version rather than patched around operationally.

That set currently includes:

- `bond_vault`
- `challenge_escrow`
- `epoch_manager`
- `score_registry`
- `settlement_hub`
- `shared_pair_vault`
- `species_registry`

The practical implication is simple:

- vNext should not just wrap the existing core forever
- it should replace the immutable-governance parts with rotatable, timelocked versions
