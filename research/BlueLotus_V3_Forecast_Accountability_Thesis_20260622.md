# BLUELOTUS V3 — ARCHITECTURE THESIS
## Probabilistic Forecast Accountability: ACMS-COP and NITE-PEI Brier Scoring
### Version: THESIS-001 | Date: 2026-06-22 | Author: Chief Architect / Chief Clerk
### Status: PROPOSED — Pending CIO Review

---

## Abstract

The BlueLotus V3 pipeline generates probabilistic forecasts every cycle from two modules — ACMS-COP and NITE-PEI — but neither module documents the evolution of its probability estimates over time, nor resolves past forecasts against observed outcomes. This creates an accountability gap: the system produces numbers that look calibrated but cannot be verified. This thesis defines the problem precisely, identifies the root causes, and proposes a lightweight solution using flat probability contingency tables appended each cycle. No complex database is required. The solution is designed to fit within the existing deterministic pipeline architecture and governance constraints.

---

## 1. Problem Statement

### 1.1 ACMS-COP — The Half-Built Scoring Loop

ACMS-COP opens 5 scenario forecasts per cycle. The architecture is structurally correct — each forecast has:

```json
{
  "forecast_id": "RELIEF_RALLY_RESUMPTION",
  "probability": 0.15,
  "horizon_sessions": 5,
  "outcome_definition": "SPY and QQQ both close higher over 5 sessions.",
  "source": "ACMS-COP text report"
}
```

This is everything needed for Brier scoring: a probability, a horizon, and a binary verifiable outcome definition.

The resolution side, however, is empty:

```json
"learning_records": []
```

Forecasts are opened every cycle. They are never closed. They are never scored. The `learning_records` array has never been populated in the system's operational history.

**The loop is half-built. The opening half works. The closing half does not exist.**

### 1.2 NITE-PEI — No Archive At All

NITE-PEI updates Bayesian kill condition probabilities every cycle:

```
WARSH_KC_01: P_kill = 0.9364 (CONFIRMED)
BOJ_KC_01:   P_kill = 0.9392 (CONFIRMED)
CKRI:        0.9359 (CRITICAL)
```

These numbers are computed, used in the current cycle, and then **overwritten by the next cycle's computation**. There is no timestamped ledger. There is no archive. Yesterday's P_kill values are gone.

This means:
- It is impossible to know whether P_kill estimates are stable, drifting, or oscillating
- It is impossible to compute a Brier score for kill condition forecasts
- It is impossible to audit whether a kill condition that reached CONFIRMED then resolved correctly

**NITE-PEI has no forecast accountability infrastructure whatsoever.**

### 1.3 What IS Available — The 1,609 Snapshot Archive

The `dataset_snapshot_archive` contains 1,609 immutable point-in-time captures of the full pipeline state:

```json
{
  "snapshot_count": 1609,
  "doctrine": "Immutable point-in-time dataset archive for reconstruction and audit.",
  "latest_snapshot": {
    "snapshot_id": "dataset_5d3c33c46252fc5962ae",
    "captured_at": "2026-06-22T18:35:28",
    "dataset_sha256": "5d3c33c46252fc5962ae..."
  }
}
```

Every past cycle's CKRI, P_kill values, ACMS-COP probabilities, and market outcomes are recoverable from this archive. **The raw material to build a complete retrospective calibration record already exists.** It has simply never been connected to a resolution engine.

---

## 2. Root Cause Analysis

### 2.1 Structural Root Cause: Write-Once Architecture Without a Closing Step

The V3 pipeline is designed as a **deterministic forward pipeline** — it reads, computes, and writes the current cycle. It has no backward-looking step that reopens past outputs and compares them against what actually happened.

The pipeline stages are:

```
Ingest → Compute → Output → Archive
```

What is missing:

```
Ingest → Compute → Output → Archive
                              ↓
                         Resolve past forecasts
                              ↓
                         Append Brier scores
                              ↓
                         Update learning_records
```

