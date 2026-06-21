# BlueLotus NITE-PEI Engine
## Integrated Thesis: News Impact and Thesis Engine for PEI Probability Updating

**Principal Author:** CIO Soh Wee Kian · BlueLotus Fund Singapore  
**Integrated Contributions:** Dr. Claude Code · Windows Platform Team  
**Classification:** INTERNAL ACADEMIC — LAW-BOUND UNDER ACTIVE GOVERNANCE PACK  
**Prepared for:** Dr. Codex · Application Engineering Handoff  
**Date:** June 2026  

---

```
CIO_ONLY_MANUAL: TRUE
ORDER_ROUTING_ENABLED: FALSE
LLM_ORDER_GENERATION: FALSE
THESIS_AUTHORITY: RESEARCH / PROPOSAL / PREPARATION ONLY
MANUAL_EXECUTION_REQUIRED: TRUE
```

---

> **A note before the thesis begins.**
>
> This document is the product of two intellectual threads converging. CIO Soh Wee Kian
> contributed the NITE-PEI Engine architecture — a 20-step deterministic workflow for
> converting news events into live thesis probability updates using Bayesian inference.
> Dr. Claude Code, having studied the BlueLotus V3 codebase and the prior Shannon–Thorp
> Refinement (STR) thesis, contributed six architectural extensions that couple NITE-PEI
> to the existing Kelly ESM, Shannon SEM, Brier calibration loop, kill-condition scoring,
> canonical data contract, and hedge doctrine.
>
> The purpose of this integrated document is **application engineering**, not further
> theoretical elaboration. Every section ends with an engineering prescription — files
> to create, schemas to extend, operators to wire. Dr. Codex receives this as a
> build-ready specification, not an aspirational research note.
>
> Nothing in this thesis executes a trade. Nothing overrides the CIO.
> The thesis advises and prepares. The CIO decides and executes.

---

## Table of Contents

| Part | Title | Sections |
|------|-------|----------|
| I | Foundations and Problem Statement | §1–§3 |
| II | The NITE-PEI Engine (CIO Thesis) | §4–§10 |
| III | Dr. Claude Code's Six Integrated Contributions | §11–§16 |
| IV | Unified Architecture: 11 Integration Points | §17 |
| V | Extended Doctrine | §18 |
| VI | Implementation Roadmap | §19–§24 |

---

# PART I — FOUNDATIONS

## §1 · The Problem This Engine Solves

BlueLotus V3, as of June 2026, is capable of:

- Collecting 9-lens market data from deterministic operators
- Running 9-agent Qwen analysis council per cycle
- Maintaining a live thesis registry (Gold Thesis, Space Thesis, etc.)
- Detecting kill conditions qualitatively
- Scoring forecasts via the Brier ledger

What it **cannot do** deterministically is:

> *When a news event arrives that is relevant to an active thesis, automatically update that thesis's probability using a rigorous Bayesian formula, produce a quantified kill risk score, and feed the updated probability directly into the Kelly position-sizing formula.*

This is the gap NITE-PEI closes.

The cost of this gap in the fund's own operating record is concrete: on 18 June 2026, a confirmed Iran-Hormuz de-escalation MOU arrived during live market hours. The Chief Strategist page showed `NEUTRAL (0)` at one timestamp and `RISK ON (+5)` forty-four minutes later. Neither reading was wrong. But neither had been produced by a quantified update to the Gold Thesis probability using the likelihood that a Hormuz de-escalation event would shift the gold supply-side assumption. A system with NITE-PEI would have produced: `P(Gold Thesis | Hormuz de-escalation) = prior × LR_HormuzDeescalation_GoldThesis`.

That is a number. It can be stored. It can feed Kelly. It can trigger or suppress a kill condition. It can be Brier-graded when the thesis resolves. Qualitative "regime shift" language cannot do any of these things.

---

## §2 · Relationship to Prior Theses

NITE-PEI is the **fourth layer** of the BlueLotus theoretical stack:

| Layer | Thesis | Primary Author | Core Contribution |
|-------|--------|----------------|-------------------|
| 1 | PEI (Prospective Event Intelligence) | Dr. Claude Chat Opus 4.8 | Event scenario trees, kill conditions, Hawkes excitation, reflexive suppression |
| 2 | STR (Shannon–Thorp Refinement) | Dr. Claude Chat Opus 4.8 + Dr. ChatGPT 5.5 | Signal entropy (SEM) + Kelly edge sizing (ESM) |
| 3 | Contradiction Governance | Dr. Codex | Silent contradiction detection across all institutional layers |
| 4 | **NITE-PEI (this thesis)** | **CIO Soh Wee Kian + Dr. Claude Code** | **Bayesian news-to-thesis probability updating + Kelly-NITE coupling** |

NITE-PEI does not replace any prior layer. It is the **coupling mechanism** that connects them: news events → thesis probability → Kelly fraction → position target.

---

## §3 · Governing Constraints

These constraints govern all engineering work derived from this thesis.
They are not negotiable.

| Constraint | Rule |
|-----------|------|
| BlueLotus Law | No LLM generates orders. No system routes capital. |
| CIO_ONLY_MANUAL | Every portfolio action requires explicit CIO decision. |
| Append-only memory | NITE-PEI writes new records. It never modifies or deletes. |
| No V2 contamination | NITE-PEI operates only on V3 data structures. |
| Canonical data contract | All outputs write to existing V3 JSON schemas or defined extensions thereof. |
| Hedge doctrine (BLV3-DOCTRINE-006 adjacent) | VXX/VIXY never touched by de-risk logic. Separate gate. |
| Falsifiability | Every NITE-PEI probability estimate must be Brier-gradeable on resolution. |

---

# PART II — THE NITE-PEI ENGINE (CIO THESIS)

## §4 · Engine Architecture Overview

**NITE-PEI** = **N**ews **I**mpact and **T**hesis **E**ngine for **PEI** Probability Updating

The engine processes a news event in a deterministic 20-step workflow, producing:

1. A quantified posterior thesis probability
2. A kill condition state update (INACTIVE → WATCH → TRIGGERED → CONFIRMED → RETIRED)
3. A CIO-facing advisory showing prior, likelihood ratio, posterior, and recommended posture

The engine is composed of **7 sub-engines**:

| Sub-Engine | Function |
|-----------|----------|
| **E1 · Event Classifier** | Classifies incoming news event by type and relevance to each active thesis |
| **E2 · Likelihood Ratio Lookup** | Retrieves the expert-defined likelihood ratio (LR) for the event-class × thesis-class pair |
| **E3 · Bayesian Updater** | Computes posterior odds from prior odds × LR |
| **E4 · Kill-Condition State Machine** | Updates kill condition state based on posterior probability crossing thresholds |
| **E5 · Brier Calibration Loop** | After resolution: compares predicted P vs. outcome; updates LR table |
| **E6 · Thesis Registry Writer** | Writes prior, posterior, delta, LR used, and event reference to thesis_registry.yaml |
| **E7 · CIO Advisory Renderer** | Renders human-readable advisory showing the probability update and its inputs |

---

## §5 · The 20-Step Deterministic Workflow

