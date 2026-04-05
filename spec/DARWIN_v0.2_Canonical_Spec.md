# DARWIN v0.2 — Canonical Protocol Specification

**An Evolutionary Intent-Centric Exchange Protocol**
**with Post-Quantum Hardened Trust Model**

Version 0.2 | April 2026 | Canonical merged specification

---

> "The exchange should learn from markets rather than ask governance to guess forever."

## Document structure

- **Part I** — Philosophy, architecture, and versioned trust model
- **Part II** — Protocol specification (intents, routing, fitness, evolution, settlement)
- **Part III** — Cryptographic foundation (PQ suite, account model, encrypted channels)
- **Part IV** — Simulator specification
- **Appendices** — Glossary, implementation sequencing, default parameters

---

# PART I — PHILOSOPHY AND ARCHITECTURE

## 1. Abstract

Most decentralized exchanges hard-code one philosophy of market design and then ask users and liquidity providers to live inside its trade-offs. Continuous AMMs optimize for immediacy, batch auctions optimize for fairness, solver networks optimize for large bespoke flow, and time-sliced execution optimizes for patience. None of these mechanisms is always best for every pair, volatility regime, or user objective.

DARWIN proposes an evolutionary alternative. Instead of forcing all order flow through one market structure, the protocol hosts multiple bounded execution modules, called **species**, that compete for flow inside defined pair clusters. Users submit signed intents that specify what they want, what constraints must be respected, and what they value most — speed, price, privacy, certainty, or patience. A routing layer selects candidate species using a contextual utility function and an exploration budget. A settlement hub executes the fill. A scorekeeper measures trader quality, LP welfare, MEV leakage, reliability, and capital efficiency. An evolution manager then reallocates future flow, admits mutations, and retires weak species.

The result is a DEX that treats market structure as something to be discovered empirically rather than fixed politically. Governance does not micromanage fees and parameters each week. Governance defines constitutional boundaries, approved templates, and metric weights. Within those bounds, the protocol adapts.

## 2. Core thesis

A market should be an organism, not a monument. DARWIN is a decentralized exchange protocol in which multiple bounded market mechanisms compete for order flow, are measured on trader and LP outcomes, and receive more or less flow based on observed fitness. The protocol evolves market structure instead of assuming one AMM design is always best.

DARWIN is first a **market-evolution protocol**, not a new monetary religion. The beachhead is DEX microstructure because execution quality can be measured quickly and empirically, unlike full monetary policy.

## 3. The problem DARWIN solves

Three failures recur across decentralized market design. First, one mechanism is forced to serve every type of order. Second, LPs are exposed to adverse selection and MEV when static fee schedules fail to recognize toxic flow. Third, governance becomes a slow human bottleneck for what is essentially a control-system problem.

| Failure | What breaks | DARWIN response |
|---|---|---|
| Static design | A single AMM or auction rule is expected to serve urgent retail flow, large rebalances, correlated pairs, and long-tail assets equally well. | Multiple species coexist and compete inside each pair cluster. |
| Heterogeneous user goals | Users care about different things: best price now, low gas, privacy, certainty, or ability to wait. | Intents include objective profiles and hard constraints. |
| LP exposure | Static fees often undercharge toxic flow and overcharge benign flow. | Species can adapt fees, matching rules, and inventory bounds. |
| Slow governance | Token votes are too slow and too political for day-to-day microstructure tuning. | Fitness-based flow allocation replaces most parameter voting. |
| Weak feedback loops | Protocols often know volume but not which mechanism actually served the user best. | DARWIN measures execution quality and routes more flow to winners. |

## 4. Philosophy

**Foundational stance:** Markets should be discovered, not declared. Human designers can specify goals and safety rails, but they should not assume one fee curve, one matching rule, or one latency model will always dominate. DARWIN moves adaptation from forum debate into measurable competition.

- **User sovereignty over preferences.** The user expresses what matters; the protocol should not guess.
- **Auditable experimentation.** Evolution is bounded by approved templates, disclosed genomes, and challengeable metrics.
- **LP alignment.** The protocol must measure LP welfare explicitly, not treat fee revenue as the only success metric.
- **Minimal governance.** Governance defines the constitution, not every mutation.
- **Fail-safe design.** A conservative baseline species always remains available as a benchmark and fallback.
- **Honest trust claims.** Every version of the protocol states exactly what it trusts and what it does not.

## 5. Design goals and non-goals

| Type | Statement |
|---|---|
| Goal | Higher realized execution quality than a static DEX, net of gas and feasible market impact. |
| Goal | Reduce sandwiching and other MEV leakage where the user opts into protected routes. |
| Goal | Price toxic flow more intelligently and protect LPs from persistent adverse selection. |
| Goal | Create a permissionless path for market design experimentation inside bounded templates. |
| Non-goal | Replace the need for audits, formal review, or emergency controls at launch. |
| Non-goal | Let arbitrary unreviewed code execute in settlement. |
| Non-goal | Turn the protocol token into money. DRW is genomic stake, not a universal currency claim. |

## 6. Versioned trust model

The original DARWIN concept implies two independent architectural choices: (a) evolving market structure via species competition, and (b) post-quantum cryptographic trust. These do not need to ship simultaneously. Conflating them produces dishonest marketing or unshippable products. DARWIN therefore defines an explicit versioned trust model.

### DARWIN v1 — Execution overlay

The product you can actually ship first.

- Settlement lives on an EVM L2 (low fees, deep stablecoin liquidity).
- Final trust is classical chain trust (secp256k1 validators, Ethereum L1 finality).
- DARWIN's novelty lives in intents, routing, species competition, fitness scoring, and batch settlement.
- Post-quantum crypto is used for **user authentication and transport hardening**, not for end-to-end settlement finality.

The honest label:

> **"PQ-hardened intent layer on classical settlement."**

Not "fully quantum-proof." Not "quantum-resistant chain."

### DARWIN v1.5 — Sovereign rollup / custom execution stack

The migration layer.

- Add ML-DSA verification as a native precompile.
- Keep the same intent format — economic semantics unchanged.
- Move score commitments, batch roots, and challenge roots into the rollup state model.
- Make PQ verification first-class without rewriting the application logic.

### DARWIN v2 — Native PQ execution layer

The endpoint described by the PQ cryptographic foundation.

- 32-byte policy-hash addresses.
- ML-DSA hot keys for all user signatures.
- ML-DSA-87 + SLH-DSA dual-signature cold path.
- ML-KEM encrypted channels.
- Validator finality with explicit k-of-n PQ signatures.
- No classical settlement dependency remaining.

