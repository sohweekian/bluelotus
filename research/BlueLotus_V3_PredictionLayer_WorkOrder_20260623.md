# BLUELOTUS V3 — PREDICTION LAYER EXPANSION WORK ORDER
## PLEXP-001: Add Options Flow, Credit Spreads, Cheap Talk Filter, and Enhanced Capital Flow
### Work Order ID: PLEXP-001 | Date: 2026-06-23 | Author: Chief Architect / Chief Clerk
### Status: PLANNING COMPLETE — AWAITING CIO AUTHORIZATION

---

## Work Order Summary

| Field | Value |
|-------|-------|
| WO ID | PLEXP-001 |
| Project | Prediction Layer Expansion |
| Companion Thesis | THESIS-002 (BlueLotus_V3_Probability_Prediction_Gap_Thesis_20260623.md) |
| Prerequisite WO | None for S0–S9. THESIS-001 WOs recommended before S14–S16. |
| Total Steps | 16 (S0–S16) |
| Total Estimated Effort | 134 engineering hours (~17 working days) |
| Data Cost | $0 for 11 of 12 additions |
| Risk Level | Low — all new modules are additive; no existing code is modified in S0–S9 |
| CIO Sign-Off Required | Yes — before S3 (pipeline entry) and before S16 (production integration) |

### The One-Sentence Brief

Add four new data-fetch modules to V3's `mid/` directory, gate all of them behind a `prediction_layers.yaml` config with every flag `enabled: false`, then enable one module per observation window until the accuracy scorecard confirms improvement.

---

## Architecture Blueprint

### New Files Created by This Work Order

```
config/
  prediction_layers.yaml          ← S0: Master feature flag file (12 flags, all false)

mid/
  prediction_layer_runner.py      ← S1: Reads YAML, calls enabled modules, writes output
  prediction_layer_merge.py       ← S2: Merges prediction_layers.json → dataset_raw.json
  fetch_enhanced_capital_flow.py  ← S5: M4 — dark pool, FII/DII, block trades, sector rotation
  fetch_cheap_talk_filter.py      ← S6: M3 — Fed/market divergence (Stackelberg gap)
  fetch_credit_spreads.py         ← S7: M2 — credit spreads, CPI surprise, Fed futures path
  fetch_options_flow.py           ← S8: M1 — put/call ratio, IV skew, max pain, GEX, VIX term
```

### Modified Files

```
config/v3_pipeline.yaml           ← S3: Two new steps inserted before bluelotus_superforecast_engine.py
mid/research_report_generator.py  ← S9: Shadow renderer block appended at end of report
```

### New Pipeline Steps (insertion point: before line 138, before bluelotus_superforecast_engine.py)

```yaml
  - working_dir: mid
    script: prediction_layer_runner.py
    timeout_seconds: 600
  - working_dir: mid
    script: prediction_layer_merge.py
```

### Data Flow

```
Existing fetch_*.py modules (unchanged)
    ↓
[NEW] prediction_layer_runner.py
  → reads config/prediction_layers.yaml
  → calls each enabled fetch module
  → writes mid/prediction_layers.json
    ↓
[NEW] prediction_layer_merge.py
  → reads mid/prediction_layers.json
  → merges into dataset_raw.json under key "prediction_layers"
    ↓
bluelotus_superforecast_engine.py  ← now has enriched dataset_raw.json
    ↓
research_report_generator.py
  → [NEW] shadow renderer appended: prints prediction_layers fields
         alongside existing signals (shadow = display only, no weighting)
```

---

## Module Manifest: M1 through M4

| Module | ID | Script | Additions Covered | Sources | Effort |
|--------|----|--------|-------------------|---------|--------|
| Options Flow | M1 | `fetch_options_flow.py` | ADD-001, ADD-002, ADD-003, ADD-004, ADD-005 | CBOE (free), Futu option chain (existing) | 40 hrs |
| Credit Spreads | M2 | `fetch_credit_spreads.py` | ADD-009, ADD-010, ADD-012 (partial) | CME FedWatch (free), Cleveland Fed (free) | 20 hrs |
| Cheap Talk Filter | M3 | `fetch_cheap_talk_filter.py` | ADD-009 (divergence), BGTM-V1 Stackelberg gap | Fed futures (CME free), Fed stated path (FOMC) | 14 hrs |
| Enhanced Capital Flow | M4 | `fetch_enhanced_capital_flow.py` | ADD-006, ADD-007, ADD-008, ADD-011 | FINRA (free), SEBI/TWSE/KRX/SGX (free), Futu ETF (existing) | 34 hrs |