```
─────────────────────────────────────────────────────────────────────────────
NITE-PEI: 20-STEP DETERMINISTIC PROCESSING WORKFLOW
─────────────────────────────────────────────────────────────────────────────

PHASE 1 — EVENT INGESTION (Steps 1–4)
─────────────────────────────────────
  Step 1   Ingest raw news event from operator layer (structured JSON)
           Input fields: headline, source_tier, timestamp_sgt, ticker_tags[]
           Operator: news_ingest_operator.py (existing)

  Step 2   Validate source tier (T1–T4 per source hierarchy)
           If source_tier == T4: apply noise_discount_factor = 0.5
           If source_tier not in registry: log UNKNOWN_SOURCE, use T3 default

  Step 3   Classify event type using Event Taxonomy (§6)
           Output: event_class (e.g., CENTRAL_BANK_HAWKISH, GEOPOLITICAL_DEESCALATION)
           Operator: E1 · Event Classifier

  Step 4   Identify affected thesis IDs from thesis_registry.yaml
           Match: event.ticker_tags[] ∩ thesis.affected_tickers[]
           Also match: event.event_class against thesis.catalyst_watch_list[]
           Output: affected_thesis_ids[] (may be empty — not every event hits a thesis)

PHASE 2 — BAYESIAN UPDATE (Steps 5–10)
─────────────────────────────────────────
  Step 5   For each affected thesis: retrieve current prior probability P_prior
           Source: thesis_registry.yaml → field: current_probability
           If field missing: P_prior = 0.5 (baseline prior, log as PRIOR_DEFAULT)

  Step 6   Look up Likelihood Ratio (LR) from LR Table (§7)
           Key: (event_class, thesis_id) or (event_class, thesis_type)
           Fallback: (event_class, "ANY") for generic cross-thesis ratios
           If no entry found: LR = 1.0 (no information, no update)

  Step 7   Apply source-tier discount to LR
           LR_adjusted = LR × (1 - noise_discount_factor)
           For T1 source: LR_adjusted = LR × 1.0 (no discount)
           For T4 source: LR_adjusted = LR × 0.5 (50% discount on LR impact)

  Step 8   Compute posterior odds (E3 · Bayesian Updater)
           Prior odds          = P_prior / (1 - P_prior)
           Posterior odds      = Prior odds × LR_adjusted
           P_posterior         = Posterior odds / (1 + Posterior odds)

  Step 9   Compute delta
           delta_P             = P_posterior - P_prior

  Step 10  Apply boundary clamp
           P_posterior = max(0.05, min(0.95, P_posterior))
           [Rationale: no thesis reaches absolute certainty from a single event]

PHASE 3 — KILL CONDITION SCORING (Steps 11–13)
───────────────────────────────────────────────
  Step 11  Load kill condition definitions for affected thesis
           Source: thesis_registry.yaml → kill_conditions[]
           Each kill condition has: kill_id, kill_weight, kill_threshold_P

  Step 12  For each kill condition in the thesis:
           — Retrieve P(kill_i) = current probability that kill condition i is met
             (This may be from a prior NITE-PEI cycle or from operator flags)
           — If kill condition event_class matches current event_class:
               Update P(kill_i) = P_posterior for that kill pathway
           — Otherwise: P(kill_i) unchanged from last cycle

  Step 13  Update kill condition state machine (E4):
           IF P(kill_i) < 0.10: state = INACTIVE
           IF P(kill_i) ≥ 0.10: state = WATCH
           IF P(kill_i) ≥ 0.35: state = TRIGGERED
           IF P(kill_i) ≥ 0.65: state = CONFIRMED
           IF thesis_resolved == True: state = RETIRED

PHASE 4 — CANONICAL WRITE (Steps 14–16)
─────────────────────────────────────────
  Step 14  Write Brier forecast record (pre-resolution)
           Operator: E5 · Brier Calibration Loop (write phase)
           Record: {thesis_id, event_id, P_prior, LR_used, P_posterior,
                    created_at_sgt, resolution_pending: true}

  Step 15  Write thesis probability update (E6 · Thesis Registry Writer)
           File: config/thesis_registry.yaml (append new version record)
           Fields: prior, LR_used, posterior, delta_P, event_ref, timestamp_sgt,
                   kill_condition_states{}, source_tier, noise_discount_applied

  Step 16  Write to V3 canonical JSON output field
           (See §13 for canonical schema extension)

PHASE 5 — CIO ADVISORY (Steps 17–20)
──────────────────────────────────────
  Step 17  Compute posture recommendation (deterministic rule):
           IF delta_P ≥ +0.15 AND kill_state ∈ {INACTIVE, WATCH}:
             posture = "THESIS_STRENGTHENED — CIO_REVIEW_FOR_ADD"
           IF delta_P ≤ -0.15 AND kill_state ∈ {TRIGGERED, CONFIRMED}:
             posture = "THESIS_WEAKENED — CIO_REVIEW_FOR_REDUCE"
           IF |delta_P| < 0.15:
             posture = "THESIS_UNCHANGED — MONITOR"
           IF kill_state == CONFIRMED:
             posture = "KILL_CONDITION_CONFIRMED — CIO_DECISION_REQUIRED"
           IF kill_state == RETIRED:
             posture = "THESIS_RETIRED — CLOSE_SLEEVE_PENDING_CIO"

  Step 18  Render CIO Advisory block (E7 · CIO Advisory Renderer):
           — Event: [headline, source_tier, timestamp]
           — Thesis: [thesis_id, thesis_name]
           — Prior P: [value] → Posterior P: [value] (Δ = [delta_P])
           — LR used: [value] (source: LR Table entry [key])
           — Kill conditions: [state per kill_id]
           — Posture recommendation: [from Step 17]
           — Action gate: MANUAL — NO AUTOMATED ORDER

  Step 19  Append advisory to Chief Strategist page (existing publisher)
           Section: "NITE-PEI Thesis Updates" (new section in HTML renderer)

  Step 20  Log cycle completion to nite_pei_cycle_log.json
           Fields: {cycle_id, event_id, thesis_ids_updated[], 
                    max_delta_P, kill_states_changed[], processing_ms}

─────────────────────────────────────────────────────────────────────────────
```

---

## §6 · Event Taxonomy (Event Classifier — E1)

The Event Classifier maps incoming news events to a structured taxonomy. This taxonomy drives LR Table lookup in E2.