The roadmap:

```
Overlay (v1) → Sovereign Rollup (v1.5) → Native PQ Chain (v2)
```

Each step preserves economic semantics and intent format. Only the trust boundary moves.

## 7. System overview

DARWIN has six layers:

1. **Intent layer** — captures user preferences as signed, structured objects.
2. **Router** — classifies each order by context and computes candidate utilities.
3. **Species** — execute according to their own matching and liquidity rules.
4. **Settlement hub** — enforces signatures, slippage, deadlines, and accounting.
5. **Scorekeeper + watchers** — compute challengeable performance metrics.
6. **Evolution manager** — updates flow weights, admits mutations, and retires weak configurations.

```
                    DARWIN Protocol Data Flow

Users / Wallets ──► Relayers ──► DARWIN Router ──┬── Species A (Continuous)
 Signed intents      Private       Context +      ├── Species B (Batch)
                     or public     utility         ├── Species C (Adaptive)
                                                   └── Species D (Patient)
                                                          │
  ScoreKeeper + ◄── Fitness Engine + ◄──────── Settlement Hub
  Watchers           Evolution Manager           Atomic execution,
  Metrics,           Flow weights,               checks, accounting
  challenges         mutation, pruning
```

## 8. Actors

| Actor | Role |
|---|---|
| Trader | Signs an intent describing the desired swap, constraints, and objective profile. |
| Relayer | Distributes intents to the router and, where applicable, to protected solver channels. |
| Solver | Competes to fill intents through a species or inventory-backed route; posts bond for reliability. |
| LP | Provides liquidity to a species via the shared pair vault. |
| Species sponsor | Posts DRW bond to launch a parameterized species instance and receives sponsor rewards if it performs. |
| Watcher | Verifies metrics, challenges false score roots, and monitors protected-order behavior. |
| Governance | Approves template families, constitutional ranges, treasury actions, and emergency changes. |

## 9. Species: the core primitive

A species is a bounded market design defined by an approved execution template plus a disclosed parameter set. Species are not free-form arbitrary code at v1. The protocol distinguishes between **template families** — audited code modules — and **genomes**, which are parameter vectors inside those families. Parameterized species can be proposed permissionlessly with bond and tests. Entirely new template families require governance approval, audit, and canary deployment.

### Species genome

| Gene | Options |
|---|---|
| Matching gene | continuous / batch / TWAMM / RFQ |
| Liquidity gene | CLAMM / oracle curve / inventory / hybrid |
| Fee gene | static / vol-scaled / toxicity / patience rebate |
| Privacy gene | public / private / commit-reveal |
| Inventory gene | passive / bounded / hedged |
| Safety gene | oracle band / flow cap / TVL cap / timeout |

### Reference species for v1

| Species | Mechanism | Primary use |
|---|---|---|
| S0 — Sentinel | Continuous baseline CLAMM | Conservative dynamic fee lane with narrow safety bounds; always on as benchmark and fallback. |
| S1 — Batch | Short sealed batch auction | Collects compatible intents over a short interval, internally crosses flow, and clears at one price per batch. |
| S2 — Adaptive | Oracle-aware adaptive curve | Moves curvature and fee schedule with volatility, inventory skew, and oracle band distance. |
| S3 — Patience | Time-sliced patient execution | Lets users trade lower immediacy for lower expected cost over a chosen completion window. |
| S4 — RFQ | Private solver lane | Uses bonded solvers or market makers to price larger or thinner flow under protected routing. |

A single pair cluster need not run every species at once. The active set is chosen by governance and evolution policy.

### Species lifecycle

```
Proposal ──► Sandbox ──► Probation ──► Active ──► Mature / Top tier ──► Retire or Mutate
Bond+genome   Static      Capped flow   Normal     Can reproduce        New candidate
              tests                     routing
```

v1 supports permissionless parameter mutations inside approved templates; new code families require governance and audit.

| Status | Behavior |
|---|---|
| Sandbox | No live flow or de minimis internal test flow; static checks and replay simulation only. |
| Probation | Receives a capped exploration share and tight TVL limits. |
| Active | Normal routing eligibility under standard caps. |
| Mature | Eligible for higher flow share and parent selection. |
| Retiring | Flow share decays; no new LP deposits; positions unwind over defined period. |
| Paused | Emergency or policy pause pending review. |

## 10. Pair clusters and context buckets

Species are not compared globally in the abstract. Performance is measured in context. Each traded pair belongs to a **pair cluster** such as major volatile, stable versus stable, correlated assets, or long-tail. Within a cluster, performance is further segmented by order-size bucket, volatility regime, urgency class, and privacy mode. The router consults context-matched fitness rather than a single global average.

## 11. Routing philosophy

Routing is not simple best-price selection. A user who wants certainty in one second should not always be routed the same way as a user willing to wait five minutes for better execution. DARWIN therefore models user intent as a preference vector. Wallets may expose this as simple profiles — NOW, BALANCED, PRIVATE, PATIENT, LIMIT — while the protocol uses numeric weights under the hood.

## 12. Token and economics

The DRW token is not positioned as general-purpose money. Its role is **genomic stake**: securing solvers, bonding species sponsors, underwriting watcher challenges, and participating in constitutional governance.

| Role | Description |
|---|---|
| Species bond | A sponsor posts DRW to launch a parameterized species and to signal confidence in its design. |
| Solver bond | Solvers stake DRW and are slashable for non-delivery or policy violations on protected flow. |
| Watcher bond | Metric challengers and reporters stake DRW to support honest score publication. |
| Governance stake | DRW holders vote only on constitutional parameters, template approval, and treasury actions. |
| Fee sink | A share of protocol revenue is routed to insurance, stakers, treasury, and sponsor rewards. |

DRW exists to govern, secure, and discipline market experimentation. Ordinary underperformance of a species loses flow; it is not automatically slashed absent misconduct.

## 13. Governance model

DARWIN rejects constant parameter politics. Governance is **constitutional, not operational**. It can approve or remove template families, set bounded ranges for metric weights and caps, control treasury use, and exercise emergency pause powers. It does not hand-tune batch intervals every day or vote on every fee slope. Those are left to bounded species competition.

- Governance approves code families, not every parameter mutation.
- Governance sets metric-weight bounds, exploration floors, and maximum flow caps.
- Governance can trigger safe mode or pause a compromised species.
- All ordinary changes follow a timelock; emergency actions are temporary and must be ratified or reversed.