This closing step is architecturally absent — not broken, simply never built.

### 2.2 Conceptual Root Cause: Conflating Estimation with Forecasting

NITE-PEI treats P_kill as a **current state estimate** — what is the probability right now that this thesis is being killed? This is a valid and useful quantity.

The problem is that it is not also being treated as a **forecast** — what did we predict yesterday about today, and were we right?

These are two different operations on the same number:
- **Estimation**: P_kill at time T = current Bayesian posterior
- **Forecasting**: P_kill at time T-1 predicted an outcome at time T — did it resolve correctly?

The existing architecture captures estimation. It does not capture forecasting.

### 2.3 Why the Ticker System Works But These Don't

The ticker Brier scoring system works because it was designed with both halves from the beginning:
- **Open**: store a forecast with `{ticker, direction, probability, target_price, horizon_days, forecast_date}`
- **Close**: at maturity, look up actual price, compute binary outcome, score Brier, append to `forecast_resolutions`

ACMS-COP has the open half. NITE-PEI has neither. The fix is to add the missing halves — not to redesign anything.

---

## 3. Proposed Solution Architecture

### Design Principle: Small, Flat, Appended

The user's specification is precise: *"It need not be a complex database to update, it's just a small probability contingency table to update."*

The solution is two lightweight flat files — one per module — appended each cycle. No database. No schema migration. No new infrastructure dependency.

---

### 3.1 ACMS-COP Solution — The Forecast Resolution Ledger

**File:** `acms_cop_forecast_ledger.json`  
**Location:** `C:\bluelotus3\data\acms_cop\acms_cop_forecast_ledger.json`  
**Operation:** Append-only

#### Structure

```json
{
  "ledger_version": "v1.0",
  "module": "ACMS-COP",
  "records": [
    {
      "record_id": "ACMS-LEDGER-20260622-RELIEF_RALLY_RESUMPTION",
      "forecast_id": "RELIEF_RALLY_RESUMPTION",
      "cycle_date": "2026-06-22",
      "snapshot_id": "dataset_5d3c33c46252fc5962ae",
      "probability_issued": 0.15,
      "horizon_sessions": 5,
      "outcome_definition": "SPY and QQQ both close higher over 5 sessions.",
      "resolution_date": null,
      "resolution_snapshot_id": null,
      "outcome_observed": null,
      "brier_score": null,
      "status": "OPEN"
    }
  ]
}
```

#### Each Cycle: Opening Step (runs at forecast generation time)

For each forecast in `acms_cop.forecasts_opened`, append a new ledger record with `status=OPEN`, recording the issued probability and the snapshot_id of the current cycle.

```python
# Opening step — runs after acms_cop block is written
for forecast in acms_cop['forecasts_opened']:
    record = {
        "record_id": f"ACMS-LEDGER-{today}-{forecast['forecast_id']}",
        "forecast_id": forecast['forecast_id'],
        "cycle_date": today,
        "snapshot_id": current_snapshot_id,
        "probability_issued": forecast['probability'],
        "horizon_sessions": forecast['horizon_sessions'],
        "outcome_definition": forecast['outcome_definition'],
        "resolution_date": None,
        "resolution_snapshot_id": None,
        "outcome_observed": None,
        "brier_score": None,
        "status": "OPEN"
    }
    append_to_ledger(record)
```

#### Each Cycle: Resolution Step (runs at cycle start, checks matured forecasts)

```python
# Resolution step — runs before new forecasts are opened
for record in ledger where status == "OPEN":
    sessions_elapsed = count_trading_sessions(record['cycle_date'], today)
    if sessions_elapsed >= record['horizon_sessions']:
        outcome = evaluate_outcome(
            record['outcome_definition'],
            snapshot_archive[today]
        )
        brier = (record['probability_issued'] - outcome) ** 2
        record['outcome_observed'] = outcome   # 1 or 0
        record['brier_score'] = brier
        record['resolution_date'] = today
        record['resolution_snapshot_id'] = current_snapshot_id
        record['status'] = "RESOLVED"
```