**Implementation sequence in S5–S8:** M4 first (lowest risk) → M3 → M2 → M1 (highest complexity)

---

## 16-Step Execution Plan

---

### S0 — Write `config/prediction_layers.yaml`

**Objective:** Create the master feature flag file. All 12 signals disabled. Zero pipeline impact.

**Risk:** None. File is not referenced by any existing code until S1 and S3 are complete.

**Reversible:** Delete the file. Done.

**Deliverable:**

```yaml
# Prediction Layer Expansion — PLEXP-001
# Set enabled: true to activate a signal. Default: all false.
# CIO authorization required before enabling any module.

prediction_layers:
  enabled: false   # Master switch — must be true for any module to run

  modules:

    # ── M4: Enhanced Capital Flow ──────────────────────────────────────────
    dark_pool_activity:
      enabled: false
      source: FINRA_ATS_weekly
      cost: zero
      layer: 2

    fii_dii_net_flow:
      enabled: false
      source: SEBI_TWSE_KRX_SGX_daily
      cost: zero
      layer: 2

    block_trade_detector:
      enabled: false
      source: SEC_TAQ_EOD
      cost: zero
      layer: 2

    sector_rotation_momentum:
      enabled: false
      source: Futu_ETF_OHLCV
      cost: zero
      layer: 4

    # ── M3: Cheap Talk Filter ──────────────────────────────────────────────
    fed_market_divergence:
      enabled: false
      source: CME_FedWatch_API
      cost: zero
      layer: 3

    cheap_talk_credibility_discount:
      enabled: false
      source: FOMC_stated_path_vs_futures
      cost: zero
      layer: 8

    # ── M2: Credit Spreads & Macro Enrichment ──────────────────────────────
    credit_spread_hy_ig:
      enabled: false
      source: FRED_ICE_BofA_OAS
      cost: zero
      layer: 3

    cpi_surprise_index:
      enabled: false
      source: Cleveland_Fed_nowcast
      cost: zero
      layer: 3

    fed_futures_implied_path:
      enabled: false
      source: CME_FedWatch_API
      cost: zero
      layer: 3

    # ── M1: Options Flow ───────────────────────────────────────────────────
    put_call_ratio:
      enabled: false
      source: CBOE_daily
      cost: zero
      layer: 5

    iv_surface_skew:
      enabled: false
      source: Futu_option_chain
      cost: zero
      layer: 5

    max_pain_level:
      enabled: false
      source: Futu_option_chain
      cost: zero
      layer: 5

    gamma_exposure:
      enabled: false
      source: Futu_option_chain
      cost: zero
      layer: 5

    vix_term_structure:
      enabled: false
      source: CBOE_daily
      cost: zero
      layer: 5

  shadow_mode: true   # When true: signals appear in report but do not weight forecasts
```

**Time estimate:** 1 hour

**CIO sign-off required:** No

---

### S1 — Write `mid/prediction_layer_runner.py`

**Objective:** Write the runner that reads `config/prediction_layers.yaml`, calls each enabled fetch module, and writes `mid/prediction_layers.json`.

**Design constraints:**
- Must respect `prediction_layers.enabled: false` master switch
- Must catch and log exceptions per module without aborting (consistent with `continue_on_step_error: true` pipeline doctrine)
- Must write `prediction_layers.json` even if all modules are disabled (empty dict `{}` is valid)
- Must not import or modify any existing pipeline module

**Output schema:**

```json
{
  "generated_at": "2026-06-23T09:15:00",
  "shadow_mode": true,
  "modules_enabled": ["dark_pool_activity", "fii_dii_net_flow"],
  "modules_disabled": ["put_call_ratio", "iv_surface_skew", "..."],
  "signals": {
    "dark_pool_activity": {
      "dark_pool_pct_volume": 0.38,
      "status": "ok"
    },
    "fii_dii_net_flow": {
      "fii_net_flow_usd_mn": -124.5,
      "status": "ok"
    }
  },
  "errors": {}
}
```

**Time estimate:** 4 hours

**CIO sign-off required:** No

---