## 14. Security model

A self-evolving exchange must be safer than its slogan. The design begins with constraints:

- A conservative baseline species always remains available.
- New parameterized species begin in sandbox and probation with hard flow and TVL caps.
- New code families require explicit governance and audit.
- Score roots are challengeable.
- Protected flows can use private routing.
- Oracle disagreement triggers safe mode.
- LP capital settles in shared pair vaults, not silently socialized across unrelated strategies.

## 15. Safe mode and emergency controls

Safe mode degrades gracefully rather than pretending evolution can solve every failure in real time. It is triggered by oracle disagreement, unresolved settlement anomalies, exploit suspicion, or governance emergency action.

| Trigger | Effect |
|---|---|
| Oracle disagreement | Pause adaptive species; baseline and batch only. |
| High revert or timeout rate | Reduce flow caps for affected species. |
| Protected-order policy breach | Pause guilty solver; slash if proven. |
| Exploit suspicion | Pause affected species and route only through baseline safe lane. |

---

# PART II — PROTOCOL SPECIFICATION

## 16. Formal objects

The protocol operates on a small number of canonical objects:

- **Intent** — the user's desired trade and constraints.
- **Species genome** — a parameterized market design inside an approved template.
- **Solution** — a solver-submitted executable fill proposal.
- **Epoch metrics** — challengeable performance data for each species and context bucket.

## 17. Intent format

| Field | Type | Description |
|---|---|---|
| trader | address | Signer and owner of the intent. |
| tokenIn / tokenOut | address | Assets to sell and buy. |
| amountType | enum | EXACT_IN, EXACT_OUT, LIMIT, or TWAP style intent. |
| amount | uint256 | Primary amount semantics defined by amountType. |
| minOut / maxIn | uint256 | Hard slippage bounds. |
| deadline | uint64 | Last valid settlement time. |
| profile | enum or vector | NOW, BALANCED, PRIVATE, PATIENT, LIMIT, or explicit weights. |
| latencyMax | uint32 | Maximum acceptable completion time. |
| privacyMode | enum | PUBLIC, PRIVATE, or SEALED_BATCH. |
| allowedSpeciesMask | bitmap | Optional restriction on eligible species. |
| solverFeeCap | uint16 bps | Maximum solver fee the user will accept. |
| partialFill | bool | Whether partial fills are valid. |
| nonce | uint256 | Replay protection. |
| permitData | bytes | Optional permit or Permit2 authorization. |
| signature | bytes | Dual-envelope signature (see Section 18). |

## 18. Dual-envelope intent signing

The whitepaper's EVM settlement path and the PQ foundation's post-quantum trust path are reconciled through a dual-envelope design. Every intent carries two cryptographically bound signatures: one post-quantum, one classical.

### Construction

Given an intent object I, compute the PQ digest:

```
h_pq = H_{DARWIN/Intent/v1}(suite_id, acct_pq, I)
```

Sign with the user's PQ hot key:

```
sigma_pq <- MLDSA65.Sign(sk_pq, h_pq)
```

Then bind the PQ intent into an EVM-settleable envelope:

```
h_evm = EIP712(chain_id, hub, keccak256(I || h_pq || suite_id))
```

Sign with the user's classical key:

```
sigma_evm <- ECDSA.Sign(sk_evm, h_evm)
```

The full order object is:

```
I* = (I, h_pq, sigma_pq, sigma_evm, suite_id)
```

### Verification split

| Layer | Verifies | Where |
|---|---|---|
| Solvers and private routing | sigma_pq (ML-DSA-65) | Off-chain |
| Settlement hub (EVM) | sigma_evm (ECDSA) | On-chain |
| Watchers | Both signatures | Off-chain |

### Migration path

- **v1:** Both signatures required. Chain verifies ECDSA. Solvers verify ML-DSA.
- **v1.5:** Chain gains ML-DSA precompile. Both verified on-chain.
- **v2:** sigma_evm dropped. Only sigma_pq required. Economic semantics unchanged.

The two signatures are cryptographically bound through the inclusion of h_pq in the EIP-712 hash. Dropping sigma_evm in v2 does not change the intent's economic meaning — only the trust boundary.

## 19. Species genome format

| Genome field | Meaning |
|---|---|
| templateId | Approved code family identifier. |
| pairCluster | Eligible cluster (majors, stables, correlated, long-tail). |
| matchMode | Continuous, batch, RFQ, or time-sliced. |
| feeMinBps / feeMaxBps | Allowed fee band. |
| volSlope | Fee sensitivity to realized volatility. |
| toxicitySlope | Fee sensitivity to toxicity estimator. |
| batchIntervalMs | Used for batch species where applicable. |
| oracleBandBps | Maximum allowed divergence from reference oracle before defense mode. |
| inventoryCapPct | Maximum inventory imbalance before throttling. |
| privacyFlag | Public, private relay, or sealed. |
| flowCapBps | Maximum order-flow share while active. |
| tvlCap | Maximum TVL allowed in probation or active mode. |
| timeoutMs | Max solver or route response time. |
| sponsor | Address receiving sponsor rewards. |
| metadataHash | Hash of disclosure package, test vectors, and simulation report. |

## 20. Router utility function

For a given intent x and a context bucket z, the router computes candidate utility for each eligible species s:

```
U(s | x, z) =
    w_price(x)   * PriceScore(s, x, z)
  + w_speed(x)   * SpeedScore(s, x, z)
  + w_privacy(x) * PrivacyScore(s, x, z)
  + w_cost(x)    * CostScore(s, x, z)
  + w_cert(x)    * CertaintyScore(s, x, z)
  + ExploreBonus(s, z)
  - RiskPenalty(s, z)
```

Weights are derived from the user's profile or explicit vector. ExploreBonus ensures new but safe species receive some live data. RiskPenalty reflects probation status, recent incidents, oracle stress, timeout behavior, and flow-cap proximity.

## 21. Reference routing algorithm

```
1. Parse signed intent x and classify context bucket z.
2. Build candidate set S(z) from allowed species, governance policy, and risk state.
3. Request executable quotes or commitments from each candidate.
4. Drop any quote that violates user's hard constraints.
5. Compute U(s | x, z) for each remaining candidate.
6. Select s* = argmax U subject to:
   - baseline flow floor
   - exploration budget floor
   - per-species flow cap
   - probation cap
   - control reservation (rho fraction to S0 for counterfactual scoring)
7. Send winning route to SettlementHub for atomic execution.
8. Record fill outcome for ScoreKeeper.
```