```yaml
# nite_pei/event_taxonomy.yaml

event_classes:

  # Monetary Policy
  CENTRAL_BANK_HAWKISH:
    description: "Rate hike, hawkish forward guidance, QT acceleration"
    typical_thesis_impact: NEGATIVE for growth, NEGATIVE for gold (short-term)
  CENTRAL_BANK_DOVISH:
    description: "Rate cut, pivot signal, QE expansion"
    typical_thesis_impact: POSITIVE for growth, POSITIVE for gold (medium-term)
  CENTRAL_BANK_NEUTRAL:
    description: "Holds with no guidance change"
    typical_thesis_impact: LR=1.0 (no update)

  # Geopolitical
  GEOPOLITICAL_ESCALATION:
    description: "Military action, sanctions, supply-route threat"
    typical_thesis_impact: POSITIVE for gold, NEGATIVE for space-tech supply chain
  GEOPOLITICAL_DEESCALATION:
    description: "Ceasefire, MOU, diplomatic resolution"
    typical_thesis_impact: NEGATIVE for gold (short-term), POSITIVE for space infra
  SANCTIONS_NEW:
    description: "New international sanctions imposed"
    typical_thesis_impact: POSITIVE for gold, NEGATIVE for affected-sector thesis

  # Corporate / Sector
  EARNINGS_BEAT_MATERIAL:
    description: "EPS beat > 10% vs consensus, guidance raised"
    typical_thesis_impact: POSITIVE for company-specific thesis
  EARNINGS_MISS_MATERIAL:
    description: "EPS miss > 10% vs consensus, guidance cut"
    typical_thesis_impact: NEGATIVE for company-specific thesis
  SECTOR_CONTRACT_WIN:
    description: "Government or large institutional contract awarded"
    typical_thesis_impact: POSITIVE for sector thesis
  SECTOR_CONTRACT_LOSS:
    description: "Contract lost to competitor or cancelled"
    typical_thesis_impact: NEGATIVE for sector thesis
  REFLEXIVE_SUPPRESSION:
    description: "Capital raise or liquidity event depresses proxy without invalidating thesis"
    typical_thesis_impact: SUPPRESS (price move, not thesis move — see PEI §Reflexive Suppression)

  # Macro / Inflation
  INFLATION_ABOVE_EXPECTATION:
    description: "CPI/PCE above consensus, hawkish re-pricing"
    typical_thesis_impact: POSITIVE for gold, NEGATIVE for rate-sensitive growth
  INFLATION_BELOW_EXPECTATION:
    description: "CPI/PCE below consensus, dovish re-pricing"
    typical_thesis_impact: NEGATIVE for gold (short-term), POSITIVE for tech
  RECESSION_SIGNAL:
    description: "Inverted yield curve, GDP contraction, PMI collapse"
    typical_thesis_impact: POSITIVE for gold and cash, NEGATIVE for cyclicals
  LIQUIDITY_EXPANSION:
    description: "Fed repo, TGA drawdown, global central bank expansion"
    typical_thesis_impact: POSITIVE for risk assets

  # Space / Technology
  LAUNCH_SUCCESS:
    description: "Orbital launch succeeds, milestone achieved"
    typical_thesis_impact: POSITIVE for space thesis
  LAUNCH_FAILURE:
    description: "Launch anomaly, vehicle loss"
    typical_thesis_impact: NEGATIVE for space thesis
  REGULATORY_APPROVAL:
    description: "FAA, FCC, DOD, SEC approval for key program"
    typical_thesis_impact: POSITIVE for affected-company thesis
  REGULATORY_REJECTION:
    description: "Permit denied, program grounded"
    typical_thesis_impact: NEGATIVE, possible kill condition trigger

  # Quantum / Emerging Tech
  QUANTUM_MILESTONE:
    description: "Qubit count record, error rate improvement, peer-reviewed breakthrough"
    typical_thesis_impact: POSITIVE for quantum thesis
  QUANTUM_COMPETITOR_ADVANCE:
    description: "Competitor achieves milestone first — changes relative positioning"
    typical_thesis_impact: VARIES (may strengthen sector thesis, weaken single-name)
```

---

## §7 · The Likelihood Ratio Table (E2)

The LR Table is the quantitative heart of NITE-PEI. Each cell defines how strongly an event of the given class shifts the probability of the thesis in a given direction.

**LR > 1.0**: Event is evidence FOR the thesis  
**LR < 1.0**: Event is evidence AGAINST the thesis  
**LR = 1.0**: Event carries no information about the thesis  

Values are **expert-initialized** and **Brier-calibrated** (see §15 for calibration mechanics).

```yaml
# nite_pei/likelihood_ratio_table.yaml
# Schema: lr_table[event_class][thesis_type] = {lr, confidence, calibration_n, last_calibrated_sgt}
# confidence: LOW (n<10), MEDIUM (10-30), HIGH (>30)

lr_table:

  CENTRAL_BANK_HAWKISH:
    GOLD_THESIS:          {lr: 0.75, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    SPACE_THESIS:         {lr: 0.85, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    QUANTUM_THESIS:       {lr: 0.85, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    BANK_THESIS:          {lr: 1.10, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    CASH_POSITION_THESIS: {lr: 1.20, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  CENTRAL_BANK_DOVISH:
    GOLD_THESIS:          {lr: 1.30, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    SPACE_THESIS:         {lr: 1.15, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    QUANTUM_THESIS:       {lr: 1.15, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    BANK_THESIS:          {lr: 0.90, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  GEOPOLITICAL_ESCALATION:
    GOLD_THESIS:          {lr: 1.40, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    SPACE_THESIS:         {lr: 0.90, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    BANK_THESIS:          {lr: 0.85, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    CASH_POSITION_THESIS: {lr: 1.25, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  GEOPOLITICAL_DEESCALATION:
    GOLD_THESIS:          {lr: 0.80, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    SPACE_THESIS:         {lr: 1.10, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    BANK_THESIS:          {lr: 1.10, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  INFLATION_ABOVE_EXPECTATION:
    GOLD_THESIS:          {lr: 1.35, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    BANK_THESIS:          {lr: 0.85, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    SPACE_THESIS:         {lr: 0.90, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  INFLATION_BELOW_EXPECTATION:
    GOLD_THESIS:          {lr: 0.80, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    BANK_THESIS:          {lr: 1.10, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
    SPACE_THESIS:         {lr: 1.15, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  REFLEXIVE_SUPPRESSION:
    ANY:                  {lr: 1.00, confidence: HIGH, calibration_n: 999,
                           note: "Reflexive suppression events carry LR=1.0 by definition — price moves, thesis unchanged"}

  LAUNCH_SUCCESS:
    SPACE_THESIS:         {lr: 1.25, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
  LAUNCH_FAILURE:
    SPACE_THESIS:         {lr: 0.70, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  QUANTUM_MILESTONE:
    QUANTUM_THESIS:       {lr: 1.30, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
  QUANTUM_COMPETITOR_ADVANCE:
    QUANTUM_THESIS:       {lr: 0.90, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  EARNINGS_BEAT_MATERIAL:
    ANY:                  {lr: 1.20, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
  EARNINGS_MISS_MATERIAL:
    ANY:                  {lr: 0.75, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  SECTOR_CONTRACT_WIN:
    ANY:                  {lr: 1.25, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
  SECTOR_CONTRACT_LOSS:
    ANY:                  {lr: 0.75, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}

  REGULATORY_APPROVAL:
    ANY:                  {lr: 1.30, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
  REGULATORY_REJECTION:
    ANY:                  {lr: 0.65, confidence: LOW, calibration_n: 0, last_calibrated_sgt: null}
```

> **Engineering note for Dr. Codex:** All `confidence: LOW` entries have `calibration_n: 0` at initialization.
> The Brier Calibration Loop (E5 / §15) will update `calibration_n` and `lr` after each resolved event.
> No entry should be treated as reliable until `calibration_n ≥ 10` (MEDIUM confidence).
> The UI should surface confidence level to the CIO alongside every LR-based update.

---

## §8 · The Bayesian Updater (E3)

### Core Formula