#### Brier Score Aggregation

After resolution, append to `acms_cop.learning_records`:

```json
{
  "learning_record_id": "LR-ACMS-20260629-RELIEF_RALLY_RESUMPTION",
  "forecast_id": "RELIEF_RALLY_RESUMPTION",
  "issued_on": "2026-06-22",
  "resolved_on": "2026-06-29",
  "probability_issued": 0.15,
  "outcome_observed": 0,
  "brier_score": 0.0225,
  "rolling_avg_brier": 0.1847
}
```

#### Outcome Evaluation — Verifiable Binary Rules

Each `outcome_definition` in the current ACMS-COP already defines a binary outcome. The evaluation logic maps to observable pipeline fields:

| Forecast | Outcome = 1 if... | Pipeline field |
|---|---|---|
| CHOPPY_DIGESTION | SPY 3-session return within ±2.0% | `live_prices.SPY.chg_pct` cumulative |
| HAWKISH_WARSH_RISK_OFF | SPY negative AND VIX/VXX rising over 5 sessions | `live_prices.SPY` + `live_prices.VXX` |
| RELIEF_RALLY_RESUMPTION | SPY and QQQ both positive over 5 sessions | `live_prices.SPY` + `live_prices.QQQ` |
| BOJ_YEN_CARRY_FLARE_UP | USDJPY stress flag active within 5 sessions | `cross_market_confirmation` or `nite_pei` BOJ_KC_01 |
| CREDIT_LIQUIDITY_ACCIDENT | Credit stress escalates to severe within 10 sessions | `nite_pei.ckri_zone == CRITICAL` + `cross_market_confirmation` |

All of these are already in the pipeline snapshot. No new data sources are needed.

---

### 3.2 NITE-PEI Solution — The P_kill Time-Series Ledger

**File:** `nite_pei_pkill_ledger.json`  
**Location:** `C:\bluelotus3\data\v3_cycles\nite_pei_pkill_ledger.json`  
**Operation:** Append-only

#### Structure

```json
{
  "ledger_version": "v1.0",
  "module": "NITE-PEI",
  "records": [
    {
      "record_id": "NITEPEI-LEDGER-20260622T172818-WARSH_KC_01",
      "cycle_timestamp_sgt": "2026-06-22T17:28:18+08:00",
      "snapshot_id": "dataset_5d3c33c46252fc5962ae",
      "thesis_id": "HAWKISH_WARSH_THESIS",
      "kill_id": "WARSH_KC_01",
      "p_kill": 0.936407,
      "current_state": "CONFIRMED",
      "ckri": 0.935897,
      "ckri_zone": "CRITICAL",
      "resolution_cycle": null,
      "outcome_observed": null,
      "brier_score": null,
      "status": "OPEN"
    }
  ]
}
```

#### Each Cycle: Logging Step (runs immediately after nite_pei block is computed)

```python
# NITE-PEI logging step — runs after nite_pei_block.json is written
for kill_condition in nite_pei['kill_breakdown']:
    record = {
        "record_id": f"NITEPEI-LEDGER-{cycle_ts}-{kill_condition['kill_id']}",
        "cycle_timestamp_sgt": cycle_ts,
        "snapshot_id": current_snapshot_id,
        "thesis_id": kill_condition['thesis_id'],
        "kill_id": kill_condition['kill_id'],
        "p_kill": kill_condition['P_kill'],
        "current_state": kill_condition['current_state'],
        "ckri": nite_pei['ckri'],
        "ckri_zone": nite_pei['ckri_zone'],
        "resolution_cycle": None,
        "outcome_observed": None,
        "brier_score": None,
        "status": "OPEN"
    }
    append_to_ledger(record)
```

This step costs microseconds. One JSON append per kill condition per cycle. Ten kill conditions = ten records per cycle.

#### NITE-PEI Outcome Definition — What Does Resolution Mean?