The baseline species floor, exploration floor, and control reservation are constitutional controls. They prevent the protocol from overfitting or collapsing into a single dominant route before enough evidence exists.

## 22. Counterfactual fitness scoring

**Core principle:** Do not score a species purely on the flow it receives, because routing itself biases outcomes. DARWIN is a controlled experiment, not a popularity contest.

### Control reservation

For each intent bucket b, randomly reserve a control fraction rho for baseline species S0. This provides unbiased estimates of what would have happened under baseline execution.

### Causal uplift estimation

```
Delta_TS_s = E[TS | A=s, b] - E[TS | A=S0, b]     (trader surplus uplift)
Delta_LP_s = E[LP | A=s, b] - E[LP | A=S0, b]     (LP health uplift)
```

### Composite fitness

Fitness is maintained per species and context bucket as an exponential moving average:

```
Fitness_{s,z}(t+1) = (1 - lambda) * Fitness_{s,z}(t)
                   + lambda * Composite_{s,z}(t)
```

where:

```
Composite_{s,z} =
    w_T * clip(Delta_TS_s)
  + w_L * clip(Delta_LP_s)
  + w_F * clip(Delta_FR_s)
  - w_A * clip(ADV_s)
  - w_R * clip(Risk_s)
```

### Metric definitions

| Metric | Definition |
|---|---|
| Delta_TS (Trader Surplus Uplift) | Realized user outcome improvement versus counterfactual S0 execution in the same context bucket. |
| Delta_LP (LP Health Uplift) | Net LP value versus passive hold, compared to S0 LP performance, adjusted for fees, inventory drift, and hedging cost. |
| Delta_FR (Fill Rate Uplift) | Fill completion rate improvement versus S0 baseline. |
| ADV (Adverse Selection) | Post-trade markout: mean absolute price move against the fill direction at tau seconds post-execution, normalized by oracle reference. |
| Risk | Oracle breaches, policy violations, concentration, manipulation, unresolved incidents. |

Individual metrics are clipped to bounded ranges to prevent single outliers from dominating the score.

### Why counterfactual

Naive fitness (measuring raw performance of routed flow) creates a selection bias: a species that receives easy flow looks good, one that receives hard flow looks bad. Counterfactual scoring against the control group eliminates this confound. DARWIN becomes experimental economics, not A/B testing theater.

## 23. Anti-gaming score rules

A species must not be able to pump its own score with wash flow. Score contributions use:

1. **Per-entity caps.** No single trader address may contribute more than C% of a species' score in any epoch.
2. **Trimmed-mean improvement.** Fitness uses median or trimmed-mean improvement, not raw volume-weighted average. Outlier fills (top/bottom 5%) are excluded.
3. **Minimum external fill count.** A species must serve at least N_min distinct external addresses before its fitness score is considered valid.
4. **Delayed markout penalties.** Trader surplus is measured not just at fill time but at tau-second markout to catch strategies that look good instantaneously but create deferred harm.
5. **Self-referential flow detection.** Flows where the sender, solver, and species sponsor share on-chain graph proximity trigger an abnormal cluster flag. Flagged flows are excluded from fitness computation and the sponsor's bond may be slashed if the pattern persists.

**Key idea:** Fitness is based on causally credible improvement, not just activity.

## 24. Revenue floor

If evolution optimizes only for trader surplus, species will race fees toward zero and protocol revenue collapses. The protocol therefore enforces two floors:

### Per-trade fee floor

```
fee_n = max(phi_s(I_n), f_min * notional_n)
```

where phi_s is the species' computed fee and f_min is the constitutional minimum fee rate (e.g., 0.5 bps).

### Protocol revenue floor

```
rev_n = max(tau_f * fee_n, tau_0 * notional_n)
```

where tau_f is the protocol take rate on fees (reference: 15%) and tau_0 is a tiny but nonzero take on notional (e.g., 0.1 bps). This ensures the protocol earns revenue even if species evolve to very low fees.

### Fee model and revenue flow

| Component | Reference design |
|---|---|
| Gross execution fee | Species-specific fee, subject to f_min floor. |
| Protocol take | max(15% of fee component, 0.1 bps of notional). |
| Insurance vault | 40% of protocol take. |
| DRW stakers | 30% of protocol take. |
| Treasury | 20% of protocol take. |
| Species sponsor reward | 10% of protocol take for the species that served the flow. |

## 25. Data availability and challengeability

Metrics are only useful if they can be challenged. Every epoch publishes four canonical roots:

```
R_I = IntentRoot       (all intents submitted this epoch)
R_F = FillRoot          (all fills executed this epoch)
R_O = OracleRoot        (all oracle attestations consumed this epoch)
R_S = ScoreRoot         (computed fitness scores for all species/context pairs)
```

Each fitness claim must be reproducible from those roots plus the public scoring ruleset. The scorekeeper publishes the epoch root. Watchers have a 24-hour challenge window to prove incorrect aggregation, false oracle references, or misclassified protected-order behavior. Successful challenges slash the reporter bond and replace the root.

Requirements:

- All fitness inputs must be derived from on-chain settlement events plus approved oracle references and published classification rules.
- Protected-flow promises are binary and auditable: if a route promised private handling, the route must follow the protected path or accept penalty.
- Benchmark routes (S0 control fills) are conservative by design; they exist to compare outcomes, not to pretend every trade could receive the best imaginable quote.
- Intent and fill data underlying the roots must be available via a data availability layer (the L2's own DA for v1, dedicated DA for v1.5+).

## 26. Liquidity design: shared pair vaults

### The fragmentation problem

If LP capital is fully isolated by species, prices can diverge across species for the same pair. Cross-species arbitrage becomes parasitic rather than corrective.

### Shared pair vault with virtual allocation

Capital for each pair settles in a single **shared pair vault**. Species receive virtual allocation weights:

```
x_s = w_s * x,    y_s = w_s * y,    sum(w_s) = 1
```

Species compete over execution logic — matching rules, fee curves, batch timing — but capital settles back into a common vault. Cross-species arbitrage becomes mostly internal accounting rather than capital fragmentation.

Allocation weights w_s are updated at epoch boundaries based on fitness scores and LP preference signals. Species in probation receive capped allocation weight.

Single-species LP positions remain available for LPs who want explicit exposure to one mechanism. Optional meta-vaults can rebalance among active species according to LP risk profile and observed LP health scores. Meta-vaults are convenience wrappers, not a requirement for the core protocol.

## 27. Evolution engine

At v1, evolution occurs primarily through parameter mutation inside approved templates.

```
For each generation G and pair cluster C:
  Parents <- top_q species by Fitness in C
  Mutants <- mutate(parameters(Parents), bounded_noise)
  Candidates <- Parents union Mutants union externally sponsored proposals
  Run static checks and simulation gates
  Admit passing candidates to sandbox or probation
  Reduce flow share of bottom_k species
  Retire species below threshold for K generations
```

### Mutation mechanics

Mutation is local and bounded:

```
theta_s' = project_C(theta_s + epsilon_s),    epsilon_s ~ N(0, Sigma)
```

where project_C clips the result back into the constitutional safety set C.

Default mutations are small: fee-band adjustments, batch-interval adjustments, oracle-band changes, inventory-cap changes, or solver-timeout changes. Code-family crossover is reserved for v2+ and should only occur after substantial operational evidence.

### Flow share update (replicator dynamics)

```
a_s^{e+1} = (1 - epsilon) * [a_s^e * exp(beta * F_s^e)] / [sum_j a_j^e * exp(beta * F_j^e)]
          + epsilon * mu_s^e
```

where epsilon is the exploration rate and mu_s^e is exploration mass reserved for new species. Beta controls selection pressure. These are constitutional parameters set by governance.

## 28. Batch clearing mathematics

For a batch-auction species on pair X/Y, let buy orders be (p_i^b, q_i^b) and sell orders be (p_j^s, q_j^s). Define cumulative demand and supply:

```
D(p) = sum_{i: p_i^b >= p} q_i^b
S(p) = sum_{j: p_j^s <= p} q_j^s
```

The executable volume at price p is:

```
V(p) = min(D(p), S(p))
```

Clearing price selection:

```
p* in argmax_p V(p)
```

Tie-breaking: minimize |D(p) - S(p)|. If still tied, choose the price nearest the signed oracle reference p^ref.

This rule makes clearing **deterministic** — less race condition, less timing edge, less room for ordering games.

## 29. Oracle policy

Execution species may use local pricing models, but scoring and safety checks rely on canonical benchmark oracles. The benchmark oracle blends robust on-chain TWAP sources with approved external feeds where necessary.

Oracle j signs attestation:

```
m_{j,t} = H_{DARWIN/Oracle/v1}(pair, t, p_{j,t}, conf_{j,t})
sigma_{j,t} <- MLDSA87.Sign(sk_j, m_{j,t})
```

Reference price is a robust statistic:

```
p^ref_t = median{p_{j,t} : Verify(pk_j, m_{j,t}, sigma_{j,t}) = 1  and  |t_now - t| <= Delta_oracle}
```

If reference feeds disagree beyond a constitutional band, the protocol enters safe mode.

## 30. Slashing

Every new species posts a bond B_s. If species s causes measurable harm:

```
slash_s = min(B_s, lambda_L * Loss_s + lambda_E * Event_s)
```

Slashable: solvers, metric reporters, and bonded actors for explicit policy failures.
Not slashable: ordinary underperformance of a species. Bad ideas lose flow; they are not automatically slashed absent misconduct.

## 31. Smart contract map

| Contract | Responsibility |
|---|---|
| IntentRegistry | Stores cancellations, nonces, and optional on-chain intent references. |
| DarwinRouter | Receives intents or route commitments and chooses the winning species. |
| SettlementHub | Verifies signatures, constraints, accounting, and executes the chosen solution atomically. |
| SpeciesRegistry | Tracks approved templates, genomes, status, and caps. |
| SpeciesFactory | Creates parameterized species instances from approved templates. |
| ScoreKeeper | Publishes epoch metric roots and handles reporter bonds. |
| ChallengeManager | Adjudicates metric disputes and slashing outcomes. |
| EvolutionManager | Updates flow weights and admits or retires species according to policy. |
| PairVault | Shared liquidity vault per pair with virtual species allocation weights. |
| DRWToken / Staking | Token issuance, bonding, and governance stake accounting. |
| Treasury / InsuranceVault | Holds protocol fee proceeds and backstop capital. |

### Interface sketch (v1)

```solidity
interface ISpecies {
    function speciesId() external view returns (bytes32);
    function templateId() external view returns (bytes32);
    function quote(Intent calldata x) external view returns (Quote memory);
    function execute(Solution calldata s) external returns (Fill memory);
    function riskState() external view returns (RiskState memory);
}

interface ISettlementHub {
    function settle(Intent calldata x, Solution calldata s) external;
    function cancel(bytes32 intentHash) external;
}

interface IPairVault {
    function deposit(address pair, uint256 amountX, uint256 amountY) external;
    function withdraw(address pair, uint256 shares) external;
    function speciesAllocation(bytes32 speciesId) external view returns (uint256 weightBps);
}
```

---

# PART III — CRYPTOGRAPHIC FOUNDATION

## 32. Design principle

**Let the market structure evolve, but do not let the cryptography improvise.** The trust layer is conservative, standardized, and swappable. Innovation belongs in routing, auctions, fitness, mutation, and selection. Conservatism belongs in signatures, KEMs, hashes, KDFs, admin trust, and upgrade paths.

"Post-quantum hardened under current assumptions" is the honest phrase. Not "quantum-proof."

## 33. Frozen PQ suite for DARWIN v1

### Signatures

| Use | Algorithm | NIST Category | Signature Size |
|---|---|---|---|
| User trading signatures (hot path) | ML-DSA-65 | 3 | 3,309 bytes |
| Validator and operator signatures | ML-DSA-87 | 5 | 4,627 bytes |
| Cold recovery key and network root | SLH-DSA-SHAKE-256s | 5 (hash-based) | 29,792 bytes |
| Cold path policy | Dual: ML-DSA-87 AND SLH-DSA | 5 (both families) | — |

SLH-DSA is the backup signature method in case ML-DSA is later found vulnerable. It belongs in cold-path recovery and governance, not per-trade flow.

### Key encapsulation

| Use | Algorithm | NIST Category | Ciphertext Size |
|---|---|---|---|
| Session key establishment (hot path) | ML-KEM-768 | 3 | 1,088 bytes |
| Long-lived cold secrets | ML-KEM-1024 | 5 | 1,568 bytes |

NIST selected HQC in 2025 as a backup KEM family. SP 800-227 approves combining multiple shared secrets with a standard key combiner. DARWIN reserves a hybrid slot for v1.5+ even though v1 ships with ML-KEM only.

### Hash and KDF stack

| Use | Primitive | Reference |
|---|---|---|
| All transcript, commitment, account, Merkle, and KDF operations | cSHAKE256, TupleHash256, KMAC256 | SP 800-185 |
| Keyed PRF/MAC | KMAC256 | SP 800-185, SP 800-56C |

Every DARWIN object is a tuple, not an ambiguous byte blob. TupleHash256 eliminates encoding ambiguity attacks by construction.

### Symmetric encryption

| Use | Primitive |
|---|---|
| Encrypted intents and operator channels | AES-256-GCM with KMAC-derived nonces |

### Explicitly not used

- **XMSS/LMS** for ordinary users — stateful, requires HSM key management.
- **Threshold PQ signatures** — NIST's threshold effort was still at first call for submissions in January 2026. v1 uses explicit k-of-n signature sets at the protocol layer.
- **Pairing-based SNARKs** — quantum-vulnerable assumptions. Future ZK needs use STARK-family (transparent, hash-based) proofs.

### Suite identifier

```
suite_id = H_{DARWIN/Suite/v1}(MLDSA65, MLDSA87+SLH256s, MLKEM768, TupleHash256, KMAC256, AES256GCM, 256)
```

Every object in the system includes suite_id. Suite upgrades are constitutional actions requiring cold-path authorization.

## 34. Hash foundation

Define:

```
H_S(x_1, ..., x_m) := TupleHash256((x_1, ..., x_m), 256, S)
M_S(K, X, L)       := KMAC256(K, X, L, S)
```

Domain-separated hashing is used everywhere. Every DARWIN object type gets its own domain string. This keeps the trust surface small: one hash family, many domains, zero ambiguity.

## 35. Account model

Use **32-byte addresses**, not 20-byte Ethereum-style addresses.

### Account policy

```
P = H_{DARWIN/AcctPolicy/v1}(pk_hot, pk_cold, C_hot, L_hot, Delta_recovery, M)
```

where:
- C_hot is the hot-key capability set (what actions the hot key may authorize)
- L_hot is the hot withdrawal/trade cap
- Delta_recovery is the recovery timelock
- M is multisig metadata

### Address derivation

```
addr = H_{DARWIN/Address/v1}(chain_id, P)
```

The address commits to **policy**, not just to one public key.

### Hot-path acceptance (trading)

```
m_tx = H_{DARWIN/Tx/v1}(suite_id, chain_id, nonce, expiry, action, payload, fee_limit)
sigma_hot <- MLDSA65.Sign(sk_hot, m_tx)

Accept_hot(tx) = Verify_MLDSA65(pk_hot, m_tx, sigma_hot) == 1
              AND action in C_hot
              AND value <= L_hot
```

### Cold-path acceptance (recovery, constitutional actions)

```
Accept_root(tx) = Verify_MLDSA87(pk_root1, m_tx, sigma_1) == 1
               AND Verify_SLH(pk_root2, m_tx, sigma_2) == 1
               AND t_now >= t_queued + Delta_recovery
```

Fast hot key for trading. Slow, conservative, different-assumption cold root for everything else.

## 36. Encrypted intent channels

Because PQ signatures are bulky, DARWIN uses off-chain signed intents with batch settlement, not a classical per-transaction mempool.

### Intent signing

```
m_I = H_{DARWIN/Intent/v1}(suite_id, addr, I)
sigma_I <- MLDSA65.Sign(sk_hot, m_I)
```

### Encryption to solver

To send privately to a solver with ML-KEM public key ek_S:

```
(K_0, c) <- MLKEM768.Encaps(ek_S)

K_master = M_{DARWIN/KDF/v1}(K_0, H_{DARWIN/Ctx/v1}(addr, solver_id, session_id, c), 608)

Parse K_master = k_enc || k_kc || n_seed
  k_enc  : 256 bits (encryption key)
  k_kc   : 256 bits (key confirmation key)
  n_seed : 96 bits  (nonce seed)
```

For message number i:

```
n_i = M_{DARWIN/Nonce/v1}(n_seed, i, 96)
(ct_i, tag_i) = AES256-GCM.Enc_{k_enc}(n_i, aad_i, (I, sigma_I))
```

Key confirmation (mirroring SP 800-227):

```
MAC_Data = H_{DARWIN/KCData/v1}(ID_P, ID_R, c, ek_S, suite_id, extra)
MacTag = M_{DARWIN/KC/v1}(k_kc, MAC_Data, 128)
```

Intent is **signed before encryption** — confidentiality and authenticity are cleanly separated.

### Future hybrid KEM combiner

When DARWIN adds HQC later:

```
K = H_{DARWIN/KEMCombine/v1}(K_1, K_2, c_1, c_2, ek_1, ek_2, p)
```

This matches NIST's approved composite-key-establishment pattern from SP 800-227.

## 37. Commitments and authenticated state

Generic commitment:

```
Com(x; r) = H_{DARWIN/Commit/v1}(x, r)
```

Merkle leaf:

```
L_i = H_{DARWIN/Leaf/v1}(i, type_i, x_i)
```

Internal node:

```
N = H_{DARWIN/Node/v1}(L, R)
```

The canonical state root, order root, fitness root, and oracle root are all domain-separated Merkle roots built on the same hash stack.

## 38. Consensus and block structure (v2)

Block digest:

```
h_t = H_{DARWIN/Block/v1}(height_t, h_{t-1}, stateRoot_t, txRoot_t,
                           fitnessRoot_t, oracleRoot_t, randRoot_t, suite_id)
```

Validator i signs:

```
sigma_i <- MLDSA87.Sign(sk_i, h_t)
```

Finality when:

```
sum_{i in Q_t} stake_i >= (2/3) * sum_i stake_i
```

and every sigma_i in Q_t verifies. The finality certificate is a set of individual PQ signatures, not a threshold signature.

## 39. Upgrade authorization (constitutional)

```
u = H_{DARWIN/Upgrade/v1}(new_suite_id, code_root, activation_height)
```

Accepted only if:

```
sum_{i in Q_u} stake_i >= q
AND forall i in Q_u: Verify_MLDSA87(pk_i, u, sigma_i) == 1
AND Verify_SLH(pk_cold_root, u, sigma_cold) == 1
AND t_now >= t_queued + Delta
```

---

# PART IV — SIMULATOR SPECIFICATION

## 40. Purpose

The simulator answers the question that must be answered before any code ships:

> Does the evolutionary engine converge to better outcomes than a static DEX, resist gaming, and produce sustainable revenue?

If the answer is no, everything else is academic.

## 41. Simulator architecture

```
┌─────────────────────────────────────────────────────┐
│                  DARWIN Simulator                     │
│                                                       │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐ │
│  │ Replay   │──►│ Router   │──►│ Species Engines   │ │
│  │ Engine   │   │ + Control│   │ S0,S1,S2,S3,S4   │ │
│  │          │   │ Reserve  │   │ + Mutants         │ │
│  └──────────┘   └──────────┘   └────────┬─────────┘ │
│       │                                  │           │
│       │         ┌──────────┐   ┌────────▼─────────┐ │
│       │         │ Fitness  │◄──│ Settlement Sim    │ │
│       │         │ Scorer   │   │ (fills, markout)  │ │
│       │         └────┬─────┘   └──────────────────┘ │
│       │              │                               │
│       │         ┌────▼─────┐                         │
│       │         │Evolution │                         │
│       │         │ Manager  │                         │
│       │         │(replicator│                        │
│       │         │ dynamics) │                        │
│       │         └──────────┘                         │
│       │                                              │
│  ┌────▼─────────────────────────────────────────┐   │
│  │              Metrics Collector                │   │
│  │  Revenue, fitness convergence, species        │   │
│  │  diversity, LP PnL, trader surplus, gaming    │   │
│  │  resistance, parameter stability              │   │
│  └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

## 42. Data source

Replay historical on-chain DEX order flow. Primary dataset:

- **Uniswap V3 ETH/USDC** on Ethereum mainnet and Arbitrum: high-volume, well-understood pair with known MEV characteristics.
- **Uniswap V3 WBTC/ETH**: volatile correlated pair.
- **USDC/USDT**: stable pair (different dynamics, low vol, tight spreads).

Data required per swap:
- Block number, timestamp
- Token pair, direction, amount in/out
- Gas used, gas price
- Price before and after (for markout)
- Pool state (tick, liquidity, fee tier)

Source: archived Ethereum/Arbitrum node or public datasets (e.g., Dune, Flipside, raw event logs).

Period: minimum 6 months of continuous data. Include at least one high-volatility event (e.g., major crash, FOMC-driven moves, memecoin season).

## 43. Species implementations for simulation

Each species is a deterministic function: given pool state + incoming order, produce a fill (or no fill) and updated state.

### S0 — Sentinel (baseline)

Standard concentrated liquidity AMM with dynamic fee in range [5, 100] bps. Fee adjusts with 1-minute realized volatility. This is the control group for all counterfactual fitness measurement.

### S1 — Batch

Accumulate orders for batchIntervalMs (default 5000ms). Clear at uniform price using the clearing algorithm from Section 28. Crosses internal flow before touching the pool.

### S2 — Adaptive

Oracle-aware curve that adjusts:
- Effective tick range based on rolling volatility
- Fee based on vol + toxicity estimator (markout of recent fills)
- Inventory skew penalty when imbalanced beyond inventoryCapPct

### S3 — Patience

Accepts orders with latencyMax > 60s. Splits into time slices. Each slice fills at the best available price within its window. Patience rebate = (baseline_fee - patience_fee) returned to user.

### S4 — RFQ

Simulated as a solver that quotes based on inventory + oracle + spread model. Solver quality varies (simulate good and bad solvers to test fitness scoring).

## 44. Simulation experiments

### Experiment 1: Convergence

**Question:** Do species flow shares converge to a stable equilibrium, oscillate, or collapse to monoculture?

**Method:** Run 180 simulated days. Vary beta (selection pressure) from 0.5 to 5.0. Vary epsilon (exploration rate) from 0.02 to 0.20. Track species allocation weights over time.

**Success criteria:** For at least one (beta, epsilon) region, flow shares stabilize within 30 generations with the best-performing species holding 25-60% share (not 100%, not uniform).

### Experiment 2: Counterfactual vs. naive fitness

**Question:** Does counterfactual scoring (uplift vs. S0) produce different species rankings than naive scoring (raw performance)?

**Method:** Run identical order flow with both scoring methods. Compare which species gain flow share under each.

**Success criteria:** At least one species that ranks well under naive scoring ranks poorly under counterfactual scoring (or vice versa), demonstrating that the counterfactual correction matters.

### Experiment 3: Gaming resistance

**Question:** Can a malicious species sponsor inflate fitness through wash trading?

**Method:** Inject a "gaming agent" that:
- Creates 50 sybil addresses
- Routes small wash trades through a target species
- Attempts to inflate trader surplus by trading against itself at favorable prices

Run with and without anti-gaming rules (per-entity caps, trimmed mean, minimum external fill count, self-referential flow detection).

**Success criteria:** With anti-gaming rules, the gaming agent's species does NOT gain materially more flow share than a non-gaming equivalent.

### Experiment 4: Revenue sustainability

**Question:** Does protocol revenue remain positive as species evolve toward lower fees?

**Method:** Run 360 simulated days with revenue floor (f_min, tau_0) enabled and disabled. Track total protocol revenue per epoch.

**Success criteria:** With revenue floor enabled, protocol revenue per unit notional never falls below tau_0. Without revenue floor, demonstrate that fee compression does occur (validating the need for the floor).

### Experiment 5: Volatility regime adaptation

**Question:** Do different species dominate in different volatility regimes?

**Method:** Segment replay data into low-vol, medium-vol, and high-vol periods. Track which species gain flow share in each regime.

**Success criteria:** Species rankings differ across volatility regimes, demonstrating that the system correctly discovers context-dependent optima rather than a single "best" mechanism.

### Experiment 6: Mutation landscape

**Question:** What mutation step sizes produce productive evolution vs. noise vs. stagnation?

**Method:** Vary the covariance matrix Sigma of the mutation operator. Track the rate at which mutants enter Active status and the fitness improvement per generation.

**Success criteria:** Identify a Sigma range where mutant admission rate is 10-30% (not 0% stagnation, not 90% chaos).

### Experiment 7: LP welfare

**Question:** Do LPs in the shared pair vault earn more than passive hold under evolutionary species competition?

**Method:** Compare LP returns under DARWIN routing vs. a static Uniswap V3 pool with the same initial parameters, over the same order flow.

**Success criteria:** DARWIN LP returns >= static LP returns over 90+ day windows, after accounting for impermanent loss and fees.

## 45. Simulator output format

Each simulation run produces:

```
{
  "run_id": "...",
  "config": {
    "beta": ..., "epsilon": ..., "rho": ..., "f_min": ...,
    "tau_0": ..., "tau_f": ..., "generation_epochs": ...,
    "anti_gaming": true/false
  },
  "epochs": [
    {
      "epoch": 0,
      "species_weights": {"S0": 0.20, "S1": 0.15, ...},
      "fitness_scores": {"S0": 0.0, "S1": 0.034, ...},
      "protocol_revenue_usd": ...,
      "lp_pnl_vs_hold_bps": ...,
      "trader_surplus_vs_baseline_bps": ...,
      "total_notional_usd": ...,
      "fill_rate": ...,
      "adv_selection_bps": ...
    },
    ...
  ],
  "summary": {
    "converged": true/false,
    "convergence_epoch": ...,
    "final_herfindahl": ...,     // species concentration index
    "total_revenue_usd": ...,
    "mean_trader_surplus_bps": ...,
    "mean_lp_pnl_bps": ...,
    "gaming_resistance_score": ...
  }
}
```

## 46. Implementation language and framework

- **Language:** Rust (performance for multi-month replay) or Python (faster iteration, acceptable for initial experiments).
- **Recommendation:** Start with Python + NumPy for rapid experiment iteration. Port hot paths to Rust if replay speed becomes a bottleneck.
- **Framework:** No external simulation framework required. The simulator is a deterministic event loop over historical trade data.

## 47. What the simulator does NOT need

- Real PQ signatures (irrelevant to economic behavior)
- Gas simulation (use historical gas data as a cost input)
- Network latency (assume all species see the same data per block)
- Real smart contracts (simulate state transitions directly)

The simulator tests the **economic engine**, not the **execution stack**.

---

# APPENDICES

## A. Canonical glossary

| Term | Meaning |
|---|---|
| Species | A parameterized market design running inside an approved template family. |
| Genome | The disclosed parameter vector that defines a species instance. |
| Context bucket | A combination of pair cluster, size bucket, volatility regime, and urgency class. |
| Fitness | Composite counterfactual performance score used for future routing and species ranking. |
| Probation | Low-cap live testing stage for new or mutated species. |
| Safe mode | Conservative operating subset triggered by stress or policy breach. |
| DRW | Protocol token used for bonding, governance, and accountability. |
| Dual envelope | Intent signed with both PQ (ML-DSA) and classical (ECDSA) keys, cryptographically bound. |
| Control reservation | Fraction rho of flow randomly assigned to S0 for counterfactual baseline measurement. |
| Replicator dynamics | Evolutionary flow-share update rule where fitter species gain share exponentially. |

## B. Implementation sequencing

1. **Simulator** — replay engine, species implementations, fitness scorer, evolution manager, metrics collector. Validate convergence, gaming resistance, and revenue sustainability.
2. **PQ intent signing SDK** — ML-DSA-65 key generation and signing, TupleHash256 domain-separated intent hashing, ML-KEM-768 encrypted channels, account policy hash and 32-byte address derivation.
3. **S0 baseline + SettlementHub + IntentRegistry** on EVM testnet — dual-envelope intents, ECDSA verification on-chain, PQ verification off-chain by solvers.
4. **S1 batch species + ScoreKeeper** — challengeable score roots, counterfactual fitness computation.
5. **DRW bonds** for solvers and reporters.
6. **S3 patience lane + limited sponsor proposals** within approved templates.
7. **S2 adaptive species + shared pair vault** — full evolutionary loop live.
8. **Canary mainnet** on one EVM L2, limited pairs, no arbitrary template additions.
9. **v1 mainnet** with DRW bonding, score challenges, and parameter mutations inside approved templates.
10. **v1.5** — sovereign rollup with ML-DSA precompile, score commitments in rollup state.
11. **v2** — native PQ execution layer, drop ECDSA envelope, full PQ account model.

## C. Default parameters

| Parameter | Reference default | Rationale |
|---|---|---|
| Chain target | One EVM L2 (low fees, deep stablecoin liquidity) | Ship fast, iterate. |
| Epoch length | 24 hours | Enough data per epoch for meaningful fitness. |
| Generation length | 7 epochs | One week of observation before evolutionary action. |
| Control reservation (rho) | 5% of eligible notional per cluster | Enough for statistical significance without excessive cost. |
| Exploration floor | 10% of eligible notional per cluster | Ensure new species get live data. |
| Baseline flow floor | 20% of eligible notional per cluster | S0 always available as fallback + control. |
| Max active flow share | 35% for any single species in first 90 days | Prevent premature monoculture. |
| Probation flow cap | 5% per eligible cluster | Bound risk of new species. |
| Batch interval (S1) | 5 seconds | Short enough for usability, long enough for crossing. |
| Metric challenge window | 24 hours | Time for watchers to verify and challenge. |
| Protocol take (tau_f) | 15% of fee component | Standard DeFi range. |
| Minimum fee (f_min) | 0.5 bps of notional | Prevent fee race to zero. |
| Notional floor (tau_0) | 0.1 bps of notional | Ensure nonzero revenue even at minimum fees. |
| Selection pressure (beta) | To be determined by simulation | Experiment 1 deliverable. |
| Exploration rate (epsilon) | To be determined by simulation | Experiment 1 deliverable. |
| Mutation covariance (Sigma) | To be determined by simulation | Experiment 6 deliverable. |
| Anti-gaming: per-entity cap | 5% of species score per epoch | Prevent wash-trading inflation. |
| Anti-gaming: minimum fills | 50 distinct external addresses | Prevent low-N score manipulation. |
| Anti-gaming: markout delay (tau) | 30 seconds | Capture deferred adverse selection. |

## D. Document history

| Version | Date | Changes |
|---|---|---|
| 0.1 | 2026-04-04 | Initial whitepaper (Part I + Part II). |
| 0.1-PQ | 2026-04-04 | Post-quantum cryptographic foundation (standalone). |
| 0.2 | 2026-04-04 | Merged canonical spec. Added: versioned trust model, dual-envelope intents, counterfactual fitness, anti-gaming rules, revenue floor, shared pair vaults, data availability requirements, simulator specification. |

---

*End of DARWIN v0.2 Canonical Specification.*