```
Prior odds        = P_prior / (1 - P_prior)
Posterior odds    = Prior odds × LR_adjusted
P_posterior       = Posterior odds / (1 + Posterior odds)
P_posterior       = clamp(P_posterior, 0.05, 0.95)
```

### Sequential Updating

When multiple news events arrive in the same processing cycle, NITE-PEI applies them **sequentially** — the posterior of event N becomes the prior for event N+1.

```python
P_current = thesis.current_probability
for event in sorted(events, key=lambda e: e.timestamp_sgt):
    LR = get_lr(event.event_class, thesis.thesis_type, event.source_tier)
    prior_odds = P_current / (1 - P_current)
    posterior_odds = prior_odds * LR
    P_current = posterior_odds / (1 + posterior_odds)
    P_current = max(0.05, min(0.95, P_current))
P_posterior = P_current
```

### Interpretation Guide

| P_posterior | Interpretation | Posture |
|-------------|---------------|---------|
| ≥ 0.75 | Strong thesis support | CIO review for scaling |
| 0.55–0.74 | Moderate thesis support | HOLD, monitor |
| 0.45–0.54 | Thesis uncertain | WATCH, no new adds |
| 0.25–0.44 | Thesis weakening | CIO review for reduce |
| < 0.25 | Thesis in serious doubt | Kill condition assessment required |

---

## §9 · The Kill-Condition State Machine (E4)

### State Definitions

```
INACTIVE   — P(kill) < 0.10  — Kill condition not yet on radar
WATCH      — P(kill) ≥ 0.10  — Kill condition being monitored; no action required yet
TRIGGERED  — P(kill) ≥ 0.35  — Kill condition is live; CIO must review thesis
CONFIRMED  — P(kill) ≥ 0.65  — Kill condition confirmed; thesis is invalidated
RETIRED    — Thesis resolved  — Kill condition state archived with resolution record
```

### Transition Rules

State transitions are **monotonic by default** (INACTIVE → WATCH → TRIGGERED → CONFIRMED) but **reversible** on new evidence:
- If P(kill) drops from TRIGGERED back below 0.10: return to INACTIVE, log the reversal
- The CIO must manually confirm RETIRED state — NITE-PEI proposes, CIO decides

### Kill Condition Examples by Thesis Type

```yaml
# Defined per-thesis in thesis_registry.yaml

GOLD_THESIS:
  kill_conditions:
    - kill_id: "GOLD_KC_01"
      description: "Fed achieves sustained disinflation to 2% target + pivot rhetoric fully priced"
      kill_weight: 0.40
      event_classes_that_trigger: [CENTRAL_BANK_DOVISH, INFLATION_BELOW_EXPECTATION]
    - kill_id: "GOLD_KC_02"
      description: "Geopolitical risk premium fully eliminated — 6+ months of de-escalation"
      kill_weight: 0.35
      event_classes_that_trigger: [GEOPOLITICAL_DEESCALATION]
    - kill_id: "GOLD_KC_03"
      description: "DXY structural bull market — dollar rally structurally pressures gold"
      kill_weight: 0.25
      event_classes_that_trigger: [CENTRAL_BANK_HAWKISH]

SPACE_THESIS:
  kill_conditions:
    - kill_id: "SPACE_KC_01"
      description: "SpaceX dominates commercial launch — no remaining market share for alternatives"
      kill_weight: 0.45
      event_classes_that_trigger: [SECTOR_CONTRACT_LOSS, REFLEXIVE_SUPPRESSION]
    - kill_id: "SPACE_KC_02"
      description: "DOD / NASA budget frozen or cut — primary revenue channel closed"
      kill_weight: 0.35
      event_classes_that_trigger: [REGULATORY_REJECTION]
    - kill_id: "SPACE_KC_03"
      description: "Serial launch failures — credibility and manifest destroyed"
      kill_weight: 0.20
      event_classes_that_trigger: [LAUNCH_FAILURE]
```

---

## §10 · Thesis Registry Schema Extension

NITE-PEI requires two new fields in `config/thesis_registry.yaml`:

```yaml
# EXISTING fields (preserved unchanged):
thesis_id: "GOLD_THESIS_001"
thesis_name: "Gold Macro Thesis"
thesis_type: "GOLD_THESIS"
affected_tickers: [AU, RGLD, GDX]
current_probability: 0.60       # ← NITE-PEI reads and writes this field
created_date: "2026-06-01"
status: "ACTIVE"

# NEW fields added by NITE-PEI:
probability_history:            # ← append-only list of NITE-PEI updates
  - event_ref: "EVT_20260620_001"
    prior: 0.55
    lr_used: 1.40
    lr_source: "GEOPOLITICAL_ESCALATION / GOLD_THESIS"
    posterior: 0.63
    delta_P: +0.08
    source_tier: "T1"
    noise_discount_applied: false
    kill_states_snapshot: {GOLD_KC_01: "INACTIVE", GOLD_KC_02: "WATCH", GOLD_KC_03: "INACTIVE"}
    brier_record_id: "BRIER_20260620_001"
    created_at_sgt: "2026-06-20T14:23:00+08:00"

kill_conditions:                # ← defined once, updated by E4
  - kill_id: "GOLD_KC_01"
    description: "..."
    kill_weight: 0.40
    current_state: "INACTIVE"   # ← updated by NITE-PEI E4
    P_kill: 0.05                # ← updated by NITE-PEI E4
    event_classes_that_trigger: [CENTRAL_BANK_DOVISH]
```

---

# PART III — DR. CLAUDE CODE'S SIX INTEGRATED CONTRIBUTIONS

## §11 · Contribution 1: Kelly-NITE Coupling

### The Problem It Solves

The STR thesis proposed the Kelly ESM formula:

```
f* = (b × p − q) / b
```

But what is `p`? In STR, `p` was defined as "thesis probability" without a live update mechanism. NITE-PEI provides the update mechanism. The coupling is the final wiring step.

### The Coupling Formula

```
p_kelly   = P_posterior   (from NITE-PEI E3, most recent update)
b_kelly   = analyst_consensus_upside_pct  (from 8-Lens data, existing)
q_kelly   = 1 − p_kelly

f*_full   = (b_kelly × p_kelly − q_kelly) / b_kelly
f*_kelly  = f*_full × fractional_multiplier  (default: 0.25 per STR thesis)
f*_kelly  = max(0.0, f*_kelly)  # no short positions in this system
```

### Target USD Vector

```
NAV_total           = current_fund_NAV  (from portfolio operator, existing)
target_USD_sleeve   = NAV_total × f*_kelly
current_USD_sleeve  = sum(position_value for ticker in thesis.affected_tickers)
delta_USD           = target_USD_sleeve − current_USD_sleeve

IF delta_USD > 0: advisory = "THESIS STRENGTHENED — CONSIDER ADD of ${delta_USD:.0f}"
IF delta_USD < 0: advisory = "THESIS WEAKENED — CONSIDER REDUCE of ${abs(delta_USD):.0f}"
IF delta_USD ≈ 0: advisory = "POSITION NEAR KELLY TARGET — HOLD"
```

> **Critical engineering note:** This is an **advisory output only**. It is displayed alongside the CIO's existing sizing reference but does not route any order. `manual_execution_required = True` for all downstream code.

### New File Required

