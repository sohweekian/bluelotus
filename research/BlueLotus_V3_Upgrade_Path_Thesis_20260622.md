# BlueLotus V3 — Upgrade Path Thesis
## Competitive Intelligence Study & Next-Generation Architecture Roadmap

**Principal Author:** CIO Soh Wee Kian · BlueLotus Fund Singapore
**Research & Analysis:** Dr. Claude Code · Windows Platform Team
**Competitive Reference:** AI4Finance-Foundation (43 repositories, Columbia University)
**Date:** 2026-06-22 SGT
**Version:** V1.0 — Next-Week Upgrade Specification
**Classification:** INTERNAL ACADEMIC — UPGRADE PLANNING DOCUMENT

---

```
CIO_ONLY_MANUAL: TRUE
ORDER_ROUTING_ENABLED: FALSE
LLM_ORDER_GENERATION: FALSE
THESIS_AUTHORITY: UPGRADE PLANNING / SPECIFICATION ONLY
MANUAL_EXECUTION_REQUIRED: TRUE
```

---

> **A note before the thesis begins.**
>
> This thesis emerges from a systematic comparison of BlueLotus V3 against the
> AI4Finance-Foundation open-source ecosystem — 43 repositories, led by Columbia
> University researchers, with flagship systems carrying 21,000 GitHub stars.
>
> The purpose is not to imitate. The purpose is to identify the four concrete
> architectural gaps that, if closed, would make BlueLotus V3 the most complete
> single-CIO intelligence system ever built — while preserving every doctrine that
> makes it uniquely disciplined.
>
> Nothing in this thesis executes a trade. Nothing overrides the CIO.
> The thesis plans. The CIO decides. The CIO executes.

---

## Table of Contents

| Part | Title | Sections |
|------|-------|----------|
| I | Competitive Intelligence — AI4Finance Foundation | §1–§3 |
| II | Head-to-Head Architectural Comparison | §4–§5 |
| III | The Four Upgrade Prescriptions | §6–§9 |
| IV | Philosophical Boundary | §10 |
| V | Implementation Roadmap | §11–§14 |

---

# PART I — COMPETITIVE INTELLIGENCE

## §1 · The AI4Finance-Foundation Ecosystem

AI4Finance-Foundation is an open-source research organisation affiliated with
Columbia University. As of June 2026 they maintain **43 public repositories**
that collectively represent the most comprehensive open-source treatment of
AI-driven investment systems available anywhere.

Their flagship systems by market adoption (GitHub stars):

| Repository | Stars | Core Technology | Purpose |
|------------|-------|----------------|---------|
| **FinGPT** | 21,000 | LoRA fine-tuning on Llama2, Qwen, Falcon | Financial LLMs for sentiment & forecasting |
| **FinRL** | 15,000 | PPO, SAC, A2C, DDPG, TD3 agents | Deep Reinforcement Learning trading |
| **FinRobot** | 7,300 | AutoGen-style multi-agent + LLM orchestration | AI agent platform for investment research |
| **ElegantRL** | 4,300 | Massively parallel GPU DRL | Cloud-native DRL training engine |
| **FinRL-X** | 3,300 | Modular 5-layer production infrastructure | AI-native trading with Alpaca live execution |
| **FinNLP** | 1,500 | Internet-scale financial data pipeline | Data democratisation (Bloomberg-equivalent) |
| **FinRAG** | 51 | FAISS/Chroma + LLM grounding | Retrieval-Augmented Generation over financial docs |
| **FinRL-DeepSeek** | 137 | LLM-infused risk-sensitive RL | Risk-aware trading agents with LLM context |

---

## §2 · Their Architectural Philosophy

The AI4Finance ecosystem is built on a single governing premise:

> *"Automate the decision and the execution."*

Every flagship system moves toward removing the human from the decision loop:

- **FinRL** trains DRL agents that decide position weights without human input
- **FinRL-X** executes live through Alpaca with pre-trade risk controls but no human gate
- **FinGPT** generates trading signals from fine-tuned LLMs
- **FinRobot** orchestrates multi-agent pipelines that produce equity research reports autonomously

