# Superforecasting, Brier Accountability, and the Event Influence Probability Weighted Effect (EIPE)
## A PhD-Level Thesis on BlueLotus V3’s Proprietary Forecasting Doctrine, Current Performance, and the Path to Calibration

---

**Author:** Soh Wee Kian — Chief Investment Officer, BlueLotus Fund  
**Institution:** BlueLotus V3 / SLICDO (Self-Learning Institutional Cognitive Digital Organization)  
**Research Support:** BlueLotus V3 Platform Team · Chief Clerk · Chief Strategist  
**Date:** 25 June 2026 · Singapore  
**Field:** Probabilistic Forecasting · Institutional Portfolio Intelligence · Event-Driven Finance  
**Classification:** BlueLotus Research Series · Superforecasting-EIPE · V3 Doctrine  
**Publication (HTML):** [superforecasting-eipe-thesis-v3.html](https://sohweekian.github.io/bluelotus/superforecasting-eipe-thesis-v3.html) *(GitHub Pages)*  
**Prior Art (BlueLotus):** [Superforecasting Thesis (May 2026)](https://sohweekian.github.io/bluelotus/superforecasting-thesis.html) · [Watchlist Superforecast Report (May 2026)](https://sohweekian.github.io/bluelotus/bluelotus-watchlist-superforecast.html)  
**Companion Theses:** `BGTM_V1_PhD_Thesis_GameTheory_NashEquilibrium_2026.md` · `BlueLotus_NITE_PEI_Integrated_Thesis.md` · `Prospective_Event_Intelligence.txt`

---

> *"The goal of probabilistic forecasting is to maximize the sharpness of the predictive distributions subject to calibration."*
>
> — Gneiting & Raftery (2007), *Strictly Proper Scoring Rules, Prediction, and Estimation*, Journal of the American Statistical Association.

---

> *"A forecast that cannot be scored is not a forecast; it is commentary."*
>
> — BlueLotus Prospective Event Intelligence doctrine (PEI, 2026), extending Tetlock & Gardner (2015).

---

> *"The Chef does not cook with tools that guess. The Chef cooks with tools that read, think, and tell the truth."*
>
> — Soh Wee Kian, CIO — BlueLotus Fund, 2026.

---

## Abstract

This thesis presents the **second generation** of BlueLotus superforecasting research. Where the inaugural [Superforecasting and Stock Market Trading thesis](https://sohweekian.github.io/bluelotus/superforecasting-thesis.html) (Research Commission 001, 26 May 2026) established the **epistemological case** for applying Tetlock-style probabilistic discipline to equity management — and where the [78-ticker Watchlist Superforecast Report](https://sohweekian.github.io/bluelotus/bluelotus-watchlist-superforecast.html) operationalised a **4-step valuation protocol** with pending Brier resolution on 24 August 2026 — this document records what BlueLotus V3 has **actually built, measured, and decided** as of June 2026.

We make six claims:

1. **Superforecasting in finance fails when it copies external vendors.** BlueLotus explicitly rejects benchmarking against commercial “accuracy score” products or outsourced crowd forecasts until our **own** method earns Brier maturity on our **own** question set.

2. **The correct sequence is test → calibrate → Event Influence Probability Weighted Effect (EIPE).** We do not fit regression or machine-learning price models to discover factors. We pre-register events, assign probabilities, declare effect templates, resolve against market data, and let Brier shrink overconfidence.

3. **BlueLotus V3 already operates a live Brier infrastructure** at institutional scale: `ticker_forecasts` → `forecast_resolutions` → method comparison, parallel CIO prediction ledger, PEI/NITE-PEI event branches, and BGTM game-theoretic probabilities (doctrine-008 cold-start blended).

4. **Current Brier performance is honest and mixed.** House method `BLUELOTUS_CONSERVATIVE` beats sell-side benchmark `ANALYST_CONSENSUS` on mean Brier at 7d/14d horizons (~0.271 vs ~0.280 at 7d) but exhibits **weak directional accuracy** (~46% at 7d). CIO gut predictions show early promise (DB mean Brier 0.125 on 4 resolved; JSONL ledger 0.23 on 25 resolved) but sample size is insufficient for promotion.

5. **Academic literature supports our anti-ML posture.** Financial machine learning exhibits spurious predictability, backtest overfitting, and forecast collapse under squared loss when signal is weak (Bailey et al., 2014; Goyal & Welch, 2008; recent arXiv 2026 literature). Proper scoring rules (Brier) reward **honest** probabilities, not complex models (Gneiting & Raftery, 2007).

6. **EIPE is our proprietary synthesis:** price views emerge from summing **event influence × calibrated probability × pre-registered effect × evidence-tier weight**, anchored to conservative valuation — not from coefficient fitting on price panels.

**Keywords:** Superforecasting, Brier Score, Murphy Decomposition, Calibration, Event Influence, EIPE, SLICDO, NITE-PEI, PEI, BGTM, Proper Scoring Rules, CIO Gut Predictions

---

## Table of Contents

1. [Introduction](#chapter-1--introduction)
2. [Literature Review: What Works and What Does Not](#chapter-2--literature-review-what-works-and-what-does-not)
3. [Lineage: From May 2026 Thesis to V3 Operations](#chapter-3--lineage-from-may-2026-thesis-to-v3-operations)
4. [BlueLotus V3 Architecture: What We Do Now](#chapter-4--bluelotus-v3-architecture-what-we-do-now)
5. [Current Brier Score Ledger (June 2026)](#chapter-5--current-brier-score-ledger-june-2026)
6. [Session Doctrine: Our Own Superforecasting Method](#chapter-6--session-doctrine-our-own-superforecasting-method)
7. [The EIPE Framework (Formal)](#chapter-7--the-eipe-framework-formal)
8. [CIO Gut Predictions and Joint Learning](#chapter-8--cio-gut-predictions-and-joint-learning)
9. [Three-Phase Roadmap to Brier → 0](#chapter-9--three-phase-roadmap-to-brier--0)
10. [Limitations and Honest Assessment](#chapter-10--limitations-and-honest-assessment)
11. [Conclusions](#chapter-11--conclusions)
12. [References](#chapter-12--references)

---

## Chapter 1 — Introduction

### 1.1 The Problem

Financial markets are prediction engines. Every position embeds a forecast. Yet the empirical record of expert prediction — across geopolitics, macroeconomics, and security analysis — is sobering. Tetlock’s twenty-year *Expert Political Judgment* study (2005) found that many domain experts perform near chance on structured forecasting tasks, with an **inverse correlation between media fame and accuracy** (Tetlock & Gardner, 2015).

Within that distribution, however, a thin tail of **superforecasters** — identified through IARPA’s Good Judgment Project tournaments — demonstrated **persistent** superiority measured by the Brier score, updating beliefs frequently, decomposing questions, and balancing inside/outside views (Mellers et al., 2015).

BlueLotus Fund, operating as a CIO-led institutional intelligence organisation in Singapore, asks a sharper question than the May 2026 thesis:

> **Can we build our own superforecasting institution — not by importing someone else’s workflow, but by measuring our own probabilities against our own resolutions until Brier forces honesty?**

This thesis answers: **we are building it; it is not mature yet; the architecture is correct; the discipline is the moat.**

### 1.2 Research Questions

| ID | Question |
|----|----------|
| **RQ1** | What does academic superforecasting research identify as **effective** vs **ineffective** practice? |
| **RQ2** | What has BlueLotus V3 implemented operationally as of June 2026? |
| **RQ3** | What are our **measured** Brier scores by method, horizon, and forecaster (CIO vs engine)? |
| **RQ4** | What method did the June 2026 design sessions specify — and how does **EIPE** relate to price forecasting? |
| **RQ5** | What is the principled path to **Brier → 0** (perfect calibration on binary resolutions) without ML overfitting? |

### 1.3 Methodology

This thesis is **not** an exercise in backtested alpha. It is:

- **Descriptive** — documenting V3 pipeline components with file/DB traceability (doctrine-001: memory before aesthetics).
- **Evaluative** — reporting Brier statistics from `bluelotus3` MySQL resolutions without selective omission.
- **Prescriptive** — specifying EIPE as the Phase-3 price engine, deferred until Phase-1 testing and Phase-2 calibration complete.
- **Governance-bound** — all outputs advisory; `CIO_ONLY_MANUAL`; no order routing (doctrine-003).

---

## Chapter 2 — Literature Review: What Works and What Does Not

### 2.1 Proper Scoring Rules and the Brier Score

Gneiting and Raftery (2007) establish the foundational principle:

> *"In prediction problems, proper scoring rules encourage the forecaster to make careful assessments and to be honest."*

A scoring rule is **strictly proper** if the expected score is uniquely maximised (or minimised, depending on convention) when the forecaster reports the true probability. The **Brier score** for binary events:

\[
\mathrm{BS} = \frac{1}{N}\sum_{i=1}^{N}(f_i - o_i)^2
\]

where \(f_i \in [0,1]\) is the stated probability and \(o_i \in \{0,1\}\) is the realised outcome. Range: **0 (perfect)** to **1 (worst)** under the standard [0,1] formulation. The **ignorance baseline** — always predicting 0.5 — yields BS = **0.25**.

Gneiting & Raftery further argue that good probabilistic forecasts maximise **sharpness subject to calibration**: probabilities should be decisive *only when* they are *also* reliable.

**What works:** Measuring forecasts with strictly proper scores; publishing probabilities before resolution; scoring every forecast.

**What fails:** Narrative predictions without numbers; retroactive relabelling of vague calls as “correct”; optimising for direction without calibration.

### 2.2 Murphy Decomposition: Where Errors Live

Murphy (1973); Murphy & Winkler (1987); DeGroot & Fienberg (1983) decompose the Brier score:

\[
\mathrm{BS} = \underbrace{\mathrm{Reliability}}_{\text{calibration}} - \underbrace{\mathrm{Resolution}}_{\text{discrimination}} + \underbrace{\mathrm{Uncertainty}}_{\text{base-rate variance}}
\]

| Component | Meaning | Improvement lever |
|-----------|---------|-------------------|
| **Reliability** | Stated 70% should happen ~70% of the time | Shrink overconfidence; tier caps |
| **Resolution** | Forecasts differ from base rate when right | Better event selection; EIPE effects |
| **Uncertainty** | Inherent unpredictability of domain | Cannot be eliminated; choose tractable questions |

Mellers et al. (2015) report superforecasters achieve **lower Brier**, **higher resolution**, and **better calibration** than comparison groups — superforecasters: average calibration ~0.01 vs ~0.03–0.04 for others (Table 1, *Perspectives on Psychological Science*).

**BlueLotus implication:** Our 7d directional accuracy ~46% with Brier ~0.27 suggests **reliability and resolution are misaligned** — probabilities may be poorly calibrated even when mean Brier beats sell-side.

### 2.3 Tetlock: Cognitive Practices That Work

From *Expert Political Judgment* (2005), *Superforecasting* (Tetlock & Gardner, 2015), and Mellers et al. (2015):

| Practice | Evidence | BlueLotus V3 mapping |
|----------|----------|----------------------|
| **Fox thinking** (many small ideas) | Foxes outperform hedgehogs | 8-Lens, contradiction mapper, multi-agent council |
| **Outside view / base rates** | Start with reference class | Sector P/E in engine; PEI base rates (planned) |
| **Belief updating** | Superforecasters update more often | NITE-PEI Bayesian posterior; forecast revision table (planned) |
| **Granular questions** | Clairvoyance test — no ex-post disputes | `resolution_criteria` in CIO/PEI predictions |
| **Cognitive debiasing training** | GJP Year-1 uplift | SLICDO learning cycle; post-mortem labels |
| **Elite teams** | Top performers in teams beat individuals | CIO + Clerk + Strategist; not outsourced crowd |
| **Brier tournaments** | Incentivises honesty | `forecast_resolutions`, CIO ledger |

**What fails (Tetlock & Gardner, 2015; Cato Institute summary):**

- **Hedgehog certainty** — single grand theories filtering all evidence.
- **Famous pundits** — inverse fame-accuracy correlation.
- **One-shot predictions** without tracking.
- **Hindsight bias** — “I knew it all along” without archived probabilities.

> *"Superforecasters update much more frequently, on average, than regular forecasters."* — Tetlock & Gardner (2015).

### 2.4 Mellers et al. (2015): Discovery and Cultivation

The IARPA tournaments demonstrate:

> *"Superforecasters are partly discovered and partly created."*

Interventions that **worked**: tracking top performers into elite teams; cognitive debiasing; collaborative teams.

Interventions with **mixed evidence**: prediction markets vs team aggregation (context-dependent).

**Critical humility** from the same paper:

> *"The mere fact that a given strategy 'won' a tournament does not mean that it was optimal or even close to optimal."*

BlueLotus takes this seriously: **winning against `ANALYST_CONSENSUS` on early horizons does not certify EIPE or engine promotion.**

### 2.5 What Fails in Financial ML and Regression Forecasting

The June 2026 design sessions explicitly rejected **ML/regression on price** as the next step. Academic support:

**Bailey, Borwein, López de Prado & Zhu (2014)** — *Pseudo-Mathematics and Financial Charlatanism*:

> *"High simulated performance is easily achievable after backtesting a relatively small number of alternative strategy configurations... investors can be easily misled into allocating capital to strategies that appear to be mathematically sound."*

**Goyal & Welch (2008)** — aggregate return prediction models rarely beat simple benchmarks out-of-sample.

**Recent ML finance literature (2026)** — spurious predictability under adaptive search; falsification audits required; transformer models suffer **forecast collapse** under squared loss when conditional mean signal is weak.

**What works instead for BlueLotus:**

| Approach | Rationale |
|----------|-----------|
| **Pre-registered event questions** | Clairvoyance test; binary resolution |
| **Brier accountability** | Proper scoring; no gaming |
| **Declared effect templates** | Auditable; updated only on resolution |
| **Walk-forward resolution** | `historical_prices` at horizon date |
| **CIO rationale archive** | Learn from causal_chain failures |

### 2.6 Synthesis: The BlueLotus Epistemic Position

We adopt **superforecasting scoring** without adopting **superforecasting cosplay**. We do not hire a crowd platform. We do not import an external Accuracy Score. We:

1. State probabilities.
2. Archive rationale.
3. Resolve against predefined criteria.
4. Compute Brier.
5. Shrink and revise.

This is closer to **institutional meteorology** than to **quantitative alpha mining**.

---

## Chapter 3 — Lineage: From May 2026 Thesis to V3 Operations

### 3.1 Research Commission 001 (26 May 2026)

The published [Superforecasting Thesis](https://sohweekian.github.io/bluelotus/superforecasting-thesis.html) proposed:

- **4-step valuation:** 8-Lens evidence → base valuation (EPS × sector P/E) → macro/strategic adjustments → Thorp margin of safety.
- **Metrics suite:** Brier, calibration error, resolution, Kelly edge, Sharpe, win rate.
- **Kelly as execution layer** for probabilistic outputs.
- **Ethnographic observation** of BlueLotus as a fox-like, multi-lens organisation.

**Status June 2026:** Steps 1–4 are codified in `bluelotus_superforecast_engine.py` (engine version `BlueLotus_Superforecast_v1.0`). Brier tracker is **no longer PENDING** — see Chapter 5.

### 3.2 Watchlist Superforecast Report (26 May 2026)

The [78-ticker Watchlist Report](https://sohweekian.github.io/bluelotus/bluelotus-watchlist-superforecast.html) documented:

- Live Moomoo OpenD prices and analyst targets (74/78 coverage).
- Conviction distribution: 29 high / 26 medium / 23 avoid.
- Brier resolution date **2026-08-24** (first major cohort).
- **BS baseline 0.25**; target **< 0.20** good; **< 0.15** superforecaster band (per thesis labels).

**Status June 2026:** V3 engine runs **~200 tickers** per cycle with **five horizons** (7/14/30/60/90 days). Resolution pipeline has **93,107** horizon resolutions logged; 30/60/90d cohorts await maturity.

### 3.3 V2 → V3 Brier Harvest (June 2026)

V2 (`bluelotus2`) is frozen archive DNA (doctrine-004). A one-way harvest imported historical `ticker_forecasts` and resolutions into `bluelotus3` for continuity. **Protected database must not be mutated going forward.**

---

## Chapter 4 — BlueLotus V3 Architecture: What We Do Now

### 4.1 Pipeline Position

The superforecasting block sits in the intelligence golden path (`config/v3_pipeline.yaml`):

```
… → institutional_quant_pipeline → bluelotus_superforecast_engine.py
  → forecast_resolution_tracker.py → forecast_resolution_backfill.py
  → forecast_method_comparison.py → governance → reports → NITE-PEI → SLICDO
```

### 4.2 Engine Layer: `BLUELOTUS_CONSERVATIVE`

`research/bluelotus_superforecast_engine.py` generates per-ticker forecasts:

| Element | Mechanism |
|---------|-----------|
| **Anchor** | EPS × sector median P/E (profitable); price proxy (loss-makers) |
| **Adjustments** | Macro regime, strategic theme, capital flow, ECE event (±5% cap) |
| **Safety margin** | 5–18% Thorp-style haircut |
| **Probabilities** | Heuristic: base 0.50 + return/flow/ECE/analyst agreement − quality penalty; clamped ~0.34–0.72 |
| **Horizons** | 7, 14, 30, 60, 90 days with `HORIZON_WEIGHTS` |
| **Opponent** | `ANALYST_CONSENSUS` benchmark (Moomoo targets) — not house method |

**Research-only.** No order routing. Inserts `ticker_forecasts` + JSON mirrors.

### 4.3 Resolution Layer: `brier_resolution_core.py`

Strict improvement over naive implementations:

- Resolves at **horizon date** using `historical_prices` (K_DAY close on or before resolution date).
- Falls back to live tape only within 3 days when history missing.
- Binary outcome: UP/DOWN/NEUTRAL per `event_definition` in engine.
- Brier: \((p - o)^2\) per horizon.

### 4.4 Accountability Layer: Method Comparison

`research/forecast_method_comparison.py` publishes:

- `research/research_forecast_accuracy_report.txt`
- `data/brier/forecast_method_comparison_latest.json`

### 4.5 Event Intelligence Layer (Parallel Tracks)

| System | Role in superforecasting |
|--------|--------------------------|
| **ECE** (`event_correlations` in ingest) | Theme basket moves, tier-capped confidence (T0–T4) |
| **PEI** | Pre-registered branches, resolution criteria, scenario trees |
| **NITE-PEI** | Bayesian `P_posterior` updates on evidence |
| **BGTM** | Nash/QRE equilibria → Geo-LR bridge (doctrine-008: blend until `calibration_n ≥ 30`) |
| **CIO predictions** | Gut calls quantified + rationale (`CIO_GUT_PREDICTION`) |
| **Kelly-NITE coupler** | Advisory sizing from posterior × analyst upside (manual execution) |

### 4.6 Governance Constraints

| Doctrine | Constraint on forecasting |
|----------|---------------------------|
| BLV3-DOCTRINE-002 | Governance before automation |
| BLV3-DOCTRINE-003 | CIO-only manual execution |
| BLV3-DOCTRINE-004 | V2 archive read-only |
| BLV3-DOCTRINE-008 | Game theory = expert-model equilibria, not predictions |

---

## Chapter 5 — Current Brier Score Ledger (June 2026)

*Snapshot: `forecast_method_comparison_latest.json` generated 2026-06-25 02:40 SGT; CIO ledger 2026-06-24.*

### 5.1 Ticker Engine — Aggregate

| Metric | Value |
|--------|-------|
| **Forecast rows** | 125,587 |
| **Resolutions** | 93,107 |
| **Horizons resolved** | 7d, 14d only (30/60/90 pending maturity) |
| **Skipped (no price bar)** | 262 |

### 5.2 Method × Horizon Mean Brier

| Method | Horizon | *n* | Mean Brier | Directional accuracy |
|--------|---------|-----|------------|----------------------|
| **BLUELOTUS_CONSERVATIVE** | 7d | 34,591 | **0.271** | 46.0% |
| ANALYST_CONSENSUS | 7d | 32,563 | 0.280 | 51.1% |
| **BLUELOTUS_CONSERVATIVE** | 14d | 13,188 | **0.278** | 43.0% |
| ANALYST_CONSENSUS | 14d | 12,765 | 0.295 | 55.1% |

**Interpretation:**

- House method **beats sell-side benchmark on mean Brier** at both horizons — consistent with May thesis goal of conservative discipline.
- **Directional accuracy below 50%** for house method at 7d/14d is a **reliability alarm**: probabilities and direction labels are not yet coherent.
- Both methods sit **above ignorance baseline 0.25** on mean Brier — **neither is yet “good forecaster” band (<0.20)** from the Watchlist report rubric.
- **30/60/90d** horizons — critical for CIO strategic calls — are **not yet scored**; promotion decisions wait until ~September 2026.

### 5.3 CIO Gut Prediction Ledger

| Metric | Value |
|--------|-------|
| **Open** | 6 (incl. oil-65 peace bundle, space rebounce) |
| **Resolved (DB)** | 4 |
| **Mean Brier (DB)** | **0.125** |
| **JSONL deduped resolved** | 25 |
| **JSONL mean Brier** | **0.23** |
| **Posture** | `early_calibration` |

**Notable resolved calls:**

| Prediction | *P* | Outcome | Brier |
|------------|-----|---------|-------|
| NVDA support @ $199.25 | 1.00 | TRUE | **0.00** |
| Relief rally / peace-Vol | 0.50 | FALSE | 0.25 |
| Space risk-on ex-SPCX | 0.50 | FALSE | 0.25 |

**Lesson:** Perfect Brier on **certain** calls (*P*=1) is trivially 0 or catastrophic; **0.50 calls** that fail score 0.25 — exactly ignorance penalty. CIO calibration work is to **stop clustering at 0.50** when gut has a view, and to **avoid P=1.0** unless resolution is definitional.

### 5.4 Comparison to May 2026 Watchlist Targets

| Band (Watchlist thesis) | Threshold | V3 Status |
|-------------------------|-----------|-----------|
| Baseline | 0.25 | Engine ~0.27–0.28 (slightly worse than coin flip) |
| Good | < 0.20 | **Not yet** |
| Superforecaster | < 0.15 | **Not yet** |
| Mellers et al. elite teams | ~0.01 calibration error | **Aspiration; years of data required** |

---

## Chapter 6 — Session Doctrine: Our Own Superforecasting Method

This chapter records the **June 2026 design session** arc — without benchmarking external fund software.

### 6.1 Rejected Path: Copy External Workflow

The session explicitly rejected:

- Importing commercial “accuracy score” portfolio products as architecture template.
- Outsourcing macro probabilities to third-party superforecaster feeds as **primary** input.
- Fitting **ML/regression** on price features to discover “what moves price” before Brier maturity.

**Reason:** Our method is **untested at 90d**; copying others optimises for their question set, not ours.

### 6.2 Accepted Path: Three Phases

```
Phase 1 — TEST (now → Sep 2026)
  Run house engine + CIO gut ledger unchanged.
  Fill Brier DB across 7→14→30→60→90d horizons.
  Do NOT rewrite coefficients.

Phase 2 — CALIBRATE (after resolutions)
  Reliability buckets by theme, regime, horizon.
  Murphy decomposition; tier-cap audit on ECE.
  Shrink: P_cal = 0.5 + (P_raw - 0.5) × (1 - mean_brier_theme)

Phase 3 — EIPE (after calibration proves ledger)
  Parallel method BLUELOTUS_EIPE vs BLUELOTUS_CONSERVATIVE.
  Promote only if Brier superior on same question set.
```

### 6.3 Core Philosophical Commitments

1. **Memory before aesthetics** — every prediction archived with rationale.
2. **Event-first, valuation-anchored** — flip engine from “valuation + event nudge” to “events + anchor.”
3. **No ML alpha mining** — effects are **declared**, not **discovered** from price.
4. **CIO gut is a first-class forecaster** — quantified, scored, learned from.
5. **Game theory supplies P, not price** — BGTM doctrine-008 cold-start blend.

### 6.4 Relationship to May 2026 4-Step Protocol

| May 2026 Step | V3 Status | EIPE Evolution |
|---------------|-----------|----------------|
| ① 8-Lens aggregation | Dataset + reports | Becomes **evidence tier** weights |
| ② Base valuation | Engine anchor | **Remains anchor only** |
| ③ Macro/strategic adj | Heuristic coeffs | **Retired** → event effects |
| ④ Thorp margin | Safety margin | **Retained** on anchor |

---

## Chapter 7 — The EIPE Framework (Formal)

### 7.1 Definition

**Event Influence Probability Weighted Effect (EIPE)** is BlueLotus V3’s proprietary method for translating **event probabilities** into **price targets and forecast probabilities** without regression on historical price panels.

For ticker \(t\), horizon \(h\):

\[
\Delta \hat{r}_{t,h} = \sum_{i \in \mathcal{E}_t} w_i \cdot P_i^{(\mathrm{cal})} \cdot E_{i \rightarrow t,h} \cdot \sigma_i
\]

\[
\hat{P}_{t,h} = \mathrm{price\_anchor}_t \cdot (1 + \Delta \hat{r}_{t,h})
\]

\[
P(\mathrm{hit}_{t,h}) = g\!\left(P_{\mathrm{base}},\, |\Delta \hat{r}_{t,h}|,\, \mathrm{calibration\_shrink}\right)
\]

Where:

| Symbol | Source | Meaning |
|--------|--------|---------|
| \(\mathcal{E}_t\) | PEI + ECE + BGTM + CIO registry | Active events affecting \(t\) |
| \(P_i^{(\mathrm{cal})}\) | NITE-PEI / CIO / Nash branch | Calibrated event probability |
| \(E_{i \rightarrow t,h}\) | `event_effect_registry.yaml` | Pre-registered % move template |
| \(w_i\) | ECE evidence tier (T0–T4) | Trust cap |
| \(\sigma_i\) | Branch sign (+1/−1) | Direction |
| \(\mathrm{price\_anchor}_t\) | EPS × sector P/E | Valuation floor/ceiling reference |
| \(g\) | Auditable shrink function | Maps effect size → binary hit probability |

### 7.2 What EIPE Is Not

| EIPE is NOT | Why |
|-------------|-----|
| OLS on returns | Overfits; fails OOS (Goyal & Welch; Bailey et al.) |
| Neural price forecast | Forecast collapse under weak signal |
| Analyst target anchor | Sell-side herding opponent only |
| BGTM equilibrium as fact | Expert-model per doctrine-008 |

### 7.3 Effect Template Registry (Planned Artifact)

```yaml
# config/event_effect_registry.yaml (Phase 3)
peace_oil_decline:
  event_id: CIO_PRED_OIL65_HORMUZ_OPEN_20260625
  effects:
  - ticker: XLE
    horizon_14d: -0.03
  - ticker: GLD
    horizon_14d: -0.02
  - ticker: ASTS
    horizon_14d: +0.05
  calibration_source: ECE_basket_median_post_resolution
```

Templates are **edited by CIO**; realised ECE basket medians **update declared effects** after resolution — **empirical calibration of declared structure**, not discovery of hidden factors.

### 7.4 Brier Optimisation Logic

Brier → 0 requires:

1. **Perfect calibration** — when you say 0.80, you're right 80% of the time.
2. **Correct resolution criteria** — binary event matches economic question.
3. **No overconfidence** — extremes only with evidence.

EIPE does not guarantee low Brier; **honest P** does. EIPE structures **where P and effects come from** so post-mortems are interpretable:

- Wrong **P** → game theory / CIO / PEI layer.
- Wrong **E** → effect template miss.
- Wrong **anchor** → valuation layer.
- Wrong **timing** → horizon weight.

---

## Chapter 8 — CIO Gut Predictions and Joint Learning

### 8.1 Problem Statement (CIO, June 2026)

> *"Right now I am relying on my gut feeling to give the predictions, but we need to quantify it, give a Brier score to it, and I'll input the rationale on why I am predicting it as such, so that we can learn from this together."*

### 8.2 Operational Response

| Artifact | Purpose |
|----------|---------|
| `data/cio/templates/cio_gut_prediction_template.json` | Structured rationale schema |
| `scripts/register_cio_gut_prediction.py` | CLI registration |
| `scripts/witness_cio_gut_prediction.py` | Manual resolution + lesson |
| `scripts/run_cio_prediction_brier.py` | Brier cycle |
| `scripts/run_cio_prediction_learning.py` | Rationale + Brier + lesson report |
| `learning/cio_prediction_learning_report.py` | Joint learning output |

### 8.3 Rationale Schema

```json
"prediction_rationale": {
  "gut_read": "Plain language",
  "why_now": "Why this session/week",
  "causal_chain": ["link1", "link2", "link3"],
  "evidence_supporting": ["..."],
  "evidence_against": ["..."],
  "what_would_change_mind": ["..."],
  "confidence_source": "GUT_PLUS_TAPE"
}
```

### 8.4 Learning Loop

```
CIO states P + rationale
    → archived in data/cio/manual_cio_*.json
    → registry MySQL + SLICDO claims
    → horizon passes / CIO witnesses
    → Brier scored
    → learning report: lesson ties miss to causal_chain / evidence_against
    → Phase-2 shrink adjusts future P by theme
    → EIPE templates updated on resolution
```

### 8.5 Open CIO Predictions (June 2026)

| ID | *P* | Horizon | Theme |
|----|-----|---------|-------|
| `CIO_PRED_OIL65_HORMUZ_OPEN_20260625` | 0.65 | ~8 Jul 2026 | Peace dividend / Hormuz |
| `CIO_PRED_GOLD_BELOW_4000_AT_OIL65_20260625` | 0.70 | linked | Safe-haven fade |
| `CIO_PRED_SILVER_BELOW_55_AT_OIL65_20260625` | 0.65 | linked | Precious metals |
| `CIO_PRED_GOLD_MINERS_BOTTOM_AT_OIL65_20260625` | 0.70 | linked | Sleeve bottom |
| `CIO_PRED_SPACE_HIGHER_AT_OIL65_20260625` | 0.60 | linked | Peace risk-on |
| `CIO_PRED_20260625_SPACE_REBOUNCE_SESSION` | 0.45 | 25–26 Jun | Tactical rebounce |

These form the **first EIPE template bundle** when oil-65 resolves.

---

## Chapter 9 — Three-Phase Roadmap to Brier → 0

### 9.1 What “Brier → 0” Means in Practice

Per-event Brier is 0 only when:

- \(P \rightarrow 1\) and outcome = TRUE, or
- \(P \rightarrow 0\) and outcome = FALSE.

**Portfolio-level mean Brier → 0** is asymptotic — requires thousands of well-calibrated forecasts. Realistic institutional targets:

| Stage | Mean Brier | Milestone |
|-------|------------|-----------|
| Ignorance | 0.25 | Coin flip |
| Competent | < 0.20 | Beat baseline reliably |
| Elite | < 0.15 | Superforecaster band (Watchlist) |
| CIO engine | < 0.10 | Requires years; fox discipline |

### 9.2 Phase 1 Deliverables (Complete / In Progress)

- [x] Superforecast engine in pipeline
- [x] Historical resolution core
- [x] 93k+ resolutions
- [x] CIO prediction Brier cycle
- [x] Gut prediction registration tooling
- [ ] 30/60/90d horizon maturity
- [ ] Fix 262 missing historical price bars
- [ ] Enrich legacy CIO files with `prediction_rationale`

### 9.3 Phase 2 Deliverables

- [ ] `forecast_calibration_report.py` — reliability diagrams
- [ ] Murphy decomposition by `sector_theme`, `regime`
- [ ] Automatic shrink on `stated_probability`
- [ ] PEI branch Brier (`calibration` block currently null)
- [ ] Forecast revision lineage table

### 9.4 Phase 3 Deliverables

- [ ] `config/event_effect_registry.yaml`
- [ ] `BLUELOTUS_EIPE` parallel engine
- [ ] Head-to-head method promotion gate
- [ ] ENF / Event-Nash parallel method (research-only until quarter closes)

### 9.5 Anti-Patterns That Prevent Brier → 0

| Anti-pattern | Effect |
|--------------|--------|
| ML price regression | Overfit; unscoreable opacity |
| Copying external vendor workflow | Wrong question set |
| Promoting engine before 90d | False confidence |
| P = 1.0 on soft questions | Brier catastrophe on miss |
| P = 0.50 always | Never beats 0.25 on misses |
| Vague resolution criteria | Ex-post disputes (violates clairvoyance test) |
| Mutating V2 archive | Breaks audit trail |

---

## Chapter 10 — Limitations and Honest Assessment

### 10.1 Sample and Horizon

- **7d/14d only** — strategic CIO questions live at 30–90d.
- **CIO n=4 DB / n=25 JSONL** — learning report posture is `early_calibration`, not `calibration_active`.
- **Engine directional accuracy < 50%** — house method not yet internally consistent.

### 10.2 Structural

- Event adjustment in engine is **±5% cap** — underpowered vs EIPE ambition.
- Kelly coupler still uses **analyst P** in places — not yet Brier-weighted house P.
- `prediction_rationale` missing on pre-June-25 CIO bundles — gut archived in `strategic_thinking` prose only.

### 10.3 Epistemic

- BGTM payoffs are **expert-initialised** — equilibrium is model output, not ground truth.
- Markets are **reflexive** — PEI Hawkes discussion acknowledges endogeneity risk.
- **Brier → 0** is a limit, not a Q3 2026 OKR.

---

## Chapter 11 — Conclusions

BlueLotus V3 has crossed from **thesis to instrumentation**. The May 2026 [Superforecasting Thesis](https://sohweekian.github.io/bluelotus/superforecasting-thesis.html) asked whether Tetlock’s discipline could apply to a Singapore CIO-led fund; the [Watchlist Report](https://sohweekian.github.io/bluelotus/bluelotus-watchlist-superforecast.html) asked whether 78 tickers could carry explicit probabilities into an August resolution. **June 2026 answers: yes — and the first numbers are humbling.**

We lead sell-side consensus on mean Brier at short horizons, yet we **fail directional accuracy** and sit **above the 0.25 ignorance line**. Our CIO ledger shows flashes of excellent calibration (NVDA support) and costly 50/50 calls on session predictions. **This is exactly what superforecasting infrastructure is for** — replacing gut narrative with scored memory.

The session doctrine is clear:

1. **Our method first** — test without copying.
2. **Calibrate second** — shrink overconfidence with Murphy-aware diagnostics.
3. **EIPE third** — event influence × probability × declared effect → price; **not** ML regression.

Academic literature supports the discipline (Gneiting & Raftery; Tetlock; Mellers) and our scepticism of financial ML (Bailey et al.; Goyal & Welch; 2026 falsification literature).

**The moat is not a secret formula. It is a public ledger of stated probabilities, archived rationales, and Brier scores that survive audit.**

The work ahead is not more complexity. It is **more resolutions**, **richer rationales**, and **honest calibration** — until the Watchlist’s “good forecaster” band (< 0.20) is earned on our own terms.

---

## Chapter 12 — References

### Superforecasting and Judgment

- Brier, G. W. (1950). Verification of forecasts expressed in terms of probability. *Monthly Weather Review*, 78(1), 1–3.
- Tetlock, P. E. (2005). *Expert Political Judgment: How Good Is It? How Can We Know?* Princeton University Press.
- Tetlock, P. E., & Gardner, D. (2015). *Superforecasting: The Art and Science of Prediction.* Crown.
- Tetlock, P. E., & Mellers, B. A. (2002). The great rationality debate. *Psychological Science*, 13(1), 94–99.
- Mellers, B., Stone, E., Murray, T., Minster, A., Rohrbaugh, N., Bishop, M., Chen, E., Baker, J., Hou, Y., Horowitz, M., Ungar, L., & Tetlock, P. (2015). Identifying and cultivating superforecasters as a method of improving probabilistic predictions. *Perspectives on Psychological Science*, 10(3), 267–281.
- Murphy, A. H. (1973). A new vector partition of the probability score. *Journal of Applied Meteorology*, 12(4), 595–600.
- Murphy, A. H., & Winkler, R. L. (1987). A general framework for forecast verification. *Monthly Weather Review*, 115(7), 1330–1338.
- DeGroot, M. H., & Fienberg, S. E. (1983). The comparison and evaluation of forecasters. *Statistical Science*, 12–22.
- Dawid, A. P. (1986). Probability forecasting. In *Encyclopedia of Statistical Sciences* (Vol. 7). Wiley.
- Baron, J. (2000). *Thinking and Deciding* (3rd ed.). Cambridge University Press.
- Kahneman, D., & Tversky, A. (1985). Extensional versus intuitive reasoning: The conjunction fallacy in probability judgment. *Psychological Review*, 90(4), 293–315.

### Proper Scoring Rules

- Gneiting, T., & Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. *Journal of the American Statistical Association*, 102(477), 359–378.
- Gneiting, T., Balabdaoui, F., & Raftery, A. E. (2007). Probabilistic forecasts, calibration and sharpness. *Journal of the Royal Statistical Society: Series B*, 69(2), 243–268.

### Finance — Forecasting Limits and Overfitting

- Goyal, A., & Welch, I. (2008). A comprehensive look at the empirical performance of equity premium prediction. *Review of Financial Studies*, 21(4), 1455–1508.
- Bailey, D. H., Borwein, J., López de Prado, M., & Zhu, Q. J. (2014). Pseudo-mathematics and financial charlatanism: The effects of backtest overfitting on out-of-sample performance. *Notices of the American Mathematical Society*, 61(5), 458–471.
- Harvey, C. R., Liu, Y., & Zhu, H. (2016). … and the cross-section of expected returns. *Review of Financial Studies*, 29(1), 5–68.
- Gu, S., Kelly, B., & Xiu, D. (2020). Empirical asset pricing via machine learning. *Review of Financial Studies*, 33(5), 2223–2273.
- Spurious Predictability in Financial Machine Learning (2026). arXiv:2604.15531.
- Forecast Collapse of Transformer-Based Models under Squared Loss in Financial Time Series (2026). arXiv:2604.00064.

### Position Sizing

- Thorp, E. O. (2017). *A Man for All Markets.* Random House.
- Kelly, J. L. (1956). A new interpretation of information rate. *Bell System Technical Journal*, 35(4), 917–926.

### BlueLotus Internal

- BlueLotus Fund (2026). *Superforecasting and Its Application to Equity Market Trading.* Research Commission 001. https://sohweekian.github.io/bluelotus/superforecasting-thesis.html
- BlueLotus Fund (2026). *Superforecasting Report — 78 Tickers.* https://sohweekian.github.io/bluelotus/bluelotus-watchlist-superforecast.html
- BlueLotus Fund (2026). *Superforecasting, Brier Accountability, and EIPE — V3 PhD Thesis.* https://sohweekian.github.io/bluelotus/superforecasting-eipe-thesis-v3.html
- Soh, W. K. (2026). *BGTM-V1 PhD Thesis: Geopolitical Game Theory & Nash Equilibrium.* BlueLotus Research Series.
- BlueLotus V3 (2026). *Prospective Event Intelligence (PEI) — Extended Edition.*
- BlueLotus V3 (2026). `config/v3_doctrine_seed.json` — Doctrines 001–008.
- BlueLotus V3 (2026). `research/bluelotus_superforecast_engine.py` — Engine v1.0.
- BlueLotus V3 (2026). `data/brier/forecast_method_comparison_latest.json` — Resolution snapshot.
- BlueLotus V3 (2026). `data/cio/cio_prediction_brier_latest.json` — CIO ledger snapshot.

---

## Appendix A — Brier Score Quick Reference

| Stated P | Outcome | Brier |
|----------|---------|-------|
| 0.50 | FALSE | 0.25 |
| 0.50 | TRUE | 0.25 |
| 0.70 | TRUE | 0.09 |
| 0.70 | FALSE | 0.49 |
| 1.00 | TRUE | 0.00 |
| 1.00 | FALSE | 1.00 |

## Appendix B — CIO Gut Registration Command

```powershell
python scripts/register_cio_gut_prediction.py `
  --question "YOUR TESTABLE CLAIM" `
  --probability 0.60 `
  --gut "Your gut read" `
  --why-now "Why now" `
  --tickers ASTS,RKLB `
  --horizon-days 5
```

## Appendix C — EIPE Formula Card

\[
\boxed{
\Delta \hat{r}_{t,h} = \sum_{i} w_i \cdot P_i^{(\mathrm{cal})} \cdot E_{i \rightarrow t,h} \cdot \sigma_i
\qquad
\mathrm{BS} = (f - o)^2
}
\]

---

*End of Thesis — BlueLotus V3 Superforecasting & EIPE — 25 June 2026*