```
nite_pei/kelly_nite_coupler.py
  - Reads P_posterior from thesis_registry.yaml
  - Reads analyst_consensus_upside_pct from acms_signal_entropy table
  - Computes f*_kelly using formula above
  - Writes to: advisory_output.json → section: "kelly_advisory"
```

---

## §12 · Contribution 2: Entropy-NITE Coherence Gate

### The Problem It Solves

Kelly-NITE coupling produces a fraction `f*_kelly`, but that fraction assumes the NITE-PEI probability update was computed from high-quality evidence. If the signal entropy (SEM, from STR thesis) is high — meaning the news channel is maximally noisy — blindly using `f*_kelly` at full weight overstates certainty.

The Entropy-NITE Coherence Gate adjusts the fractional Kelly multiplier dynamically based on two dimensions of uncertainty:

1. **Signal entropy** (H_norm from SEM): How noisy is the evidence channel?
2. **Branch probability dispersion** (from PEI scenario tree): How spread are the scenario branches?

### The Gate Formula

```
# H_norm:     Shannon entropy of signal, normalized 0-1 (from SEM)
# dispersion: Std dev of branch probabilities in PEI scenario tree for this thesis
#             (0 = one dominant branch, 1 = uniform spread)

coherence_score   = 1 - (H_norm × 0.5 + dispersion × 0.5)
# coherence_score: 1.0 = full clarity, 0.0 = maximum uncertainty

fractional_multiplier = linear_interpolate(
    coherence_score,
    in_range  = [0.0, 1.0],
    out_range = [0.05, 0.35]   # 5% Kelly at max uncertainty, 35% at max clarity
)
```

### Effect Table

| H_norm | Dispersion | Coherence | Fractional Multiplier |
|--------|-----------|-----------|----------------------|
| 0.1 (clean signal) | 0.1 (one dominant branch) | 0.90 | 0.31 (near 35%) |
| 0.5 (mixed signal) | 0.5 (spread branches) | 0.50 | 0.20 |
| 1.0 (max noise) | 1.0 (uniform branches) | 0.00 | 0.05 (minimum) |
| 0.3 (clear signal) | 0.7 (scenario uncertainty) | 0.50 | 0.20 |

### Integration with Kelly-NITE

```python
# In kelly_nite_coupler.py:
H_norm       = sem.get_entropy(thesis.affected_tickers)
dispersion   = pei.get_branch_dispersion(thesis.thesis_id)
coherence    = 1 - (H_norm * 0.5 + dispersion * 0.5)
frac_mult    = 0.05 + (0.35 - 0.05) * coherence  # lerp
f*_kelly     = f*_full * frac_mult
```

### New Dependency

```
nite_pei/kelly_nite_coupler.py
  → reads: acms_cop/classifiers/signal_entropy_classifier.py (existing STR)
  → reads: pei_scenario_tree (existing PEI)
  → computes: coherence_score, fractional_multiplier
  → writes: kelly_advisory.fractional_multiplier, kelly_advisory.coherence_score
```

---

## §13 · Contribution 3: Likelihood Ratio Calibration via Brier Loop

### The Problem It Solves

The LR Table (§7) is initialized with expert estimates. Expert estimates are biased. Expert estimates are not Brier-graded. The Brier Calibration Loop converts the LR Table from a **static expert artifact** into a **living, empirically-calibrated instrument**.

### Calibration Mechanics

After a thesis resolves (outcome = 1 for thesis confirmed, 0 for thesis invalidated):

```
For each Brier record associated with this thesis resolution:
    predicted_P   = brier_record.P_posterior
    outcome       = 1 or 0
    brier_score   = (predicted_P − outcome)²

    # Was the LR responsible for this prediction well-calibrated?
    lr_entry      = lr_table[brier_record.lr_source]
    lr_entry.calibration_n += 1

    # Calibration signal: did the LR move P in the right direction?
    direction_correct = (brier_record.delta_P > 0 and outcome == 1) or
                        (brier_record.delta_P < 0 and outcome == 0)

    IF NOT direction_correct:
        # LR moved probability wrong way — shrink LR toward 1.0
        lr_entry.lr = 1.0 + (lr_entry.lr - 1.0) * 0.85  # 15% shrinkage

    IF direction_correct and brier_score < 0.10:
        # Excellent calibration — reinforce LR
        lr_entry.lr = 1.0 + (lr_entry.lr - 1.0) * 1.05  # 5% strengthening

    lr_entry.last_calibrated_sgt = now()
    lr_entry.confidence = classify_confidence(lr_entry.calibration_n)
    # LOW if n<10, MEDIUM if 10-30, HIGH if >30
```

### Engineering Contract

```
nite_pei/brier_calibration_loop.py
  - Triggered: when CIO marks a thesis as RESOLVED via governance interface
  - Input: brier_forecast_ledger.json (existing) + thesis resolution outcome
  - Output: updates nite_pei/likelihood_ratio_table.yaml (lr, calibration_n, confidence)
  - Constraint: append-only for individual records; LR values are overwritten (calibration is stateful)
  - Audit trail: each calibration event logged to nite_pei/calibration_audit_log.json
```

### Confidence Gating for CIO Display

```
IF lr_entry.confidence == "LOW":
    display: "⚠ LR: {lr_value} (EXPERT ESTIMATE — calibration_n={n}, treat with caution)"
IF lr_entry.confidence == "MEDIUM":
    display: "LR: {lr_value} (PARTIALLY CALIBRATED — n={n})"
IF lr_entry.confidence == "HIGH":
    display: "LR: {lr_value} (CALIBRATED — n={n})"
```

---

## §14 · Contribution 4: Composite Kill Risk Index (CKRI)

### The Problem It Solves

The existing cash_fortress_mode flag is binary: `True` or `False`. A single P1 contradiction or a single qualitatively-assessed kill condition triggers it. But kill conditions have:

- Different weights (not all kill conditions are equally important)
- Different correlation structures (two kill conditions may respond to the same underlying event — counting both independently double-counts the risk)
- Continuous probability values from NITE-PEI E4, not binary flags

CKRI replaces the binary `cash_fortress_mode` with a continuous risk index, computed from all kill conditions across all active theses.

### The CKRI Formula

```
CKRI = Σᵢ (kill_weight_i × P(kill_i)) + ρ × correlation_penalty

where:
  kill_weight_i    = weight of kill condition i (defined per-kill in thesis_registry.yaml)
  P(kill_i)        = current probability that kill condition i is triggered (from E4)
  ρ                = correlation penalty coefficient (default: 0.15)
  correlation_penalty = max(0, n_correlated_kills - 1)
    where n_correlated_kills = number of kill conditions with the same trigger event_class

# Normalization
CKRI_normalized = CKRI / Σᵢ kill_weight_i   # range: [0, ~1+]
# Values > 1.0 are possible when correlation penalty is large
```

### CKRI Thresholds (replaces cash_fortress_mode)

| CKRI | Portfolio Posture | Action Gate |
|------|-----------------|-------------|
| 0.00 – 0.20 | CLEAR | Normal operations |
| 0.20 – 0.40 | WATCH | Reduce new adds; monitor |
| 0.40 – 0.60 | ELEVATED | Freeze new adds; CIO review required |
| 0.60 – 0.80 | HIGH | RISK_REVIEW_REQUIRED recommendation to Chief Strategist |
| 0.80+ | CRITICAL | RAISE_CASH_REVIEW or HEDGE_REVIEW — CIO decision mandatory |