### S2 — Write `mid/prediction_layer_merge.py`

**Objective:** Merge `prediction_layers.json` into `dataset_raw.json` under the key `prediction_layers`.

**Design constraints:**
- If `prediction_layers.json` does not exist: write warning, exit 0, do not crash
- If `dataset_raw.json` does not exist: write warning, exit 0
- Merge is non-destructive: existing keys in `dataset_raw.json` are never overwritten
- After merge: re-export `dataset_raw.json` (consistent with existing `export_dataset_raw.py` pattern)

**Time estimate:** 2 hours

**CIO sign-off required:** No

---

### S3 — Insert Two New Steps into `config/v3_pipeline.yaml`

**Objective:** Register the runner and merge hook in the live pipeline.

**CIO SIGN-OFF REQUIRED BEFORE THIS STEP.**

Rationale: This is the first step that modifies existing V3 infrastructure (the pipeline manifest). Although the new steps are additive and both modules are no-ops when all flags are `false`, the pipeline manifest change must be approved.

**Exact YAML change — insert before `bluelotus_superforecast_engine.py`:**

```yaml
  # ── PLEXP-001: Prediction Layer Expansion ──────────────────────────────
  - working_dir: mid
    script: prediction_layer_runner.py
    timeout_seconds: 600
  - working_dir: mid
    script: prediction_layer_merge.py
  # ── end PLEXP-001 insertion ─────────────────────────────────────────────
  - working_dir: .
    script: bluelotus_superforecast_engine.py
```

**Verification after insertion:** Run `python pipeline_validator.py` (or equivalent) to confirm the pipeline YAML loads without syntax errors.

**Time estimate:** 1 hour (edit + validate)

**CIO sign-off required:** YES

---

### S4 — Validate: Dry-Run One Full Pipeline Cycle

**Objective:** Run the complete V3 pipeline exactly once in dry-run or test mode to confirm the two new steps execute without error and produce `prediction_layers.json` (expected: empty signals dict with all modules disabled).

**Pass criteria:**
- Pipeline completes without error on new steps
- `mid/prediction_layers.json` exists and contains `"modules_enabled": []`
- `dataset_raw.json` contains the key `"prediction_layers": {}` or `"prediction_layers": {"signals": {}}`
- All 91 existing tests continue to pass

**Time estimate:** 2 hours

**CIO sign-off required:** No

---

### S5 — Write `mid/fetch_enhanced_capital_flow.py` (M4)

**Objective:** Implement the enhanced capital flow module. The first module to write because it uses the simplest data sources (public daily files) and has the lowest integration risk.

**Signals implemented:**

| Signal | Source | Method |
|--------|--------|--------|
| `dark_pool_pct_volume` | FINRA ATS weekly report | Download weekly CSV, extract ATS volume as % total reported |
| `fii_net_flow_usd_mn` | SEBI / TWSE / KRX / SGX | Parse daily published CSV/HTML tables per exchange |
| `block_trade_direction` | SEC TAQ EOD via EDGAR | Parse block-size trade reports (≥10,000 shares or ≥$1M) |
| `sector_rotation_top2` | Futu ETF OHLCV (existing connection) | Rolling 20-day relative strength vs SPY for XLK, XLE, XLF, XLV, XLC, XLI, XLU, XLP, XLB, XLRE |
| `sector_rotation_bottom2` | Same | Bottom 2 sectors by RS |

**Output added to `prediction_layers.json`:**

```json
"dark_pool_activity": {
  "dark_pool_pct_volume": 0.38,
  "source_date": "2026-06-20",
  "status": "ok"
},
"fii_dii_net_flow": {
  "fii_net_flow_usd_mn": -124.5,
  "coverage": ["SEBI", "TWSE"],
  "status": "ok"
},
"block_trade_detector": {
  "block_direction": "NET_SELL",
  "block_count_session": 14,
  "status": "ok"
},
"sector_rotation_momentum": {
  "top": ["XLE", "XLV"],
  "bottom": ["XLK", "XLC"],
  "status": "ok"
}
```

**Time estimate:** 34 hours (includes SEBI/TWSE/KRX/SGX parsing)

**CIO sign-off required:** No

---

### S6 — Write `mid/fetch_cheap_talk_filter.py` (M3)