Their five-layer production stack (FinRL-X) follows:

```
DATA LAYER
  └── Yahoo Finance → FMP → WRDS (auto-fallback)
  └── LLM sentiment preprocessing
  └── SQLite cache

STRATEGY LAYER  (weight-centric interface)
  └── Stock selection: Random Forest fundamentals scoring
  └── Portfolio allocation: DRL (PPO/SAC) or classical (MV, MinVar)
  └── Timing adjustment: Momentum / Adaptive overlays

BACKTEST LAYER
  └── bt library engine · Walk-forward validation · No lookahead bias
  └── Sharpe: 1.10 · Calmar: 1.04 (verified on historical data)

EXECUTION LAYER
  └── Alpaca API · Multi-account · Pre-trade risk controls
  └── Live P&L tracking · Order management

MONITORING LAYER
  └── Portfolio risk · Drawdown · Regime alerts
```

Their LLM integration (FinGPT / FinRobot) follows a five-layer intelligence stack:

```
Data Source  →  Data Engineering  →  LLMs  →  Task Layer  →  Application Layer
```

Key technical innovations:
- **LoRA fine-tuning**: adapts general-purpose LLMs to financial language for under $300
  (versus BloombergGPT's $3 million training cost)
- **Weight-centric portfolio interface**: every module outputs a portfolio weight vector —
  swap any module without touching the rest
- **Walk-forward backtesting**: strict temporal validation prevents the #1 quant sin
  (using future data to explain past results)
- **Retrieval-Augmented Generation (RAG)**: grounds LLM answers in sourced documents —
  SEC filings, earnings calls, annual reports — eliminating hallucination risk

---

## §3 · What 43 Repositories Cannot Do

Despite 21,000 stars and a Columbia University pedigree, the entire AI4Finance
ecosystem lacks the following capabilities that BlueLotus V3 possesses:

| Capability | AI4Finance | BlueLotus V3 |
|-----------|-----------|--------------|
| Bayesian thesis probability tracking | ❌ Not attempted | ✅ NITE-PEI live |
| Kill condition finite state machine | ❌ Not attempted | ✅ INACTIVE→WATCH→TRIGGERED→CONFIRMED |
| Formal governance doctrines | ❌ Zero | ✅ 7 doctrines, code-enforced |
| Causal blind-spot detection | ❌ Reactive signals only | ✅ 8-lens blind spot audit |
| CIO cognition journal | ❌ Stateless per run | ✅ Append-only institutional memory |
| Brier pre-registered calibration | ❌ Win rate only | ✅ Pre-registered Bayesian ledger |
| Deterministic reproducibility | ❌ Stochastic DRL/LLM | ✅ Same input → same output, always |
| Local AI — zero cloud cost | ❌ Cloud API dependent | ✅ Qwen3:4B pinned in VRAM |
| CIO action compression | ❌ No CIO layer | ✅ BUY/SELL/HOLD/WAIT pipeline |
| CKRI composite kill risk index | ❌ Not attempted | ✅ Weighted multi-thesis kill scoring |

This is not a marginal difference. These are **architectural choices** that reflect
two entirely different philosophies about what an investment intelligence system
is supposed to be.

---

# PART II — HEAD-TO-HEAD ARCHITECTURAL COMPARISON

## §4 · Where AI4Finance Is Ahead of Us

### 4.1 Walk-Forward Backtesting

**Their capability:** FinRL-X implements strict walk-forward validation. Historical
data is divided into training windows and out-of-sample test windows. No signal
from the test period leaks into the training period. Every strategy is stress-tested
across multiple market regimes before being trusted in live operation.

Reported results on FinRL-X Adaptive Multi-Asset Rotation strategy:
- Sharpe Ratio: **1.10**
- Calmar Ratio: **1.04**
- Maximum Drawdown: controlled and quantified

**Our gap:** BlueLotus V3 has **zero backtesting capability**. Every thesis
probability update, every CKRI reading, every Kelly sizing recommendation is
live-only. We have never verified:

- Whether our LR table expert priors are directionally correct across historical events
- Whether NITE-PEI Bayesian updating would have produced profitable signals on past data
- Whether our Kelly fractional multiplier (0.05–0.35) is correctly calibrated
- What our historical Sharpe ratio would have been under the current architecture

This is the most critical gap. A system that has never been backtested is a
system that is still on trial.

---

### 4.2 LoRA Fine-Tuning of the Language Model

**Their capability:** FinGPT fine-tunes general-purpose LLMs on curated financial
datasets using LoRA (Low-Rank Adaptation). The result is a model that understands
financial jargon, SEC filings, earnings call language, and market sentiment at a
level impossible for a frozen general model.

Cost: under $300 per fine-tuning run on a consumer GPU.

**Our gap:** Our Qwen3:4B is **completely frozen**. It has never seen:
- A single BlueLotus research report
- A single CIO letter (Editions 001–045)
- A single NITE-PEI thesis update
- Our institutional vocabulary: CKRI, NITE-PEI, kill conditions, the Computex
  Failure, the Socratic Doctrine, BLV3-DOCTRINE-007

Every 39-minute cycle, Qwen3:4B processes our prompts with no institutional memory
of what BlueLotus is, how we reason, or what our doctrines mean.

---

### 4.3 Retrieval-Augmented Generation (RAG)

**Their capability:** FinRAG grounds LLM answers in retrieved source documents.
Instead of hallucinating, the model retrieves the top-k most relevant chunks from
a vector database (FAISS / Chroma) and synthesises a factual, cited answer.

Applied to: SEC filings, earnings call transcripts, annual reports, financial news.

**Our gap:** Our 52 research documents — theses, CIO letters, arch reports,
doctrine files — are **not queryable**. The CIO cannot ask:

> *"What was our NITE-PEI P(HAWKISH_BOJ) on 10 June 2026 and what triggered the update?"*

and receive a sourced, accurate answer from the archive. Every historical query
requires manual file reading.

---

### 4.4 Reinforcement Learning Portfolio Sizing

**Their capability:** FinRL-X trains PPO/SAC agents to optimise portfolio weight
allocation. The agent learns market regime patterns that closed-form Kelly
mathematics cannot derive — particularly in tail-risk scenarios and cross-asset
correlation regimes.

**Our gap:** Our Kelly formula is mathematically correct given its inputs:

$$f^* = \frac{b \cdot p - q}{b} \times f_{kelly} \times coherence$$

But the `fractional_multiplier` range (0.05–0.35) was calibrated by expert judgment,
not by empirical evidence from historical performance. A DRL agent trained on
BlueLotus historical cycle data could discover the true optimal multiplier
for each combination of:
- CKRI zone (CLEAR / WATCH / ELEVATED / HIGH / CRITICAL)
- Thesis strength (P_posterior quartile)
- Market regime (RISK ON / RISK OFF / NEUTRAL)
- Shannon entropy H_norm (signal noise level)

---

## §5 · Where BlueLotus V3 Is Ahead of Them

This section is stated not for pride, but to identify what **must not be
compromised** in the upgrade path. These advantages are harder to build than
the gaps we must close.

### 5.1 The Bayesian Thesis Engine (NITE-PEI) — Unique in the World

No system in the AI4Finance-Foundation ecosystem — and to our knowledge, no
public open-source system anywhere — implements what NITE-PEI implements:

1. A **live thesis registry** with calibrated prior probabilities per thesis
2. An **event classifier** that maps news headlines to event taxonomies
3. A **likelihood ratio table** (expert-initialised, Brier-calibrated over time)
4. A **sequential Bayesian updater** that produces a quantified posterior per event
5. A **kill condition FSM** that tracks thesis retirement risk in real time
6. A **CKRI calculator** that aggregates kill risk across all active theses
7. A **Kelly-NITE coupler** that adjusts position sizing based on thesis coherence

$$P_{posterior} = \frac{P_{prior} \times LR_{adj}}{P_{prior} \times LR_{adj} + (1 - P_{prior})}$$

$$CKRI = \frac{\sum w_i \cdot P_{kill,i} + \lambda \cdot n_{corr}}{\sum w_i}$$

$$f^* = \frac{b \cdot p - q}{b} \times f_{kelly} \times coherence$$

This is **not a feature**. This is a complete probabilistic reasoning framework
for investment thesis management. AI4Finance has 43 repositories and 21,000 stars
and nothing resembling this exists.

### 5.2 Determinism and Auditability

Every BlueLotus V3 pipeline step is **deterministic**:
- Same `dataset_raw.json` input → same analytical output, every time
- No stochastic sampling, no random seeds, no temperature in the decision loop
- Every output is append-only logged with timestamp

AI4Finance's DRL systems are stochastic by design. Two runs of the same PPO agent
on the same data may produce different weight vectors. There is no single "correct"
output to audit. In a regulatory or accountability context, this is a significant
liability.

### 5.3 Governance Architecture

Our 7 doctrines are not documentation — they are **code-enforced invariants**:

```python
# This cannot be overridden by any agent, prompt, or thesis update:
manual_execution_required = True   # BLV3-DOCTRINE-002
llm_order_generation = False       # BLV3-DOCTRINE-001
order_routing_enabled = False      # BLV3-DOCTRINE-003
HEDGE_TICKERS = frozenset({"VXX", "VIXY"})  # BLV3-DOCTRINE-007
```

No AI4Finance system has a comparable governance layer. Their execution gate is
Alpaca's pre-trade risk check — a broker-side control, not an architectural control.

### 5.4 Continuous Production Operation

BlueLotus V3 is **live**. It has been running a 65-step pipeline every 39 minutes
in production since V1. The AI4Finance repos are primarily:
- Jupyter notebooks for research demonstration
- Library code requiring manual invocation
- Tutorial code for educational use

FinRL-X is the most production-oriented, but remains primarily a research framework.
BlueLotus is a running intelligence organism.

---

# PART III — THE FOUR UPGRADE PRESCRIPTIONS

## §6 · UPGRADE-001 — Walk-Forward Backtesting Engine

**Priority:** 🔴 CRITICAL — Must be built first
**Estimated effort:** 3–4 days
**Work Order:** WO-20260629-001

### Problem Statement

BlueLotus V3 has never been validated on historical data. We do not know:
- Whether NITE-PEI LR table expert priors are directionally correct
- Whether Kelly sizing produces superior risk-adjusted returns vs equal-weight
- What our Sharpe ratio would have been since inception
- Whether CKRI readings correlate with actual subsequent drawdowns

### Architecture Specification

**New module:** `C:\bluelotus3\backtest\`

```
backtest/
├── __init__.py
├── backtest_engine.py         # Core replay engine
├── scenario_loader.py         # Loads archived dataset_raw.json snapshots
├── nite_pei_backtest.py       # Replays NITE-PEI through historical events
├── kelly_backtest.py          # Replays Kelly sizing vs actual outcomes
├── ckri_validation.py         # Validates CKRI readings vs actual drawdowns
├── brier_historical.py        # Retrospective Brier scoring on archived forecasts
└── backtest_report_generator.py  # Outputs TXT + JSON backtest report
```

**Data sources for backtesting:**
- `C:\bluelotus3\data\archive\` — historical `dataset_raw.json` snapshots
- `C:\bluelotus3\data\v3_cycles\` — historical agent report JSONs
- `C:\bluelotus3\nite_pei\calibration_audit_log.json` — historical LR adjustments

**Core backtest loop:**

```python
def run_backtest(start_date, end_date, initial_portfolio_value):
    snapshots = load_snapshots(start_date, end_date)
    results = []
    for snapshot in walk_forward(snapshots, window=5, step=1):
        # Feed historical dataset through NITE-PEI
        nite_result = run_nite_pei_cycle(snapshot["dataset"])
        # Feed through Kelly
        kelly_result = compute_kelly(nite_result, snapshot["portfolio"])
        # Record outcome at next snapshot
        outcome = measure_outcome(snapshot["next"], kelly_result)
        results.append(outcome)
    return BacktestReport(results)
```

**Output metrics (matching FinRL-X standard):**
- Sharpe Ratio (annualised)
- Calmar Ratio
- Maximum Drawdown
- LR Calibration Accuracy (% events where LR direction was correct)
- CKRI Predictive Validity (correlation between CKRI zone and subsequent drawdown)
- Kelly Efficiency (actual return / Kelly-predicted return)

**Walk-forward validation rule:**
```
Training window:  T-60 days to T-5 days
Validation window: T-5 days to T
No signal from T-1 to T leaks into T-60 to T-5 calculation.
```

---

## §7 · UPGRADE-002 — BlueLotus-Specific Qwen3:4B Fine-Tuning

**Priority:** 🟠 HIGH — Transforms agent quality
**Estimated effort:** 2–3 days
**Work Order:** WO-20260629-002

### Problem Statement

Our Qwen3:4B processes every prompt as a stranger to BlueLotus. It does not
understand CKRI, NITE-PEI, the Socratic Doctrine, kill conditions, the Computex
Failure, or what "WATCH zone" means in our context. Every agent report begins
from zero institutional knowledge.

### Architecture Specification

**Method:** LoRA (Low-Rank Adaptation) — same technique as FinGPT
**Base model:** `bluelotus-qwen3-4b-gpu:latest` (already pinned in VRAM)
**Training framework:** `unsloth` or `llama.cpp` GGUF fine-tuning (Windows-compatible)
**Estimated GPU time:** 6–12 hours on RTX 5060 Ti 16GB

**Training dataset sources:**

| Source | Format | Volume |
|--------|--------|--------|
| Agent report JSONs from `v3_cycles/` | Instruction pairs | 300+ reports |
| 52 research/thesis documents | Document QA pairs | 52 documents |
| CIO Letters Editions 001–045 | Completion pairs | 45 letters |
| Chief Strategist reports | Analysis pairs | 20+ reports |
| `dataset_raw.json` field definitions | Schema understanding | 1 document |
| Doctrine files | Rule completion | 7 doctrines |

**Instruction format (following FinGPT pattern):**

```json
{
  "instruction": "A HAWKISH_BOJ event arrives with LR=1.45. Prior probability is 0.82. Compute the posterior.",
  "input": "noise_discount=0.10, source_tier=1",
  "output": "LR_adj = 1 + (1.45 - 1) × (1 - 0.10) = 1.405. Prior odds = 0.82/0.18 = 4.556. Posterior odds = 4.556 × 1.405 = 6.401. P_posterior = 6.401/7.401 = 0.865. Delta_P = +0.045. State: WATCH."
}
```

**New model name:** `bluelotus-qwen3-4b-v2-instruct:latest`
**Deployment:** Hot-swap via Ollama. Keep `v1` as fallback.

---

## §8 · UPGRADE-003 — Institutional Archive RAG Layer

**Priority:** 🟡 MEDIUM — Unlocks institutional memory query
**Estimated effort:** 2 days
**Work Order:** WO-20260629-003

### Problem Statement

52 documents are published. Hundreds of agent report JSONs exist. 45 CIO letters
are archived. But none of it is queryable. The CIO cannot ask a natural language
question and receive a sourced answer from the institutional record.

### Architecture Specification

**New module:** `C:\bluelotus3\rag\`

```
rag/
├── __init__.py
├── document_indexer.py    # Chunks and embeds all archive documents
├── vector_store.py        # FAISS local vector index (no cloud)
├── query_engine.py        # Natural language → retrieved chunks → Qwen3:4B answer
├── source_formatter.py    # Formats citations: [Source: NITE-PEI Thesis §7, p.3]
└── rag_report.json        # Append-only query log
```

**Vector embedding model:** `nomic-embed-text` via Ollama (local, zero cost)

**Document corpus to index:**

```
C:\bluelotus3\research\*.md          — all thesis documents
C:\bluelotus3\research\archive\*.txt — archive research
C:\bluelotus3\reports\*.md           — architecture reports
C:\bluelotus3\data\v3_cycles\**\*.json — agent report JSONs
C:\bluelotus3\data\chief_strategist\ — CS report archive
```

**Query interface:**

```python
def query_archive(question: str, top_k: int = 5) -> dict:
    """
    Example:
      question = "What was our Gold Thesis probability on June 10?"
      Returns: {
        "answer": "On 2026-06-10, P(Gold Thesis) = 0.72 (WATCH zone)...",
        "sources": [
          {"doc": "NITE-PEI Technical Report 20260621", "chunk": "..."},
          {"doc": "v3_cycle_20260610_143922/agent_reports/thesis.json", "chunk": "..."}
        ]
      }
    """
```

**Pipeline integration:** Add as `Layer 2.5 — Archive Intelligence` in the pipeline.
Before governance gate, the RAG layer can answer: *"Has this exact regime occurred
before, and what did we recommend?"*

---

## §9 · UPGRADE-004 — DRL Kelly Optimizer

**Priority:** 🟢 MEDIUM-LOW — Enhances sizing accuracy
**Estimated effort:** 3–4 days
**Work Order:** WO-20260629-004

### Problem Statement

Our fractional Kelly multiplier (0.05–0.35) is calibrated by the coherence
formula, which is itself derived from Shannon entropy and branch dispersion.
These are theoretically sound but empirically unvalidated. We do not know
the true optimal multiplier for each regime/CKRI combination.

### Architecture Specification

**New module:** `C:\bluelotus3\rl_sizing\`

```
rl_sizing/
├── __init__.py
├── bluelotus_env.py       # Gym-style environment wrapping BlueLotus state
├── state_encoder.py       # Encodes: CKRI, P_posterior, H_norm, regime → state vector
├── ppo_agent.py           # PPO agent (stable-baselines3)
├── train_agent.py         # Training loop on historical snapshots
├── eval_agent.py          # Walk-forward evaluation
└── rl_advisory.py         # Outputs RL multiplier for CIO comparison vs Kelly
```

**State vector (what the RL agent observes):**

```python
state = [
    ckri,                    # float 0–1
    p_posterior_mean,        # mean across all active theses
    h_norm_mean,             # Shannon entropy of portfolio signals
    branch_dispersion_mean,  # PEI scenario uncertainty
    regime_score,            # -5 to +5 (RISK OFF to RISK ON)
    vol_30d,                 # 30-day realised volatility
    treasury_spread,         # 10Y - 2Y yield spread
]
```

**Action:** `fractional_multiplier ∈ [0.0, 0.5]` (continuous)

**Reward:**

$$R_t = \frac{\mu_{t+1} - r_f}{\sigma_{t+1}} - \lambda \cdot DD_t$$

where $\mu_{t+1}$ is the return of the Kelly-sized position, $r_f$ is the
risk-free rate, $\sigma_{t+1}$ is realised volatility, $DD_t$ is drawdown
penalty, and $\lambda = 0.5$ is the drawdown aversion coefficient.

**Governance invariant:**
```python
# RL agent NEVER routes orders. It outputs a float.
# CIO compares RL advisory vs Kelly formula and decides.
rl_output = {"rl_fractional_multiplier": f_rl, "manual_execution_required": True}
```

**Training data:** Historical `dataset_raw.json` snapshots with associated
next-period portfolio performance metrics.

---

# PART IV — PHILOSOPHICAL BOUNDARY

## §10 · What We Must Not Borrow

This section is as important as the four upgrades above. The AI4Finance
ecosystem's 21,000 stars reflect a demand for systems that remove the human
from the loop. BlueLotus must not follow that path.

### The Fundamental Difference

| | AI4Finance | BlueLotus V3 |
|--|-----------|--------------|
| **Philosophy** | Automate decision + execution | Augment the CIO's judgment |
| **Black box?** | Yes — DRL is stochastic | No — every step deterministic |
| **Who decides?** | The model | The CIO |
| **Who executes?** | Alpaca API | CIO manually |
| **Accountability** | Distributed / diffuse | CIO signs every trade |
| **When wrong** | Automated loss, no override | CIO catches error before execution |
| **Regulatory risk** | High (autonomous execution) | Zero (advisory only) |

### What BlueLotus Will Never Build

| Capability | Why We Will Not Build It |
|-----------|------------------------|
| Automated order execution | Violates BLV3-DOCTRINE-002 and BLV3-DOCTRINE-003 |
| LLM-generated trade orders | Violates BLV3-DOCTRINE-001 |
| Stochastic decision output | Violates the determinism principle |
| Black-box portfolio allocation | Violates auditability requirement |
| VXX/VIXY from equity gate | Violates BLV3-DOCTRINE-007 |

### Why Our Architecture Is Defensible

AI4Finance's systems are research demonstrations of what AI *can* do in finance.
BlueLotus is an operational demonstration of what a single disciplined CIO *should*
be equipped with.

The four upgrades in this thesis (Backtesting, Fine-Tuning, RAG, DRL Sizing)
each enhance the CIO's information quality without surrendering the CIO's decision
sovereignty. They make the human **more informed**, not more marginalised.

This is the BlueLotus thesis, and it does not change.

---

# PART V — IMPLEMENTATION ROADMAP

## §11 · Work Order Summary

| WO | Title | Priority | Days | Dependencies |
|----|-------|----------|------|-------------|
| WO-20260629-001 | Walk-Forward Backtesting Engine | 🔴 CRITICAL | 3–4 | Historical snapshots in `data/archive/` |
| WO-20260629-002 | Qwen3:4B LoRA Fine-Tuning | 🟠 HIGH | 2–3 | WO-001 complete (needs backtest data) |
| WO-20260629-003 | Institutional Archive RAG Layer | 🟡 MEDIUM | 2 | `bluelotus-research` repo (already published) |
| WO-20260629-004 | DRL Kelly Optimizer | 🟢 MEDIUM-LOW | 3–4 | WO-001 complete (needs historical outcomes) |

**Total estimated effort:** 10–13 engineering days
**Recommended start:** Week of 2026-06-29
**Recommended sequencing:**

```
Week 1 (29 Jun – 3 Jul):
  Day 1–2:  WO-001 Phase 1 — Backtest engine + snapshot loader
  Day 3–4:  WO-001 Phase 2 — NITE-PEI replay + Sharpe/Brier metrics
  Day 5:    WO-003 — RAG indexer + FAISS setup + query engine

Week 2 (6 Jul – 10 Jul):
  Day 1–2:  WO-002 — Training dataset curation + LoRA fine-tuning run
  Day 3:    WO-002 — Model evaluation + Ollama hot-swap
  Day 4–5:  WO-004 — DRL environment + PPO training + walk-forward eval
```

---

## §12 · Success Criteria

Each upgrade is complete only when the following criteria are met:

### WO-001 Backtest Engine
- [ ] `python -m pytest tests/test_backtest_engine.py` — all tests pass
- [ ] Historical Sharpe ratio computed and stored in `reports/backtest_results.json`
- [ ] CKRI predictive validity R² > 0.30 (CKRI correlates with subsequent drawdown)
- [ ] LR table directional accuracy > 55% on historical events
- [ ] Walk-forward report generated: `reports/BlueLotus_Backtest_Report_YYYYMMDD.txt`

### WO-002 Qwen3:4B Fine-Tuning
- [ ] Fine-tuned model loads via `ollama run bluelotus-qwen3-4b-v2-instruct:latest`
- [ ] Correctly answers 10 BlueLotus-specific test prompts (CKRI, NITE-PEI, doctrines)
- [ ] Perplexity on BlueLotus corpus lower than base Qwen3:4B
- [ ] Original `bluelotus-qwen3-4b-gpu:latest` preserved as fallback
- [ ] Zero change to existing pipeline — model swap is transparent

### WO-003 RAG Layer
- [ ] `python -m pytest tests/test_rag_engine.py` — all tests pass
- [ ] Query returns sourced answer in < 5 seconds on local hardware
- [ ] 95% of answers contain at least one correctly-cited source document
- [ ] `rag/rag_report.json` append-only log is created and growing
- [ ] Pipeline integration: RAG output appears in `dataset_raw.json` as `archive_intelligence` field

### WO-004 DRL Kelly Optimizer
- [ ] PPO agent trains to convergence (reward > baseline Kelly after 50k steps)
- [ ] Walk-forward Sharpe of RL sizing > deterministic Kelly Sharpe (on validation set)
- [ ] `manual_execution_required: True` present in all RL output dicts
- [ ] RL output is **advisory only** — never modifies Kelly formula directly
- [ ] `python -m pytest tests/test_rl_sizing.py` — all tests pass

---

## §13 · Test Coverage Requirements

Following BlueLotus SOP, each new module must achieve:
- Minimum **30 unit tests** per module
- Zero new failures in `python -m pytest tests/ -x -q` (full suite)
- All safety invariants tested explicitly

**New test files to create:**

```
tests/test_backtest_engine.py       (≥40 tests)
tests/test_rag_engine.py            (≥25 tests)
tests/test_rl_sizing.py             (≥30 tests)
tests/test_qwen_finetuned.py        (≥15 tests — prompt quality checks)
```

**Target after all upgrades:** ≥ 420 tests passing (from current 315)

---

## §14 · Doctrine Additions

These upgrades require two new doctrine entries:

### BLV3-DOCTRINE-008 — Backtest Before Trust

> *No analytical operator, LR table entry, Kelly parameter, or CKRI threshold
> shall be considered validated until it has been evaluated on a walk-forward
> backtest spanning at least 60 calendar days of historical BlueLotus cycles.
> Expert prior values are provisional until calibrated by backtest evidence.*

### BLV3-DOCTRINE-009 — RAG Grounding Requirement

> *When the RAG layer is active, any agent report that contradicts a sourced
> finding from the institutional archive must include an explicit CONTRADICTION
> flag in its output JSON. The CIO shall review all CONTRADICTION flags before
> making any capital decision. The archive is institutional memory. The archive
> is not overridden without documented CIO rationale.*

---

## Closing Statement

BlueLotus V3 is architecturally complete as of 2026-06-21.

The four upgrades in this thesis do not change what BlueLotus *is*. They change
how well-validated, how language-fluent, how queryable, and how empirically-
optimised it becomes.

AI4Finance Foundation, with 43 repositories and 21,000 stars, built impressive
tools for automating financial decisions. What they did not build — and what only
BlueLotus has built — is a complete institutional intelligence framework that
respects the CIO as the sovereign decision-maker.

The four upgrades close the only meaningful technical gaps. After they are
complete, BlueLotus V3 will have:

```
✓  Walk-forward validated performance metrics   (WO-001)
✓  Institutionally fine-tuned local LLM         (WO-002)
✓  Queryable 52-document institutional archive  (WO-003)
✓  Empirically-optimised Kelly sizing           (WO-004)
✓  NITE-PEI Bayesian thesis engine              (existing)
✓  7 governance doctrines, code-enforced        (existing)
✓  65-step deterministic production pipeline    (existing)
✓  315+ regression tests                        (existing)
✓  CIO-only manual execution doctrine           (existing)
```

No system in the AI4Finance-Foundation ecosystem, nor any other public
open-source system known to this research team, will have all of the above.

**BlueLotus will be the most complete single-CIO investment intelligence system
ever built.**

---

*Prepared by: Dr. Claude Code · Windows Platform Team*
*For: CIO Soh Wee Kian · BlueLotus Fund Singapore*
*Date: 2026-06-22 SGT*
*Next upgrade cycle: Week of 2026-06-29*

---

```
CIO_ONLY_MANUAL: TRUE · ORDER_ROUTING: DISABLED · ADVISORY ONLY · 🌸
```