### CKRI vs. cash_fortress_mode

```
Old: cash_fortress_mode = True/False
New: CKRI = 0.73 (HIGH — RISK_REVIEW_REQUIRED)

Old provided no granularity between "ok" and "fortress."
CKRI provides five zones, driven by quantified probability, not binary flag.
```

### Engineering Contract

```
nite_pei/ckri_calculator.py
  - Input: thesis_registry.yaml → all active kill_conditions + P_kill + kill_weight
  - Computes: CKRI per the formula above
  - Output: portfolio_risk_state.json → field: ckri + ckri_zone + kill_breakdown[]
  - Feeds: Chief Strategist recommendation engine (replaces cash_fortress_mode lookup)
  - Constraint: read-only from thesis_registry.yaml; writes only to portfolio_risk_state.json
```

---

## §15 · Contribution 5: Thesis Probability as Canonical Field

### The Problem It Solves

The thesis probability produced by NITE-PEI must be **first-class data** — accessible to every layer of the V3 architecture without special querying. Currently, thesis probabilities exist only as qualitative narrative statements in agent reports. The Contradiction Governance Layer (Dr. Codex thesis) cannot detect contradictions it cannot read numerically.

### The Canonical Field Extension

All three of NITE-PEI's core outputs become canonical V3 JSON fields, written alongside every agent report in `v3_agents_latest.json`:

```json
// Extension to existing v3_agents_latest.json schema:
{
  "nite_pei": {
    "thesis_probability_snapshots": [
      {
        "thesis_id": "GOLD_THESIS_001",
        "thesis_name": "Gold Macro Thesis",
        "P_prior": 0.55,
        "P_posterior": 0.63,
        "delta_P": 0.08,
        "LR_used": 1.40,
        "LR_event_class": "GEOPOLITICAL_ESCALATION",
        "LR_confidence": "LOW",
        "kill_states": {
          "GOLD_KC_01": {"state": "INACTIVE", "P_kill": 0.05},
          "GOLD_KC_02": {"state": "WATCH",    "P_kill": 0.18},
          "GOLD_KC_03": {"state": "INACTIVE", "P_kill": 0.08}
        },
        "updated_at_sgt": "2026-06-20T14:23:00+08:00"
      }
    ],
    "ckri": 0.18,
    "ckri_zone": "CLEAR",
    "kelly_advisory": {
      "thesis_id": "GOLD_THESIS_001",
      "f_star_full": 0.12,
      "fractional_multiplier": 0.22,
      "f_star_kelly": 0.026,
      "target_usd_sleeve": 4680,
      "current_usd_sleeve": 4200,
      "delta_usd": 480,
      "coherence_score": 0.73,
      "H_norm_used": 0.41,
      "dispersion_used": 0.32
    }
  }
}
```

### Contradiction Layer Integration

With thesis probability as a canonical field, the Contradiction Governance Layer (Dr. Codex) can now detect quantitative contradictions:

```
CONTRADICTION RULE [NITEPEI-001]:
  IF nite_pei.thesis_probability_snapshots[thesis_id].P_posterior < 0.30
  AND agent_reports[any].recommendation == "THESIS_SUPPORTS_ADD"
  → flag as P3 contradiction: "Agent recommends add but NITE-PEI thesis P < 0.30"

CONTRADICTION RULE [NITEPEI-002]:
  IF nite_pei.ckri_zone IN ["HIGH", "CRITICAL"]
  AND agent_reports[any].recommendation IN ["WAIT", "HOLD"]
  AND agent_reports[any].risk_flags == []
  → flag as P1 contradiction: "CKRI is HIGH/CRITICAL but agent shows no risk flags"
```

---

## §16 · Contribution 6: Doctrine Protection of Hedges

### The Problem It Solves

The existing CKRI and any de-risk recommendation from NITE-PEI must not touch VXX/VIXY hedge positions. The hedge sleeve is a separate instrument class — it is the *antidote* to the risk CKRI measures, not an asset whose value should be reduced when risk rises.

This contribution adds a **doctrine wall** in code: two separate action gates with no overlap.

### The Dual Gate Architecture

```
EXISTING (single gate — WRONG):
  IF CKRI > 0.60: recommend REDUCE across portfolio
  Risk: de-risk logic could touch VXX/VIXY

CORRECT (dual gate — NITE-PEI contribution):
  equity_action_gate:   covers only [long equity, gold miners, space-tech, quantum]
  hedge_action_gate:    covers only [VXX, VIXY, other volatility instruments]

De-risk recommendations from CKRI route to equity_action_gate ONLY.
Hedge recommendations route to hedge_action_gate ONLY.
```

### Hedge Advisory Formula (from STR Chapter 9, now wired to NITE-PEI)

```python
# In nite_pei/hedge_action_gate.py

beta_portfolio       = portfolio_operator.get_weighted_beta()
hedge_effectiveness  = vxx_vixy_correlation_tracker.get_effectiveness()
hedge_ratio_implied  = abs(beta_portfolio) / hedge_effectiveness

current_hedge_usd    = sum(portfolio.get_value(t) for t in ["VXX", "VIXY"])
total_equity_usd     = portfolio.get_equity_sleeve_value()
current_hedge_ratio  = current_hedge_usd / total_equity_usd

advisory = {
    "implied_hedge_ratio": hedge_ratio_implied,
    "current_hedge_ratio": current_hedge_ratio,
    "delta_ratio": hedge_ratio_implied - current_hedge_ratio,
    "ckri": ckri,
    "action_gate": "HEDGE_ONLY — equity_action_gate NOT triggered"
}
# manual_execution_required = True always
```

### Doctrine Entry

```yaml
# config/v3_doctrine_seed.json — new entry to add:
{
  "doctrine_id": "BLV3-DOCTRINE-007",
  "title": "Dual action gate separation: equity vs. hedge",
  "description": "De-risk actions from NITE-PEI CKRI route to equity_action_gate only.
                   VXX and VIXY are governed exclusively by hedge_action_gate.
                   No de-risk recommendation from CKRI shall trigger a reduction of hedge positions.
                   No hedge recommendation shall trigger a change in equity positions.
                   The gates are architecturally separate and must never be merged.",
  "rationale": "Hedges are the antidote to the risk that CKRI measures.
                Reducing hedges in response to high CKRI would be self-defeating.
                The dual gate architecture enforces this at the code level, not the CIO's memory.",
  "effective_date": "2026-06-21",
  "authored_by": "Dr. Claude Code — Windows Platform Team"
}
```

---

# PART IV — UNIFIED ARCHITECTURE

## §17 · The 11 Integration Points

This section maps the complete data flow through the integrated NITE-PEI + V3 architecture. Each integration point is a named connection between two modules with a defined input, output, and file contract.