**Objective:** Implement the Cheap Talk Filter — the BGTM-V1 Stackelberg Discount computed from the gap between the Fed's stated rate path and the market-implied path.

**Signals implemented:**

| Signal | Source | Method |
|--------|--------|--------|
| `fed_implied_rate_12m` | CME FedWatch API (free JSON) | Parse CME probability table → implied rate at 12-month horizon |
| `fed_stated_rate` | FOMC SEP (existing in V3 dataset_raw.json) | Read from dataset_raw.json |
| `stackelberg_divergence_bps` | Computed | `(fed_stated_rate - fed_implied_rate_12m) × 100` in basis points |
| `cheap_talk_credibility` | Computed | `1 / (1 + abs(stackelberg_divergence_bps) / 100)` → range [0, 1] |

**Interpretation:**
- `stackelberg_divergence_bps > 50`: Fed is more hawkish than market believes → market is underpricing tightening risk
- `stackelberg_divergence_bps < -50`: Market is more hawkish than Fed → equities facing downside risk from rate repricing
- `cheap_talk_credibility ≈ 1.0`: Fed and market are aligned → forward guidance is credible
- `cheap_talk_credibility < 0.5`: Significant divergence → Fed guidance may be discounted

**Time estimate:** 14 hours

**CIO sign-off required:** No

---

### S7 — Write `mid/fetch_credit_spreads.py` (M2)

**Objective:** Implement the Credit Spreads and CPI surprise module.

**Signals implemented:**

| Signal | Source | Method |
|--------|--------|--------|
| `hy_oas_bps` | FRED: ICE BofA US High Yield OAS (BAMLH0A0HYM2) | FRED API (free) GET latest value |
| `ig_oas_bps` | FRED: ICE BofA US Corp BBB OAS (BAMLC0A4CBBB) | FRED API (free) GET latest value |
| `credit_spread_ratio` | Computed | `hy_oas_bps / ig_oas_bps` — stress amplifier |
| `cpi_surprise_last` | Cleveland Fed Inflation Nowcasting | Parse latest actual minus prior nowcast delta |
| `fed_funds_futures_12m` | CME FedWatch (shared with M3) | Same endpoint as M3 — cached if M3 runs first |

**Interpretation of credit spreads:**
- HY OAS > 500 bps: credit stress — equity downside risk elevated
- HY OAS < 300 bps: credit benign — equity risk appetite normal
- Credit spread widening while equities are flat: leading indicator of equity decline (credit leads equities)

**Time estimate:** 20 hours

**CIO sign-off required:** No

---

### S8 — Write `mid/fetch_options_flow.py` (M1)

**Objective:** Implement the full options flow module. This is the highest-complexity module and the one with the largest expected accuracy impact.

**Signals implemented:**

| Signal | Source | Method |
|--------|--------|--------|
| `put_call_ratio_equity` | CBOE daily data file | Download `total_pc_ratio.csv` from cboe.com/data |
| `put_call_ratio_index` | CBOE daily | Same file, index-only column |
| `iv_skew_25d` | Futu option chain (existing connection) | Pull front-month option chain → compute 25-delta put IV minus 25-delta call IV |
| `max_pain_level` | Futu option chain | Full chain across all expirations → minimize total open interest dollar value |
| `gamma_exposure_bn` | Futu option chain | Net GEX = Σ (gamma × OI × multiplier × spot²) for all strikes/expirations |
| `vix_term_structure_ratio` | CBOE VIX and VIX3M files | `VIX_spot / VIX3M_spot` — inverted (>1.0) = near-term stress |

**Computation notes:**

```python
# Max pain: the strike S* that minimizes total option holder losses
# For each candidate strike S:
#   pain(S) = Σ_puts max(K - S, 0) × OI_put(K) + Σ_calls max(S - K, 0) × OI_call(K)
# S* = argmin pain(S)

# GEX: net market maker gamma exposure
# gamma_exposure = Σ_calls (gamma × OI × 100 × spot²/100)
#                - Σ_puts  (gamma × OI × 100 × spot²/100)
# Positive GEX → mean-reverting price behavior (MM buys dips, sells rallies)
# Negative GEX → trend-amplifying price behavior (MM sells dips, buys rallies)
```

**Output schema:**

