# DARWIN Operator Quickstart

Run a DARWIN overlay node. Start with **watcher** — the safest and most valuable first role.

## Prerequisites

- Python 3.12+
- Git
- ~500 MB disk, 4 vCPU, 16 GB RAM (watcher profile)

## Step 1: Clone and verify

```bash
git clone https://github.com/darwin-protocol/darwin.git
cd darwin
```

## Step 2: Install dependencies

```bash
cd sim
python -m venv .venv && source .venv/bin/activate
pip install pyyaml numpy pandas pyarrow zstandard
cd ..
```

## Step 3: Run the self-check

```bash
cd sim
python -m pytest tests/test_end_to_end.py -v
```

All 6 tests must pass before proceeding.

## Step 4: Run the E1-E7 experiment suite

```bash
python -m darwin_sim.experiments.suite configs/baseline.yaml 10000 2026
```

Expected: all 7 experiments PASS.

## Step 5: Verify watcher replay

```bash
# Run an experiment to produce artifacts
python -m darwin_sim.experiments.runner configs/baseline.yaml data/raw/raw_swaps.csv ../outputs/e2

# Replay and verify independently
python -m darwin_sim.watcher.replay ../outputs/e2
```

Expected: `REPLAY PASSED — all metrics match`

---

## Running the Overlay Services

### Watcher (first role for outside operators)

```bash
cd darwin
export PYTHONPATH="$PWD/sim"
python overlay/watcher/service.py 9446 /var/lib/darwin/watcher http://archive-host:9447
```

**What it does:**
- Mirrors epoch artifacts from the archive
- Recomputes all scores independently
- Detects mismatches and emits challenge candidates
- Serves replay status via HTTP

**Endpoints:**
- `GET /healthz` — health check
- `GET /readyz` — readiness (has it replayed at least one epoch?)
- `GET /v1/status` — all replay results
- `GET /v1/epochs/:id` — single epoch detail
- `GET /v1/challenges/open` — detected mismatches
- `POST /v1/replay/local` — replay from local artifacts

**Success condition:** Your watcher produces `passed: true` on the latest epoch.

### Archive mirror

```bash
python overlay/archive/service.py 9447 /var/lib/darwin/archive
```

**What it does:**
- Stores epoch artifacts with SHA-256 verification
- Serves them to watchers via HTTP

**Endpoints:**
- `GET /v1/epochs` — list available epochs
- `GET /v1/epochs/:id` — epoch manifest with file hashes
- `GET /v1/epochs/:id/:filename` — download artifact
- `POST /v1/ingest` — ingest new epoch

### Public finalizer

```bash
python overlay/finalizer/service.py 9448 1800
```

**What it does:**
- Monitors epoch state
- Finalizes epochs permissionlessly after the challenge window (1800s = 30 min)
- No bond required — just gas

**Endpoints:**
- `GET /v1/check/:epoch_id` — is it finalizable?
- `POST /v1/finalize/:epoch_id` — finalize it

---

## Running the Full Devnet

Start all 7 services and run the integration test:

```bash
export PYTHONPATH="$PWD/sim"
python overlay/devnet.py
```

Expected output: 7/7 services UP, E2 PASS, watcher PASS, epoch finalized.

---

## Role Onboarding Order

1. **Watcher** — verify epoch scores independently
2. **Archive mirror** — store and serve artifacts
3. **Public finalizer** — finalize epochs after challenge window
4. **Gateway** — accept intents (requires 2 WETH bond)
5. **Solver** — quote for RFQ species

---

## Trust Model (Honest)

v1 is a **PQ-hardened intent layer on classical EVM settlement**.

- Settlement trust: classical chain (machine-enforced)
- Intent authenticity (PQ): operator-enforced in v1
- Score correctness: challengeable (watcher-verified)
- Emergency intervention: admin multisig (explicitly centralized in v1)

Do NOT call these "validator nodes." They are overlay service nodes.

---

## Contract Tests

```bash
cd contracts
forge test -vv
```

Expected: 37/37 tests pass across all 7 contracts.

---

## Questions

- **How do I know if my replay is correct?** Compare your `recomputed_uplift` against the published `uplift` in the epoch report. If they match within 0.5 bps, you're good.
- **What if I find a mismatch?** That's the point. Open a challenge via the ChallengeEscrow contract. Material challenges require 0.25 WETH bond. If upheld, you get your bond back + 25% of the slash.
- **Do I need a bond to run a watcher?** Optional standing bond of 1 WETH. You can run without one, but bonded watchers get priority in the challenge queue.