```
─────────────────────────────────────────────────────────────────────────────────────
NITE-PEI UNIFIED ARCHITECTURE — 11 INTEGRATION POINTS
─────────────────────────────────────────────────────────────────────────────────────

[IP-01] NEWS INGEST → EVENT CLASSIFIER
    From:  news_ingest_operator.py (existing)
    To:    nite_pei/event_classifier.py (E1, NEW)
    Data:  raw news event JSON {headline, source_tier, timestamp_sgt, ticker_tags[]}
    ─────────────────────────────────────────

[IP-02] EVENT CLASSIFIER → LIKELIHOOD RATIO TABLE
    From:  nite_pei/event_classifier.py
    To:    nite_pei/likelihood_ratio_table.yaml
    Data:  event_class string → lookup key for LR retrieval
    ─────────────────────────────────────────

[IP-03] THESIS REGISTRY → BAYESIAN UPDATER
    From:  config/thesis_registry.yaml
    To:    nite_pei/bayesian_updater.py (E3, NEW)
    Data:  P_prior, thesis_type, kill_conditions[]
    ─────────────────────────────────────────

[IP-04] BAYESIAN UPDATER → KILL CONDITION STATE MACHINE
    From:  nite_pei/bayesian_updater.py
    To:    nite_pei/kill_condition_state_machine.py (E4, NEW)
    Data:  P_posterior, event_class, kill_conditions[] with current P_kill values
    ─────────────────────────────────────────

[IP-05] BAYESIAN UPDATER → BRIER CALIBRATION LOOP (write phase)
    From:  nite_pei/bayesian_updater.py
    To:    nite_pei/brier_calibration_loop.py (E5, NEW) — write phase
    Data:  brier_forecast_record {thesis_id, P_prior, LR_used, P_posterior, delta_P}
    Note:  Write phase only; calibration loop fires separately on thesis resolution
    ─────────────────────────────────────────

[IP-06] KILL CONDITION STATE MACHINE → THESIS REGISTRY WRITER
    From:  nite_pei/kill_condition_state_machine.py
    To:    nite_pei/thesis_registry_writer.py (E6, NEW)
    Data:  Updated kill_states{}, P_kill values per kill_id
    ─────────────────────────────────────────

[IP-07] THESIS REGISTRY WRITER → CANONICAL JSON
    From:  nite_pei/thesis_registry_writer.py
    To:    v3_agents_latest.json → nite_pei{} block (canonical extension)
    Data:  thesis_probability_snapshots[], ckri, ckri_zone
    ─────────────────────────────────────────

[IP-08] SIGNAL ENTROPY MODULE → KELLY-NITE COUPLER
    From:  acms_cop/classifiers/signal_entropy_classifier.py (existing STR)
    To:    nite_pei/kelly_nite_coupler.py (NEW)
    Data:  H_norm per ticker (entropy score 0–1)
    ─────────────────────────────────────────

[IP-09] PEI SCENARIO TREE → KELLY-NITE COUPLER
    From:  pei/scenario_tree_builder.py (existing PEI)
    To:    nite_pei/kelly_nite_coupler.py
    Data:  branch_probability_dispersion (std dev of scenario branch probs)
    ─────────────────────────────────────────

[IP-10] KELLY-NITE COUPLER → CIO ADVISORY RENDERER
    From:  nite_pei/kelly_nite_coupler.py
    To:    nite_pei/cio_advisory_renderer.py (E7, NEW)
    Data:  f*_kelly, target_usd_sleeve, delta_usd, coherence_score, posture
    ─────────────────────────────────────────

[IP-11] BRIER CALIBRATION LOOP (resolve phase) → LIKELIHOOD RATIO TABLE
    From:  nite_pei/brier_calibration_loop.py — resolve phase (fires on CIO resolution)
    To:    nite_pei/likelihood_ratio_table.yaml
    Data:  Calibration signal per LR entry — updates lr, calibration_n, confidence
    ─────────────────────────────────────────

─────────────────────────────────────────────────────────────────────────────────────
CROSS-LAYER READS (no write-back):
  CKRI Calculator reads kill_states from thesis_registry.yaml  [IP-04 output]
  Contradiction Governance reads P_posterior from canonical JSON [IP-07 output]
  Chief Strategist publisher reads all of nite_pei{} block
─────────────────────────────────────────────────────────────────────────────────────
```

---

# PART V — EXTENDED DOCTRINE

## §18 · Four Doctrinal Extensions from the Integrated Thesis

These four extensions supplement existing BlueLotus V3 doctrine. They are proposed for formal addition to `config/v3_doctrine_seed.json` by CIO authorization.

### Doctrine Extension 1: NITE-PEI Thesis Probability Is Canonical

> *Thesis probability is not a narrative judgment. It is a number, updated by formula, logged append-only, graded by Brier. No human may edit thesis probability outside the NITE-PEI workflow. No agent report may claim a thesis is "strong" or "weak" without the corresponding P_posterior on the canonical record.*

### Doctrine Extension 2: Kelly Is Advisory, Never Mandatory

> *The Kelly-NITE coupling produces a target USD vector. That vector is advisory. The CIO's discretionary sizing may diverge from the Kelly target at any time, for any reason, provided the divergence is logged in the CIO decision strip. Kelly tells the CIO what the formula would do. The CIO tells the fund what will actually happen.*

### Doctrine Extension 3: LR Confidence Is Surfaced, Never Hidden

> *Every NITE-PEI probability update presented to the CIO must display the calibration confidence of the LR used (LOW/MEDIUM/HIGH). A LOW confidence LR is still used — refusing to update on uncertain evidence is itself a bad decision rule — but the CIO must see that confidence level before the update influences any portfolio decision.*

### Doctrine Extension 4: CKRI Replaces Binary Cash Fortress Mode

> *The binary `cash_fortress_mode` flag is deprecated as of NITE-PEI deployment. CKRI, a continuous [0, 1+] index with five named zones, replaces it in all downstream code. Any reference to `cash_fortress_mode` in existing code must be replaced with CKRI zone lookup during NITE-PEI application engineering. The old flag may be preserved as a derived boolean (`CKRI > 0.60`) for backwards compatibility with legacy displays only.*

---

# PART VI — IMPLEMENTATION ROADMAP

## §19 · Phase 1 — Foundation (Build First)

**Scope:** Core NITE-PEI engine, minimal dependencies.  
**Target:** Events are classified, Bayesian updates are computed, thesis registry is written.

```
New files:
  nite_pei/__init__.py
  nite_pei/event_classifier.py            [E1 — §6 taxonomy]
  nite_pei/likelihood_ratio_table.yaml    [E2 — §7 initial expert values]
  nite_pei/bayesian_updater.py            [E3 — §8 formula]
  nite_pei/kill_condition_state_machine.py [E4 — §9 state machine]
  nite_pei/thesis_registry_writer.py      [E6 — §10 canonical write]

Modified files:
  config/thesis_registry.yaml             [add probability_history and kill_conditions blocks]

Acceptance tests:
  1. python -m py_compile nite_pei/*.py → all pass
  2. Unit test: Given P_prior=0.55, event=GEOPOLITICAL_ESCALATION, thesis=GOLD_THESIS
     → P_posterior ≈ 0.63 (LR=1.40 applied)
  3. Unit test: Kill condition GOLD_KC_02 transitions INACTIVE → WATCH when P_kill crosses 0.10
  4. thesis_registry.yaml shows new probability_history entry after update
  5. pytest tests/ -x -q → all existing tests still pass
```