```json
"options_flow": {
  "put_call_ratio_equity": 0.85,
  "put_call_ratio_index": 1.12,
  "iv_skew_25d": -0.032,
  "max_pain_level": 512.00,
  "max_pain_expiry": "2026-06-27",
  "gamma_exposure_bn": 1.24,
  "vix_term_structure_ratio": 0.94,
  "gex_regime": "POSITIVE_MEAN_REVERTING",
  "status": "ok"
}
```

**Time estimate:** 40 hours

**CIO sign-off required:** Yes — approval to increase Futu API option chain pull volume per cycle.

---

### S9 — Append Shadow Renderer to `mid/research_report_generator.py`

**Objective:** Display prediction layer signals in the generated report, clearly labeled as SHADOW (display-only, no influence on forecasts).

**Design constraints:**
- Append only — no modification of existing report sections
- Shadow block only renders if `prediction_layers.json` exists and `shadow_mode: true`
- If no prediction layers data is available, the section is silently omitted
- Shadow signals must NOT be consumed by ACMS-COP, NITE-PEI, STR, or any forecast module until CIO authorizes production integration in S16

**Shadow block format in report:**

```
══════════════════════════════════════════════════════════════
PREDICTION LAYER SIGNALS — SHADOW MODE (Display only. Not weighted in forecasts.)
══════════════════════════════════════════════════════════════

OPTIONS FLOW (Layer 5)
  Put/Call Ratio (Equity): 0.85  [NEUTRAL — range 0.7–1.0]
  Put/Call Ratio (Index):  1.12  [ELEVATED HEDGING]
  IV Skew (25-delta):     -0.032 [MILD TAIL HEDGING]
  Max Pain:              $512.00 [Expiry: 2026-06-27]
  Gamma Exposure:         +1.24B [POSITIVE — mean-reverting regime]
  VIX Term Ratio:          0.94  [NORMAL CONTANGO]

CREDIT SPREADS (Layer 3)
  HY OAS:              428 bps   [BENIGN — below 500 stress threshold]
  IG OAS:              142 bps   [BENIGN]
  Credit Spread Ratio:   3.01
  CPI Surprise (last):  -0.1pp   [DOVISH — below consensus]

CHEAP TALK FILTER (Layer 3/8)
  Fed Implied Rate (12M): 4.25%
  Fed Stated Rate:        4.50%
  Stackelberg Divergence: +25 bps [Fed more hawkish than market]
  Cheap Talk Credibility:  0.80   [HIGH — guidance credible]

ENHANCED CAPITAL FLOW (Layer 2)
  Dark Pool % Volume:    38.2%   [ELEVATED institutional activity]
  FII Net Flow:         -$124.5M [OUTFLOW — bearish for covered markets]
  Block Trade Direction: NET_SELL
  Sector Rotation:       TOP: XLE, XLV | BOTTOM: XLK, XLC

══════════════════════════════════════════════════════════════
END SHADOW SIGNALS
══════════════════════════════════════════════════════════════
```

**Time estimate:** 4 hours

**CIO sign-off required:** No — shadow mode is read-only display.

---

### S10 — Enable M4 (Enhanced Capital Flow) — Observation Window 1

**Objective:** Flip the master switch and M4 flags in `config/prediction_layers.yaml`. Observe for 2–4 weeks.

**YAML change:**

```yaml
prediction_layers:
  enabled: true   # ← changed from false

  modules:
    dark_pool_activity:
      enabled: true   # ← changed
    fii_dii_net_flow:
      enabled: true   # ← changed
    block_trade_detector:
      enabled: true   # ← changed
    sector_rotation_momentum:
      enabled: true   # ← changed
    # all other modules remain: enabled: false
```

**Observation criteria (2–4 weeks):**
- No errors in `mid/prediction_layers.json` for ≥ 10 consecutive cycles
- FII net flow and block trade direction visually consistent with observed price moves on ≥ 3 clearly directional sessions
- No performance regression in pipeline cycle time (target: < 39 min)
- CIO: review shadow section in 3 report cycles and confirm data looks reasonable

**Pass gate:** CIO verbal or written authorization to proceed to S11.

**Estimated calendar time:** 2–4 weeks

---

### S11 — Enable M3 (Cheap Talk Filter) — Observation Window 2

**Objective:** Enable M3 alongside M4. Add `fed_market_divergence` and `cheap_talk_credibility_discount` to enabled modules.

