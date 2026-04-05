# Security

## Reporting Vulnerabilities

If you discover a security vulnerability in DARWIN, please report it privately.

**Email:** security@darwin-protocol.org (placeholder — update before public release)

Do NOT open a public GitHub issue for security vulnerabilities.

## Scope

The following components are in scope for security reports:

- Smart contracts (`contracts/src/`)
- Overlay services (`overlay/`)
- SDK signing and verification (`sim/darwin_sim/sdk/`)
- Watcher replay logic (`sim/darwin_sim/watcher/`)

## Bug Bounty

A bug bounty program will be established before mainnet launch. Details will be published here.

## Current Security Status

| Component | Status |
|---|---|
| Contracts | Written, tested (37/37), NOT audited |
| Overlay services | Alpha, NOT production-hardened |
| SDK crypto | Simulated (HMAC stand-in, not real ML-DSA/ECDSA) |
| Key management | Development only — no HSM integration |

## Known Limitations

1. **v1 is an overlay, not a sovereign chain.** Settlement trust depends on the underlying EVM L2.
2. **PQ signatures are simulated in the current SDK.** Production will use FIPS 204 ML-DSA-65.
3. **The gateway does not yet verify signatures against real cryptographic libraries.**
4. **No formal audit has been conducted.**
5. **Safe mode is triggered manually by an admin multisig in v1.**

## Security Invariants

These invariants are tested in the contract test suite:

1. No intent settles above its remaining quantity (no overfill)
2. No batch replays with the same batchId
3. Slashing is restricted to ChallengeEscrow role only
4. Safe mode blocks new experimental flow but preserves withdrawals
5. Epoch finalization requires challenge window expiry + all roots present
6. Bond withdrawal requires 7-day cooldown
7. Only governance can exit safe mode