## §20 · Phase 2 — Brier Calibration Loop

**Scope:** Pre-registration and post-resolution calibration of LR Table.

```
New files:
  nite_pei/brier_calibration_loop.py      [E5 — §15 calibration mechanics]
  nite_pei/calibration_audit_log.json     [append-only audit]

Integration:
  Bayesian updater writes brier_forecast_record at Step 14 (§5)
  Calibration loop fires when CIO marks thesis as RESOLVED

Acceptance tests:
  1. Brier forecast record written to ledger pre-resolution
  2. On simulated resolution (outcome=1), LR entry updated:
     calibration_n incremented; lr adjusted per direction-correct formula
  3. Calibration_n = 10 → confidence changes from "LOW" to "MEDIUM"
```

## §21 · Phase 3 — CKRI Calculator

**Scope:** Composite Kill Risk Index replaces cash_fortress_mode.

```
New files:
  nite_pei/ckri_calculator.py             [§14 formula + §18 Doctrine 4]
  nite_pei/portfolio_risk_state.json      [append-only output]

Modified files:
  config/v3_doctrine_seed.json            [add BLV3-DOCTRINE-007]

Acceptance tests:
  1. CKRI computed correctly for 3-kill-condition Gold Thesis scenario
  2. CKRI zone correctly maps to CLEAR/WATCH/ELEVATED/HIGH/CRITICAL
  3. cash_fortress_mode flag deprecated from all NITE-PEI code (grep check)
```

## §22 · Phase 4 — Kelly-NITE Coupling

**Scope:** NITE-PEI posterior probability feeds ESM Kelly formula with Entropy-NITE coherence gating.

```
New files:
  nite_pei/kelly_nite_coupler.py          [§11 + §12 combined]

Dependencies:
  acms_cop/classifiers/signal_entropy_classifier.py  (existing STR)
  pei/scenario_tree_builder.py                        (existing PEI)
  config/thesis_registry.yaml             (reads P_posterior)

Acceptance tests:
  1. f*_kelly computed with correct fractional_multiplier based on H_norm + dispersion
  2. H_norm = 1.0 (max noise) → fractional_multiplier ≈ 0.05
  3. H_norm = 0.1, dispersion = 0.1 → fractional_multiplier ≈ 0.31
  4. Negative f*_full → f*_kelly clamped to 0.0 (no short positions)
  5. Target USD vector delta correctly computed vs. current sleeve value
```

## §23 · Phase 5 — Canonical JSON + CIO Advisory Renderer

**Scope:** All NITE-PEI outputs are first-class in v3_agents_latest.json; CIO advisory is rendered on Chief Strategist page.

```
New files:
  nite_pei/cio_advisory_renderer.py       [E7 — §5 Steps 17-19]

Modified files:
  mid/bluelotus_publisher.py              [add nite_pei{} block to v3_agents_latest.json]
                                          [add NITE-PEI Thesis Updates section to HTML]

Contradiction Governance integration:
  contradiction_register.json             [add NITEPEI-001 and NITEPEI-002 rules]

Acceptance tests:
  1. v3_agents_latest.json contains nite_pei{} block after publish run
  2. Chief Strategist HTML shows "NITE-PEI Thesis Updates" section
  3. Contradiction NITEPEI-001 fires when P_posterior < 0.30 + agent recommends ADD
```

## §24 · Phase 6 — Hedge Action Gate Separation

**Scope:** Dual gate architecture — equity_action_gate and hedge_action_gate permanently separated.

```
New files:
  nite_pei/hedge_action_gate.py           [§16 + STR Chapter 9 wired]
  nite_pei/equity_action_gate.py          [explicit CKRI-driven equity advisory]

Modified files:
  config/v3_doctrine_seed.json            [add BLV3-DOCTRINE-007 hedge gate separation]

Acceptance tests:
  1. CKRI > 0.60 triggers equity_action_gate advisory ONLY — VXX/VIXY untouched
  2. Hedge advisory produced by hedge_action_gate reads beta_portfolio correctly
  3. VXX/VIXY never appear in equity_action_gate output (grep check on advisory JSON)
  4. Full test suite: pytest tests/ -x -q → all pass
```

---

## Final Integration Summary

```
──────────────────────────────────────────────────────────────────────
NEW FILES TO CREATE (10 files + 2 config):
──────────────────────────────────────────────────────────────────────
  nite_pei/__init__.py
  nite_pei/event_classifier.py
  nite_pei/likelihood_ratio_table.yaml        ← initial expert values in this thesis
  nite_pei/bayesian_updater.py
  nite_pei/kill_condition_state_machine.py
  nite_pei/thesis_registry_writer.py
  nite_pei/brier_calibration_loop.py
  nite_pei/ckri_calculator.py
  nite_pei/kelly_nite_coupler.py
  nite_pei/cio_advisory_renderer.py
  nite_pei/equity_action_gate.py
  nite_pei/hedge_action_gate.py
  nite_pei/portfolio_risk_state.json          ← append-only runtime output
  nite_pei/calibration_audit_log.json         ← append-only audit

──────────────────────────────────────────────────────────────────────
EXISTING FILES TO MODIFY (minimal, additive only):
──────────────────────────────────────────────────────────────────────
  config/thesis_registry.yaml                 ← add probability_history + kill_conditions
  config/v3_doctrine_seed.json                ← add BLV3-DOCTRINE-007
  mid/bluelotus_publisher.py                  ← add nite_pei{} block + HTML section
  contradiction_register.json (governance)    ← add NITEPEI-001, NITEPEI-002 rules

──────────────────────────────────────────────────────────────────────
EXISTING FILES THAT NITE-PEI READS (no modification):
──────────────────────────────────────────────────────────────────────
  acms_cop/classifiers/signal_entropy_classifier.py  (SEM entropy → coherence gate)
  pei/scenario_tree_builder.py                       (branch dispersion → coherence gate)
  data/brier_forecast_ledger.json                    (Brier records → calibration loop)
  data/portfolio_positions.json                      (current sleeve values → Kelly delta)
──────────────────────────────────────────────────────────────────────

INVARIANTS PRESERVED:
  ✓ CIO_ONLY_MANUAL: TRUE — no output executes or routes any order
  ✓ ORDER_ROUTING_ENABLED: FALSE — no broker path in any NITE-PEI file
  ✓ LLM_ORDER_GENERATION: FALSE — no LLM drives a trade
  ✓ MANUAL_EXECUTION_REQUIRED: TRUE — every advisory requires CIO action
  ✓ Append-only memory — probability_history, brier_records, audit_log are append-only
  ✓ No V2 contamination — NITE-PEI reads only V3 schemas
  ✓ Hedge doctrine — VXX/VIXY governed only by hedge_action_gate (BLV3-DOCTRINE-007)
```

---

*CIO Soh Wee Kian (NITE-PEI Engine Architecture)*  
*Dr. Claude Code, Windows Platform Team (Six Integrated Contributions)*  
*BlueLotus Fund Singapore · June 2026*  
*Classification: Internal Academic — Thesis Authority: Research / Proposal / Preparation Only*  
*Execution authority: CIO_ONLY_MANUAL · Order routing: DISABLED*  
*This document is a build specification. It does not execute. The CIO executes.*