**Observation criteria:**
- Stackelberg Divergence values stable and directionally consistent with observed Fed communications
- No `status: error` in M3 output for ≥ 10 consecutive cycles
- CIO confirms divergence values are plausible relative to current policy environment

**Estimated calendar time:** 2–4 weeks

---

### S12 — Enable M2 (Credit Spreads) — Observation Window 3

**Objective:** Enable M2 alongside M3 and M4. All three lower-complexity modules running simultaneously.

**Observation criteria:**
- HY/IG OAS values consistent with Bloomberg/FRED crosscheck
- CPI surprise values consistent with published actuals
- Fed futures path consistent with CME FedWatch public display

**Estimated calendar time:** 2 weeks (credit spreads are well-established data)

---

### S13 — Enable M1 (Options Flow) — Observation Window 4

**Objective:** Enable M1 — all four modules now active in shadow mode.

**Pre-requisites for S13:**
- CIO sign-off on Futu API option chain volume increase (from S8)
- M4, M3, M2 all passing with `status: ok` for ≥ 20 consecutive cycles

**Observation criteria:**
- Put/call ratios consistent with CBOE public daily summary
- Max pain levels visually consistent with observed expiry-week price pinning behavior
- GEX regime label (POSITIVE/NEGATIVE) consistent with observed intraday price behavior on known expiry-week sessions
- IV skew consistent with VIX behavior (elevated fear = more negative skew)

**Estimated calendar time:** 3–4 weeks (most complex module, needs longest observation)

---

### S14 — Full Test Suite Expansion

**Objective:** Write pytest tests for all four new modules. Target: 100% coverage of signal computation logic. Bring total test count from 91 to ≥ 130.

**Test categories per module:**

| Module | Tests |
|--------|-------|
| `fetch_enhanced_capital_flow.py` | Parse FINRA CSV, handle missing file, FII flow sum, sector RS computation |
| `fetch_cheap_talk_filter.py` | Divergence computation, credibility formula, edge case: rates equal |
| `fetch_credit_spreads.py` | FRED response parse, credit ratio computation, CPI surprise delta |
| `fetch_options_flow.py` | Max pain algorithm (unit test with synthetic chain), GEX formula, put/call parse |
| `prediction_layer_runner.py` | Master switch off → empty output; one module enabled → calls only that module |
| `prediction_layer_merge.py` | Missing input file → graceful exit; correct merge key; no overwrites |

**Time estimate:** 16 hours

**CIO sign-off required:** No

---

### S15 — 30-Day Shadow Period (All Modules Active)

**Objective:** Run all four modules in shadow mode for 30 consecutive calendar days before any production integration.

**Pass criteria for 30-day shadow period:**
- All four modules: `status: ok` for ≥ 90% of cycles
- Zero pipeline aborts attributable to new modules
- Shadow section appears in ≥ 90% of generated reports
- CIO: qualitative review — do shadow signals align with observed market outcomes?

**Accuracy measurement (using WO-PROB-004 infrastructure, if deployed):**
- Compare H1 directional accuracy in the 30-day shadow period against the pre-enrichment archive baseline
- Expected: H1 accuracy begins trending toward 53–56% (Phase 1 target from THESIS-002)

**This step requires no code changes.** It is a pure observation and measurement period.

**Estimated calendar time:** 30 days (non-negotiable)

---

### S16 — CIO Integration Sign-Off

**Objective:** Authorize promotion of prediction layer signals from shadow-only to production weighting in the forecast engine.

**CIO SIGN-OFF REQUIRED FOR THIS STEP.**

**Deliverables for CIO review package:**
1. 30-day shadow period accuracy log (H1 directional accuracy before and after)
2. Module error rate table (% cycles with `status: ok` per module)
3. Sample shadow sections from ≥ 5 report cycles showing signal quality
4. THESIS-002 work order completion checklist (WO-PROB-001 through WO-PROB-004 status)

**Production integration scope (post CIO sign-off):**
- `shadow_mode: false` in `config/prediction_layers.yaml`
- `bluelotus_superforecast_engine.py`: add `prediction_layers` key as weighted input (weighting TBD by CIO)
- ACMS-COP: incorporate options flow signals in scenario probability computation
- NITE-PEI: incorporate credit spreads and Cheap Talk Filter in kill condition probability calibration

**This work order is COMPLETE at S16 CIO sign-off.** Post-integration accuracy tracking continues under WO-PROB-004 (THESIS-002).