Unlike ACMS-COP where outcomes are market price movements observable in the next snapshot, NITE-PEI kill conditions resolve when a thesis is formally killed or confirmed dead.

**Proposed resolution rules:**

| Kill Condition State | Resolution Trigger | outcome_observed |
|---|---|---|
| CONFIRMED → thesis explicitly killed | CIO records thesis as killed in `cio_decision_journal` | 1 (kill correct) |
| CONFIRMED → thesis survives N cycles | State returns to INACTIVE or stays WATCH for 30 cycles | 0 (false alarm) |
| INACTIVE → stays INACTIVE | State never fires | 0 (correct abstention) |
| INACTIVE → transitions to CONFIRMED | State escalates | Special case — log as missed early signal |

The resolution horizon for NITE-PEI is **30 cycles** (approximately 20 hours of pipeline operation). At 30 cycles, any CONFIRMED kill condition that has not resulted in a thesis kill event is scored as a false alarm (outcome=0).

```python
# NITE-PEI Brier score computation
brier = (p_kill_issued - outcome_observed) ** 2

# Example: P_kill=0.9364, outcome=1 (thesis correctly killed)
brier = (0.9364 - 1.0) ** 2  # = 0.0041 — excellent calibration

# Example: P_kill=0.9364, outcome=0 (false alarm — thesis survived 30 cycles)
brier = (0.9364 - 0.0) ** 2  # = 0.8768 — severe miscalibration
```

#### CKRI Aggregate Time-Series

In addition to per-kill-condition tracking, log the aggregate CKRI as a pure time-series:

```json
{
  "ckri_series": [
    {
      "cycle_timestamp_sgt": "2026-06-22T17:28:18+08:00",
      "ckri": 0.935897,
      "ckri_zone": "CRITICAL",
      "snapshot_id": "dataset_5d3c33c46252fc5962ae"
    }
  ]
}
```

This enables trend analysis — is aggregate kill risk rising, falling, or stable? It requires no resolution logic. It is a pure time-series log.

---

## 4. Implementation Approach — Minimum Viable Change

### 4.1 What Needs to Be Built

Two new pipeline steps only. Nothing else changes.

| Step | When It Runs | What It Does |
|---|---|---|
| `nite_pei_ledger_append` | After `nite_pei_block.json` is written each cycle | Appends all kill conditions + CKRI to `nite_pei_pkill_ledger.json` |
| `acms_forecast_open` | After `acms_cop_latest.json` is written each cycle | Appends 5 new OPEN records to `acms_cop_forecast_ledger.json` |
| `acms_forecast_resolve` | At start of each cycle, before new forecasts are opened | Checks all OPEN records whose horizon has matured; scores and closes them |

### 4.2 File Sizes — Negligible

**ACMS-COP ledger growth:**
- 5 records × ~200 bytes = 1 KB per cycle
- 39-minute cycles → ~37 cycles per day → ~37 KB per day
- 1 year → ~13 MB — trivially small

**NITE-PEI ledger growth:**
- 10 kill conditions + 1 CKRI record = 11 records × ~150 bytes = 1.65 KB per cycle
- ~37 cycles per day → ~61 KB per day
- 1 year → ~22 MB — trivially small

### 4.3 Retroactive Bootstrapping from Snapshot Archive

The 1,609 existing snapshots already contain all historical P_kill and ACMS-COP probability values. A one-time bootstrap script populates both ledgers retroactively:

```python
# One-time retroactive bootstrap
for snapshot in snapshot_archive.all_snapshots_sorted_by_date():
    raw = load_snapshot(snapshot['snapshot_id'])

    # Bootstrap NITE-PEI
    for kc in raw['nite_pei']['kill_breakdown']:
        append_nite_pei_ledger_record(kc, snapshot)

    # Bootstrap ACMS-COP
    for forecast in raw['acms_cop']['forecasts_opened']:
        if not already_in_ledger(forecast['forecast_id'], snapshot['captured_at']):
            append_acms_forecast_open_record(forecast, snapshot)
```