---

## Risk Register

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Futu option chain pull increases cycle time > 39 min | Medium | Medium | Add `timeout_seconds: 600` to step; time option chain pull separately |
| CBOE/FINRA file format changes break parser | Low | Medium | Defensive parser with fallback to `status: error` (non-blocking) |
| SEBI/TWSE/KRX/SGX website scraping blocked | Medium | Low | M4 degrades gracefully to partial output; block trade and sector rotation still work |
| CME FedWatch API rate limit | Low | Low | Cache response for 6 hours; single daily pull sufficient |
| GEX computation produces outlier values | Low | Medium | Add sanity bounds: `abs(gex_bn) < 50` constraint with `status: warning` |
| Integration with ACMS-COP in S16 introduces regression | Medium | High | Revert `shadow_mode` to `true` immediately; S16 scope is CIO-authorized only |

---

## Governance Compliance

All steps in this work order comply with BLV3-DOCTRINE-010:

- `LLM_ORDER_GENERATION = FALSE` — unchanged throughout
- `ORDER_ROUTING_ENABLED = FALSE` — unchanged throughout
- `CIO_ONLY_MANUAL` — unchanged throughout; new signals are informational only until S16 CIO sign-off
- `shadow_mode: true` enforced through S15 — prediction layer signals carry zero weight in any automated computation until explicitly authorized

This work order does not enable automated trading, autonomous order generation, or any behavioral change to V3's production forecast weighting until S16, which requires explicit CIO written authorization.

---

## Execution Checklist

| Step | Description | Effort | CIO Sign-Off | Status |
|------|-------------|--------|-------------|--------|
| S0 | Write `config/prediction_layers.yaml` | 1 hr | No | PENDING |
| S1 | Write `mid/prediction_layer_runner.py` | 4 hrs | No | PENDING |
| S2 | Write `mid/prediction_layer_merge.py` | 2 hrs | No | PENDING |
| S3 | Insert steps into `config/v3_pipeline.yaml` | 1 hr | **YES** | BLOCKED — awaiting CIO |
| S4 | Validate dry-run one full cycle | 2 hrs | No | PENDING |
| S5 | Write M4 `fetch_enhanced_capital_flow.py` | 34 hrs | No | PENDING |
| S6 | Write M3 `fetch_cheap_talk_filter.py` | 14 hrs | No | PENDING |
| S7 | Write M2 `fetch_credit_spreads.py` | 20 hrs | No | PENDING |
| S8 | Write M1 `fetch_options_flow.py` | 40 hrs | **YES** (Futu API) | PENDING |
| S9 | Append shadow renderer to report generator | 4 hrs | No | PENDING |
| S10 | Enable M4, observe 2–4 weeks | 0 hrs | No | PENDING |
| S11 | Enable M3, observe 2–4 weeks | 0 hrs | No | PENDING |
| S12 | Enable M2, observe 2 weeks | 0 hrs | No | PENDING |
| S13 | Enable M1, observe 3–4 weeks | 0 hrs | **YES** (Futu) | PENDING |
| S14 | Full test suite (91 → ≥130 tests) | 16 hrs | No | PENDING |
| S15 | 30-day shadow period | 0 hrs | No | PENDING |
| S16 | CIO integration sign-off | — | **YES** | BLOCKED — awaiting S15 |

**Total engineering hours:** 134 hrs
**Total calendar time (including observation windows):** ~20 weeks from CIO authorization

---

## The Safest First Action

**S0 is the safest first action.** Write `config/prediction_layers.yaml` with all 12 modules `enabled: false`.

Zero risk. No existing code is touched. Fully reversible in 30 seconds (`rm config/prediction_layers.yaml`).

Say **"proceed"** to begin S0, or specify any step or module you want to start with.

---

*PLEXP-001 | BlueLotus V3 Prediction Layer Expansion Work Order*
*Classification: INTERNAL OPERATIONAL — NOT FOR DISTRIBUTION*
*Author: Chief Architect, Claude Code — Permanent Secretary, CLERK_ONLY*
*Date: 2026-06-23 | Status: PLANNING COMPLETE — AWAITING CIO AUTHORIZATION*
*Companion: THESIS-002 (BlueLotus_V3_Probability_Prediction_Gap_Thesis_20260623.md)*