This provides immediate historical depth without waiting for future cycles. Day one of implementation, the system has 1,609 cycles of P_kill history to analyze.

---

## 5. Governance Constraints

The proposed solution must respect existing doctrine:

| Constraint | How This Solution Complies |
|---|---|
| CIO_ONLY_MANUAL | Ledger logging is a data operation, not an execution decision. No orders are generated. |
| LLM_ORDER_GENERATION: FALSE | Brier scores are computed deterministically from observed market data. No LLM involvement in scoring. |
| BLV3-DOCTRINE-010 | LLM synthesizes Brier score summaries from pre-computed numbers. It does not compute them. |
| Observation Lock (until 2026-06-27) | This is classified as a DATA_QUALITY_FIX — explicitly permitted under the lock. Not an ARCHITECTURE_REFACTOR. |
| Immutable snapshot archive | Ledger files are separate from the snapshot archive. The archive doctrine is not violated. |

---

## 6. What This Enables — Long-Term Value

Once operational, the ledgers provide:

**For ACMS-COP:**
- Rolling Brier score per scenario type — is the system better at forecasting market stress or relief rallies?
- Calibration curve — are 15% probabilities actually happening 15% of the time?
- Detection of systematic over/underconfidence per scenario agent

**For NITE-PEI:**
- P_kill time-series — is WARSH_KC_01 oscillating or monotonically rising?
- Kill condition accuracy — when P_kill reaches 0.90+, does the thesis actually die?
- CKRI trend — is aggregate kill risk a leading indicator of drawdown?
- False alarm rate — how often does CRITICAL CKRI resolve without consequence?

**For the System:**
- A formal answer to: *"Is this system's probability engine calibrated?"*
- The Brier score becomes a health metric alongside existing pipeline checks (canonical contract PASS, deterministic pipeline PASS)
- Objective graduation criteria for future experimental modules — a module can only be promoted from EXPERIMENTAL to PIPELINE-ACTIVE once its Brier score over N resolved forecasts meets a defined threshold

---

## 7. BGTM-V1 Graduation Criterion (Future Reference)

Per CIO directive (2026-06-22), BGTM-V1 is PARALLEL RESEARCH and must not be integrated until a reference benchmark exists. The ledger framework proposed above defines the objective graduation criterion:

> **BGTM-V1 may be considered for pipeline integration when:**
> 1. It has generated forecasts for ≥ 30 resolved geopolitical events
> 2. Its Brier score over those events is ≤ 0.25 (better than the naive 50/50 baseline of 0.25)
> 3. Its payoff tensor has been sensitivity-tested and documented
> 4. The Observation Lock has expired and a CIO architecture review has been completed

Until these criteria are met, BGTM-V1 outputs are research observations only.

---

## 8. Summary Recommendation

| Item | Recommendation |
|---|---|
| **ACMS-COP** | Add `acms_forecast_open` and `acms_forecast_resolve` pipeline steps. Write to `acms_cop_forecast_ledger.json`. Append Brier scores to `learning_records` at resolution. |
| **NITE-PEI** | Add `nite_pei_ledger_append` pipeline step. Write P_kill time-series to `nite_pei_pkill_ledger.json` each cycle. Add 30-cycle resolution rule for kill condition scoring. |
| **Retroactive bootstrap** | Run one-time script against 1,609 existing snapshots to populate both ledgers with historical data immediately. |
| **Ticker Brier scoring** | Leave as-is. Intentionally waiting to harvest. No changes. |
| **BGTM-V1** | Remains PARALLEL RESEARCH. Ledger framework defines its future graduation criteria. |
| **Observation Lock** | Classify both new pipeline steps as DATA_QUALITY_FIX — permitted under current lock. |

---

*This thesis was produced by the Chief Architect / Chief Clerk role on 2026-06-22. It is a design proposal only. Implementation requires CIO review and approval. No pipeline changes have been made. CIO_ONLY_MANUAL intact. SYSTEM_ORDERS_GENERATED = 0.*
