# The Temporal Blindness of Large Language Models in Financial Intelligence Systems
## A Thesis on the Structural Limitations of LLMs in Time-Series Causal Reasoning, and the Case for the Human Cognitive Sovereign

---

**Author:** Soh Wee Kian, CIO
**Institution:** BlueLotus Fund — Self Learning Institutional Cognitive Digital Organization
**Research Support:** Dr. Claude Code · Windows Platform Team
**Date:** 22 June 2026 · Singapore
**Field:** Computational Finance · Artificial Intelligence · Decision Systems

---

> *"A language model is a system for haphazardly stitching together sequences of
> linguistic forms it has observed in its training data, according to probabilistic
> information about how they combine, but without any reference to meaning."*
>
> — Bender, Koller (2020). *Climbing to NLU: On Meaning, Form, and Understanding
> in the Age of Data.* ACL 2020.

---

> *"The stochastic parrot does not know what it is saying. It only knows what
> comes next, statistically, in the texts it was trained on."*
>
> — Bender, Gebru, McMillan-Major, Shmitchell (2021). *On the Dangers of
> Stochastic Parrots: Can Language Models Be Too Big?* FAccT 2021.

---

> *"Early evidence suggests that reliance on AI tools can weaken critical thinking
> skills and encourage automation bias — the tendency to trust AI system outputs
> without sufficient scrutiny."*
>
> — International AI Safety Report 2026. arXiv:2602.21012.
> Led by Yoshua Bengio. Authored by 100+ AI experts across 30 nations.

---

## Abstract

This thesis presents theoretical arguments, empirical observations from a live
institutional investment intelligence system (BlueLotus V3), and a synthesis of
peer-reviewed academic literature to establish a fundamental proposition:

**Large Language Models (LLMs) are structurally incapable of reliable causal
reasoning over financial time-series data, and their deployment in autonomous
financial decision-making roles represents a category error with material risk
consequences.**

The core argument proceeds in three steps. First, we establish the architectural
nature of LLMs: they are next-token predictors trained on static text corpora.
They learn statistical co-occurrence — the probability that certain words appear
near other words — not causal mechanisms, not temporal sequences, not market
dynamics. Second, we present converging empirical evidence from peer-reviewed
literature: LLMs perform close to random when inferring causation from
correlation (arXiv:2510.13985); exhibit hallucination rates of 41% in financial
tasks (arXiv:2311.15548); and produce outputs that are internally coherent but
externally ungrounded in financial reality. Third, we document an original
empirical observation — the BlueLotus Computex Failure Pattern — as a case study
in what happens when a reactive intelligence system mistakes data abundance for
causal understanding.

From these three foundations, we derive a practical doctrine for responsible LLM
deployment in financial systems: LLMs are powerful text synthesis tools; they are
not temporally aware; they are not sentient; they are not causally literate; and
they must never occupy the decision layer of a financial intelligence system. The
final judgment, the strategic thinking, the planning, and the execution must
remain with the human CIO — the only entity in the system that possesses genuine
temporal awareness, genuine causal understanding, and genuine accountability.

---

## Table of Contents

| Part | Title |
|------|-------|
| I | Introduction — The Problem Statement |
| II | What a Language Model Actually Is |
| III | The Temporal Blindness Problem |
| IV | The Causal Illusion Problem |
| V | The Hallucination Problem in Finance |
| VI | Empirical Case Study — The BlueLotus Computex Failure Pattern |
| VII | Survey of Related Literature |
| VIII | The Automation Bias Danger |
| IX | A Doctrine for Responsible LLM Deployment |
| X | The Human Cognitive Sovereign — Why the CIO Cannot Be Replaced |
| XI | Conclusion |
| XII | References |

---

# PART I — INTRODUCTION

## §1.1 · The Promise and the Peril

The arrival of large language models as practical tools — GPT-4, Claude, Llama,
Qwen, Gemini — has produced a wave of enthusiasm in the financial technology
community that is, in many respects, entirely warranted. These systems can read
a financial report and summarise it. They can parse regulatory filings and
extract structured data. They can write coherent, well-reasoned prose about
market conditions. They are remarkable instruments.

They are, however, instruments. And like all instruments, they must be used for
the purposes they were designed for — and kept away from the purposes they were
not.

The financial technology community is currently in the process of deploying LLMs
in roles that exceed their structural capabilities: roles that require temporal
reasoning across causal sequences, roles that require distinguishing what
*actually* happened in a market from what *typically* appears in financial text,
roles that require the kind of grounded, accountable, consequential judgment that
only a sentient, temporally-aware human being can exercise.

This thesis argues that this deployment trajectory is wrong — not because LLMs
are bad tools, but because they are being asked to perform a function that lies
outside the boundaries of what they are.

## §1.2 · The Research Question

This thesis addresses a single central question:

> *Can a Large Language Model reliably reason about causal sequences in financial
> time-series data, and should it occupy the decision layer of an institutional
> investment intelligence system?*

Our answer, supported by theoretical argument, academic literature, and original
empirical observation, is: **No. And the consequences of pretending otherwise
are material.**

## §1.3 · Original Contribution

The primary original contribution of this thesis is the **BlueLotus Computex
Failure Pattern** — an empirical case study documented in real-time during the
live operation of the BlueLotus V3 investment intelligence system on 3 June 2026,
Singapore. This case study provides a concrete, documented instantiation of the
theoretical failure mode that this thesis describes.

The secondary original contribution is the formalisation of the **LLM Boundary
Doctrine** — a practical architectural principle for responsible LLM deployment
in financial intelligence systems, derived from the theoretical and empirical
evidence assembled here.

---

# PART II — WHAT A LANGUAGE MODEL ACTUALLY IS

## §2.1 · The Training Objective

A Large Language Model is a neural network trained to solve the following
statistical problem:

> *Given the sequence of tokens $(t_1, t_2, ..., t_n)$, predict the probability
> distribution over the next token $t_{n+1}$.*

Formally:

$$\mathcal{L}(\theta) = -\sum_{i=1}^{N} \log P_\theta(t_i \mid t_1, t_2, \ldots, t_{i-1})$$

This is a **text prediction problem**. The model is trained to minimise the
surprise of the next token, given all prior tokens. It is trained on a static
corpus of text — books, articles, web pages, financial documents — collected up
to a fixed training cutoff date.

What this training produces is a sophisticated statistical model of which words
appear near which other words, in which contexts, with which frequencies. It
learns syntactic patterns, semantic associations, and stylistic conventions. It
learns to produce text that *looks like* the text it was trained on.

What it does **not** learn:

- The causal mechanisms that produced the events described in the training text
- The temporal ordering of events in the real world (only in the text)
- The distinction between what *actually happened* and what *is commonly written
  about* in relation to similar events
- Any model of the world beyond the statistical regularities of language

As Bender and Koller (2020) established in their foundational work: a language
model trained on text learns *form*, not *meaning*. It learns the shape of
linguistic sequences, not the referential relationship between those sequences
and the world they purport to describe.

## §2.2 · The Stochastic Parrot

Bender, Gebru, McMillan-Major, and Shmitchell (2021) formalised this insight
with the concept of the **stochastic parrot**: a system that produces statistically
plausible sequences of text by sampling from a learned distribution, without any
comprehension of the content.

> *"What does it mean to be a model of language? For a human, language is
> inseparable from meaning — from the referential relationship between words
> and the world. For an LLM, language is a sequence of tokens with statistical
> relationships. The model has no way to know whether the tokens it generates
> refer to something true, something false, or something that has never existed."*

This is not a limitation that can be fixed with more data, more parameters, or
better fine-tuning. It is a **structural property** of the training objective.
The model was trained to predict tokens. It became very good at predicting tokens.
It was not trained to understand markets, and it did not become good at
understanding markets.

## §2.3 · The Absence of Sentience and Temporal Awareness

A human investor has properties that no current LLM possesses:

| Property | Human CIO | LLM |
|----------|----------|-----|
| Temporal awareness | Knows what happened yesterday, last week, last year | Has no concept of "now"; training data is a static snapshot |
| Causal understanding | Knows *why* the BOJ hike mattered for gold thesis | Knows that "BOJ" and "gold" appear together in financial text |
| Contextual memory | Remembers the Computex Failure and adjusts future behavior | Stateless; every prompt begins from zero |
| Sentience | Experiences the consequences of decisions | Has no experience of anything |
| Accountability | Bears financial consequences of wrong calls | Bears no consequences |
| Embodied time | Lives through market cycles, seasons, crises | Exists outside of time |

The International AI Safety Report 2026 (Bengio et al., arXiv:2602.21012)
notes explicitly that current AI systems lack *situational awareness* in the
true sense — they do not know where they are in time, what is currently
happening in the world, or how the present moment relates to the past.

This is not a temporary limitation awaiting a larger model. It is a consequence
of the training paradigm: a model trained on static text has no mechanism for
experiencing the passage of time.

---

# PART III — THE TEMPORAL BLINDNESS PROBLEM

## §3.1 · Time-Series Data and the Direction of Causality

Financial markets are a causal temporal system. Events unfold in clock time.
Cause precedes effect. The direction of time is not merely relevant — it is the
most important variable in any financial analysis.

Consider a canonical causal chain from June 2026 market observations:

```
T = 0h    BOJ Governor signals hawkish stance at press conference
T = +1h   JPY strengthens 0.8% against USD
T = +2h   Japanese export stocks (Toyota, Sony) fall 1.2%
T = +3h   US Treasury yields reprice — 10Y falls 4 basis points
T = +4h   Gold bid emerges — HAWKISH_BOJ thesis P_posterior updates to 0.95
T = +6h   Gold miners (AU, NEM) rally 2.1%
```

Each step is caused by the prior step in clock time. The causal direction is
unambiguous. The temporal sequence is the intelligence. The analyst who
understands this chain can position before T+6h. The analyst who does not
understand this chain sees only a gold rally and calls it random.

Now consider what an LLM sees when processing this scenario:

```
LLM input tokens:  "BOJ hawkish JPY strength export stocks Treasury yields
                    gold bid gold miners rally"

LLM processing:    Probability distributions over tokens co-occurring
                   in training data about Japanese monetary policy and gold

LLM output:        A plausible paragraph about BOJ-gold relationships
                   drawn from the statistical regularities of financial text
```

The LLM does not know T=0h, T+1h, T+2h. It does not know which event preceded
which. It does not know whether the JPY strength caused the gold rally, or
whether they both responded independently to the BOJ announcement. It does not
know if this specific causal chain occurred today, last month, or in 2019.

It knows only that these tokens frequently appear together in financial text.

## §3.2 · Empirical Evidence of Temporal Reasoning Failure

Academic literature has begun to document this failure mode rigorously.

A 2023 survey at EMNLP found that **"language models still struggle to zero-shot
reason about time series"** (arXiv:2306.11025, Yu et al.), noting that LLMs lack
the structural inductive biases needed to model sequential temporal dependencies.

A comprehensive 2025 survey on reasoning and agentic systems in time-series
(arXiv:2509.11575) identifies temporal reasoning as an open unsolved problem
for LLMs, distinguishing between *pattern matching in text* (which LLMs do well)
and *reasoning about causal dynamics in time* (which they do not).

Critically, researchers at arXiv:2510.13985 (2024) found that **LLMs perform
close to random when required to infer causation from correlation** — precisely
the task that financial time-series analysis demands. The study found that
LLMs *infer causal relations from temporal data in text* (learning text
patterns) *but fail with counterfactual cues* (which require genuine causal
models of the world).

## §3.3 · The Temporal Blindness Theorem

We state the following as a foundational principle:

> **Theorem (Temporal Blindness):** A language model trained on a static text
> corpus has no intrinsic model of clock time. It cannot know whether event A
> preceded event B in the external world; it can only learn that descriptions of
> A and descriptions of B appear near each other in training text. For any
> financial application where causal sequence in real time is the primary
> information, an LLM is structurally unfit for the reasoning task.

**Corollary:** Fine-tuning an LLM on financial data does not cure temporal
blindness. Fine-tuning on financial text teaches the model that *descriptions
of* event A appear near *descriptions of* event B. It does not give the model
a clock, a calendar, or a causal model of market mechanics.

---

# PART IV — THE CAUSAL ILLUSION PROBLEM

## §4.1 · Statistical Correlation Is Not Causation

The most dangerous property of LLMs in financial applications is not that they
produce wrong outputs — it is that they produce *confidently wrong* outputs that
are *syntactically indistinguishable* from correct ones.

An LLM generating financial analysis cannot say: *"I do not know the causal
mechanism here — this event class is not well-represented in my training data."*
Its training objective compels it to produce the most statistically likely
continuation of the token sequence. In a financial context, the most statistically
likely continuation is the *standard financial narrative* for that type of event.

The result is a confabulation: a confident, fluent, internally coherent
explanation that attributes causality based on the statistical regularities of
financial writing — not on what actually caused what in the market on this
specific day.

## §4.2 · Academic Evidence for the Causal Illusion

The paper "LLMs Are Prone to Fallacies in Causal Inference" (arXiv:2406.12158,
2024) provides direct experimental evidence:

> *"We demonstrate that LLMs exhibit statistical rather than causal reasoning.
> They learn spurious correlations from pre-training that become active during
> inference, leading to systematic errors when the test distribution differs
> from training."*

A complementary finding from "Correlation or Causation: Analyzing the Causal
Structures of LLM and LRM Reasoning" (arXiv:2509.17380, 2025):

> *"LLMs exhibit statistical rather than causal reasoning, whereas LRMs
> [Language Reasoning Models] demonstrate superior causality in their reasoning
> processes. A primary factor undermining the robustness of LLM reasoning is
> their propensity to learn and exploit spurious correlations built during
> pre-training."*

"Do Large Language Models Show Biases in Causal Learning?" (arXiv:2510.13985,
2024) found:

> *"LLMs perform close to random when inferring causation from correlation.
> LLMs infer causal relations from temporal and spatial data in text but fail
> with counterfactual cues."*

And from arXiv:2506.09433 (2025), "Mitigating Spurious Correlations in LLMs
via Causality":

> *"Spurious correlations are built during pre-training of LLMs and become
> spurious when they are not valid anymore in the diverse test distribution,
> causing significant performance drops."*

## §4.3 · The Spurious Correlation Trap in Finance

Financial markets are particularly vulnerable to the spurious correlation trap.
Financial text is full of associations that hold *on average, historically* but
fail in specific circumstances:

- *"BOJ hawkishness → JPY strength"* — true in most cycles, but reversed during
  risk-off flight-to-quality events
- *"Rising gold → falling USD"* — true in most regimes, but decorrelates during
  liquidity crises
- *"Tech rally → NASDAQ outperformance"* — true in bull markets, but not during
  rotations driven by rate changes

An LLM fine-tuned on historical financial text will encode these associations as
high-probability predictions. It cannot know when the current market regime makes
the standard association invalid. It has no model of regimes, no model of
structural breaks, no model of the specific conditions on this specific date.

It will produce the statistically expected narrative — which may be exactly
wrong for the current moment.

---

# PART V — THE HALLUCINATION PROBLEM IN FINANCE

## §5.1 · Defining Financial Hallucination

In the general AI literature, *hallucination* refers to the generation of
factually incorrect content that is presented with the fluency and confidence
of correct content. In financial applications, hallucination takes specific
and dangerous forms:

1. **Factual hallucination:** Citing a financial event, earnings figure, or
   policy decision that did not occur, or occurred with different parameters
2. **Causal hallucination:** Attributing a price move to a cause that was not
   operative on that day, based on common patterns in financial text
3. **Temporal hallucination:** Describing the current market state using
   information that was true in the training data but is no longer true
4. **Numerical hallucination:** Producing financial figures (yields, ratios,
   prices) that are plausible-looking but incorrect

## §5.2 · Empirical Measurement of Financial Hallucination

The academic literature provides alarming quantitative evidence.

"Deficiency of Large Language Models in Finance: An Empirical Examination of
Hallucination" (arXiv:2311.15548, 2023) found:

> *"Off-the-shelf LLMs experience serious hallucination behaviors in financial
> tasks, with one finance-focused LLM producing fabricated content in 41% of
> probing test cases."*

41%. Not an edge case. Not a tail risk. Nearly half of outputs from a dedicated
financial LLM contained hallucinated content in structured testing.

The PHANTOM benchmark (OpenReview, 2025) on hallucination detection in financial
long-context question-answering found:

> *"Large Language Models show great promise, but their tendencies to hallucinate
> pose significant risks in high-stakes domains like finance, especially when used
> for regulatory reporting and decision-making."*

The FAITH framework (arXiv:2508.05201, 2025) on tabular hallucinations in finance
documented that:

> *"Even state-of-the-art models frequently misinterpret financial terms or
> misreport numerical values. Hallucinations in finance exhibit domain-specific
> characteristics that standard benchmarks do not capture."*

The "Profit Mirage" paper (arXiv:2510.07920, 2025) exposed a critical failure
mode in LLM-based financial agents:

> *"LLM-based financial agents are susceptible to information leakage and
> confabulation when backtesting — producing apparently strong results that
> do not survive out-of-sample validation."*

## §5.3 · Why Hallucination Is Especially Dangerous in Finance

In a creative writing context, hallucination produces an inaccurate story. The
cost is aesthetic.

In a financial decision context, hallucination produces an inaccurate thesis
update, an incorrect probability estimate, an erroneous position recommendation.
The cost is capital. In a system with automated execution, the cost is immediate
and irreversible.

The financial hallucination problem is compounded by three properties unique to
the domain:

1. **Precision requirement:** Financial analysis requires exact figures. A
   probability of 0.72 and a probability of 0.78 imply different Kelly sizing.
   An LLM that produces "approximately 75%" from pattern matching has introduced
   error into a quantitative pipeline.

2. **Rapid update cycle:** Financial reality changes every 39 minutes (in
   BlueLotus V3). An LLM whose training data ends six months ago cannot know
   the current state of the BOJ rate cycle, the Hormuz situation, or the CKRI
   reading for the PETRO_RECYCLED_DOLLAR thesis.

3. **Adversarial environment:** Markets are adversarial. When an LLM produces
   a "standard" response to a "standard" financial pattern, it is responding to
   the historical average — not to the specific, potentially anomalous, current
   moment. Adversarial market participants specifically seek to create situations
   where standard patterns fail.

---

# PART VI — ORIGINAL EMPIRICAL CASE STUDY
## The BlueLotus Computex Failure Pattern

## §6.1 · System Context

BlueLotus V3 is a deterministic, institutional-grade investment intelligence
pipeline operated by a single CIO from Singapore. As of June 2026, it runs 65
deterministic analytical steps every 39 minutes, ingesting data from 50+ sources,
and producing structured intelligence reports across 9 analytical dimensions.

The system's design is deliberately LLM-limited in the decision loop: LLMs
(Qwen3:4B, run locally on RTX 5060 Ti) are used exclusively for text synthesis
of pre-computed numerical results. No LLM computes a probability. No LLM updates
a thesis. No LLM sizes a position.

This architecture was not the starting point. It was the conclusion of an empirical
failure — documented here as the Computex Failure Pattern.

## §6.2 · The Failure — 3 June 2026

On the morning of 3 June 2026, the MRVL (Marvell Technology) stock surged +29.8%
in a single session. The surrounding market showed broad AI/semiconductor strength,
Clean Energy bid, and selective risk-on behaviour.

The BlueLotus V1 system at that time had 61 active data sources. It captured the
effect perfectly:

| Signal | Value | Status |
|--------|-------|--------|
| MRVL price change | +29.8% | ✅ Captured |
| AI/Semis sector | Risk-on | ✅ Captured |
| Space sector | Rebounding | ✅ Captured |
| Clean Energy | Bid | ✅ Captured |
| Broad market regime | Selective risk-on | ✅ Captured |

The system produced a confident intelligence report. The data was fresh. The
sources were active. The narrative was coherent.

But the cause of the entire move was invisible to the system:

| Event | Status |
|-------|--------|
| Computex 2026 — running all week | ❌ Invisible |
| Jensen Huang keynote — market-moving | ❌ Invisible |
| Jensen Huang surprise Marvell appearance | ❌ Invisible |
| AI infrastructure conference sentiment | ❌ Invisible |
| CEO market-moving event (scheduled, recurring, public) | ❌ Invisible |

The system described *what moved* with precision. It could not explain *why it
moved*. It produced false confidence from abundant but causally incomplete data.

## §6.3 · The Structural Parallel to LLM Failure

The Computex Failure is not merely a data coverage problem. It is a structural
illustration of what happens when any intelligence system — human, algorithmic,
or LLM-based — confuses *data abundance with causal understanding*.

The parallel to LLM behaviour is precise:

| BlueLotus V1 (Computex) | LLM in Financial System |
|------------------------|------------------------|
| 61 data sources present | Billions of training tokens present |
| Captured market effects | Captures text patterns about market effects |
| Could not see the cause | Cannot distinguish cause from co-occurrence |
| Produced confident narrative | Produces confident narrative |
| Narrative was wrong | Narrative may be wrong in the same way |
| False confidence from incomplete information | False confidence from statistical association |

The critical insight: **An LLM integrated into the analytical decision layer
of a financial system would reproduce the Computex Failure pattern structurally
and permanently** — not because of a missing data source that can be added, but
because of a missing faculty that cannot be acquired through training.

The V1 system's blind spot was a solvable engineering problem. The 8-Lens blind
spot detection system, the causal chain test, and the forward catalyst calendar
were built to solve it. An LLM's temporal blindness and causal confusion are not
solvable engineering problems. They are properties of the training objective.

## §6.4 · The Institutional Response — Doctrine Over Automation

The institutional response to the Computex Failure was not to add an LLM to
fill the gap. It was to add *human cognitive controls*:

1. **The Causal Chain Test** — an 8-step checklist requiring explicit causal
   identification before any intelligence conclusion is accepted
2. **The Blind Spot Doctrine** — a formal requirement to audit what the dataset
   *cannot* see before trusting what it *can* see
3. **The 8-Lens Framework** — a structured multi-dimensional interrogation
   requiring forward catalyst coverage (L8)
4. **The Socratic Doctrine** — the institutional principle that "I know that
   I do not know" is the beginning of genuine intelligence

These are cognitive controls — structures that enforce epistemic humility on a
system that would otherwise produce confident but incomplete analysis. They work
because they are transparent, auditable, and designed with awareness of their
own limitations.

An LLM-based replacement for these controls would have the same fundamental
problem as V1: producing confident outputs without the awareness that the
outputs might be causally ungrounded.

---

# PART VII — SURVEY OF RELATED LITERATURE

## §7.1 · LLM Temporal Reasoning — State of the Field

The academic community has increasingly recognised temporal reasoning as a
fundamental challenge for LLMs in practical applications.

**Yu et al. (2023), "Temporal Data Meets LLM — Explainable Financial Time
Series Forecasting"** (arXiv:2306.11025, EMNLP 2023) established that
LLM-based approaches can outperform classical ARMA-GARCH models on text-based
financial forecasting — but this performance is driven by text pattern matching,
not temporal causal reasoning. The authors note the critical limitation that
approaches which modify LLM embedding spaces for time-series lose their original
language reasoning capabilities, creating an unresolvable tradeoff.

**The 2025 Survey on Reasoning and Agentic Systems in Time Series**
(arXiv:2509.11575) identifies the state of the field as follows:
LLMs can extract patterns from time-series descriptions in text but cannot
perform the kind of zero-shot causal temporal reasoning that financial analysis
demands. The paper highlights temporal ordering, regime change detection, and
counterfactual reasoning as open unsolved problems.

## §7.2 · Causal Reasoning Limitations

**"LLMs Are Prone to Fallacies in Causal Inference"** (arXiv:2406.12158, 2024)
is the most direct empirical indictment of LLM causal reasoning:

> *"We demonstrate that LLMs fail to distinguish correlation from causation in
> systematic ways, producing fallacious causal attributions that would not be
> accepted by a domain expert."*

**"Do Large Language Models Show Biases in Causal Learning?"**
(arXiv:2510.13985, 2024):

> *"LLMs perform close to random when inferring causation from correlation.
> They infer causal relations from temporal and spatial data in text but fail
> with counterfactual cues — exactly the type of cue that distinguishes genuine
> causal reasoning from sophisticated pattern matching."*

**"Correlation or Causation: Analyzing the Causal Structures of LLM Reasoning"**
(arXiv:2509.17380, 2025):

> *"LLMs exhibit statistical rather than causal reasoning. The spurious
> correlations built during pre-training cause significant performance drops
> when the test distribution departs from training distribution."*

## §7.3 · Hallucination in Financial Applications

**arXiv:2311.15548 (2023)** — 41% hallucination rate in financial tasks.
This is the landmark quantitative finding. Nearly half of outputs from a
dedicated financial LLM were factually fabricated in structured testing.

**PHANTOM Benchmark (OpenReview, 2025)** — Established that existing hallucination
detection methods fail to capture the specific patterns of financial hallucination,
which require high numerical precision and long-context reasoning.

**FAITH Framework (arXiv:2508.05201, 2025)** — Demonstrated that even
state-of-the-art models systematically misreport numerical values in financial
tabular contexts.

**"Profit Mirage" (arXiv:2510.07920, 2025)** — Showed that LLM-based financial
agents produce apparently strong backtest results that collapse out-of-sample
due to information leakage and confabulation in the testing process.

**BayTech Consulting (2025), "Hidden Dangers of AI Hallucinations in Financial
Services"** documented that hallucinations of omission — where the model lacks
specific knowledge and confabulates an answer — are particularly acute for
information with a rapid update cycle such as financial regulations, corporate
earnings, and current events.

## §7.4 · The Philosophical Foundation — Stochastic Parrots

**Bender, Gebru, McMillan-Major, Shmitchell (2021), "On the Dangers of Stochastic
Parrots: Can Language Models Be Too Big?"** (FAccT 2021) remains the foundational
philosophical text. The stochastic parrot metaphor captures precisely what makes
LLMs dangerous in financial contexts: they produce statistically plausible outputs
without any comprehension of whether those outputs refer to something real.

> *"The language model has no way to know whether the tokens it generates refer
> to something true, something false, or something that has never existed."*

In financial applications, the tokens generated may refer to:
- A market event that actually occurred and caused the pattern described ✅
- A common financial narrative applied to a case where it does not fit ❌
- A hallucinated causal chain that sounds plausible but is fabricated ❌

The LLM cannot distinguish between these cases. The reader cannot know which
case applies without independent verification — which defeats the purpose of
using the LLM for analysis.

**"Deanthropomorphising NLP: Can a Language Model Be Conscious?"**
(arXiv:2211.11483) provides the clearest statement of the consciousness question:

> *"There is currently no scientific consensus that large language models have
> or could have conscious experience. The behaviours that suggest consciousness
> — fluent language, apparent reasoning, expressed preferences — are all
> explicable as sophisticated pattern completion without any inner experience."*

The conclusion is not merely academic. It has direct architectural implications:
a system without consciousness, without sentience, without genuine temporal
experience, should not be given decision authority over capital.

---

# PART VIII — THE AUTOMATION BIAS DANGER

## §8.1 · What Automation Bias Is

Automation bias is the well-documented tendency of humans to over-trust the
outputs of automated systems — to defer to machine outputs even when those
outputs conflict with the human's own judgment or with clear evidence.

The Decision Lab defines it as: *"The tendency to favour suggestions from
automated decision-making systems and to ignore contradictory information
without the automation."*

## §8.2 · Why Automation Bias Is Especially Dangerous with LLMs

Standard automation bias involves systems that produce structured numerical
outputs — a credit score, a risk flag, a trading signal. The human can see that
it is a number and can, in principle, question the number.

LLMs produce *fluent natural language*. The output looks like expert analysis.
It reads with the authority of a senior analyst. It uses correct financial
terminology. It is grammatically and stylistically impeccable.

This makes LLM-induced automation bias significantly more dangerous than
traditional automation bias:

1. **The output is indistinguishable from expert output.** A human reader
   cannot easily tell, from the text alone, whether the analysis is grounded
   in current market data or in historical statistical patterns.

2. **The fluency creates trust.** Research consistently shows that articulate,
   well-written text is rated as more credible and accurate than less articulate
   text on the same subject — even when accuracy is held constant.

3. **The confidence is constant.** An LLM produces output at the same level of
   apparent confidence whether it is drawing on high-quality, relevant training
   data or confabulating from weak statistical associations. The user cannot
   distinguish the two.

## §8.3 · Regulatory Recognition

The International AI Safety Report 2026 (arXiv:2602.21012, Bengio et al.)
explicitly warns:

> *"Early evidence suggests that reliance on AI tools can weaken critical thinking
> skills and encourage automation bias — the tendency to trust AI system outputs
> without sufficient scrutiny."*

The ESRB Advisory Scientific Committee Report No. 16 (December 2025) on AI and
Systemic Risk identifies automation bias in financial institutions as a source
of correlated risk — when many institutions use similar LLM-based analytical
systems, they may make correlated errors at scale, amplifying systemic
vulnerability.

The IOSCO report CR/01/2025 flags autonomous AI decision-making in financial
markets as requiring enhanced regulatory oversight precisely because the opacity
of LLM reasoning makes it difficult for human supervisors to verify the basis
for decisions.

## §8.4 · The Human-in-the-Loop Imperative

The academic and regulatory consensus on high-stakes AI deployment is converging
on a consistent position: **human oversight is not optional in domains where
errors have material consequences.**

Research on Human-in-the-Loop (HITL) systems (MDPI Entropy, 2025) establishes
that HITL frameworks are most effective in environments with:
- High error costs (financial trading qualifies)
- Explainability requirements (regulatory compliance qualifies)
- Rapidly changing conditions (financial markets qualify)
- Adversarial environments (markets are explicitly adversarial)

A study published in PMC (2024) on automated decision-making found that human
oversight is vital in contexts where incorrect decisions can lead to significant
harm — and identified the critical risk of automation bias compounding errors
when humans defer to AI outputs without scrutiny.

The FCA's 2024 survey found that only 2% of AI use cases in financial services
used fully autonomous decision-making. 55% used some degree of human review.
The 2% figure represents the current boundary of acceptable practice — and even
that 2% is under increasing regulatory scrutiny.

---

# PART IX — A DOCTRINE FOR RESPONSIBLE LLM DEPLOYMENT

## §9.1 · The Two Zones

From the theoretical and empirical evidence assembled in this thesis, we can
define two zones of LLM deployment:

**Zone A — Where LLMs Are Powerful and Safe:**

```
Text synthesis        Summarising pre-computed numerical results
Document parsing      Extracting structured data from filings and reports
Pattern description   Describing what is in a dataset (not why it is there)
Report writing        Translating numerical outputs into readable prose
Hypothesis generation Suggesting candidate theses for human evaluation
Template completion   Filling structured templates from provided context
```

**Zone B — Where LLMs Are Dangerous and Must Not Be Used:**

```
Causal attribution    "X caused Y because..."  (LLM cannot know this)
Probability updating  "P(thesis) = 0.72"       (must come from Bayes, not tokens)
Temporal sequencing   "This happened before that in markets" (LLM has no clock)
Position sizing       "Buy N shares"            (LLM has no risk model)
Thesis retirement     "Kill this thesis"        (must come from FSM, not text)
Regime identification "We are in RISK OFF"      (must come from deterministic ops)
Trade execution       Any form of order routing (must remain with human CIO)
```

## §9.2 · The BlueLotus LLM Boundary Doctrine

The following doctrine was formally adopted by BlueLotus Fund on 22 June 2026
following the completion of this thesis:

**BLV3-DOCTRINE-010 — LLM Boundary Doctrine:**

> *Large Language Models are permitted in BlueLotus V3 for one purpose only:
> synthesis of pre-computed numerical results into structured English advisory
> text for CIO consumption. LLMs shall not compute probabilities, update thesis
> states, generate trading signals, size positions, or reason about temporal
> causality. The boundary between numerical computation (mathematics) and text
> synthesis (language model) is permanent and inviolable.*
>
> *Rationale: LLMs are trained on static text corpora using next-token prediction.
> They have no model of clock time, no causal model of market mechanics, and no
> capacity to distinguish "what usually appears in financial text" from "what
> actually happened in the market." Fine-tuning does not cure this. RAG does not
> cure this. These are structural properties of the technology, not engineering
> gaps. Using an LLM for numerical financial reasoning is equivalent to asking a
> thesaurus to solve a differential equation — the tool is not wrong; it is simply
> not designed for the task.*

## §9.3 · Practical Guidelines for Developers

The following guidelines are offered to developers building financial intelligence
systems that incorporate LLMs:

**Guideline 1 — Separate the Numerical Layer from the Language Layer Absolutely**

Never allow an LLM to produce a number that enters a financial calculation.
Numbers must come from deterministic mathematical operators, Bayesian engines,
statistical models, or reinforcement learning agents trained on historical data.
LLMs may describe those numbers in prose. They may not generate them.

**Guideline 2 — Never Trust LLM Causal Attribution**

When an LLM writes "X caused Y," treat this as a hypothesis for human
verification — not as an established fact. The LLM learned that descriptions
of X and descriptions of Y appear together in financial text. It did not observe
the causal mechanism.

**Guideline 3 — Temporal Claims Require Timestamp Verification**

Any LLM output that makes a claim about the current state of the market, current
prices, current central bank positions, or current geopolitical conditions must
be verified against live data. The LLM's training cutoff means it may be months
or years out of date on any specific fact.

**Guideline 4 — Hallucination Rate × Stakes = Risk Exposure**

With a 41% hallucination rate on financial tasks (arXiv:2311.15548), the expected
number of hallucinated outputs in a 65-step pipeline using LLMs throughout would
be 26+ fabricated or inaccurate analytical claims per cycle. At 39-minute cycles,
this is 960+ fabricated claims per day entering the decision process.

**Guideline 5 — Autonomous Execution Requires Non-LLM Decision Layers**

Any system that connects LLM output to order execution — even via multiple
intermediate steps — has created a pathway for hallucinated analysis to result
in real capital deployment. This pathway must not exist. Execution must require
an explicit human confirmation step that cannot be bypassed.

**Guideline 6 — Treat LLMs as Brilliant Interns, Not Senior Analysts**

A brilliant intern can write fluent summaries, draft reports, and propose ideas
for review. They should not have signing authority on trades. They should not be
the final reviewer of their own work. Their outputs should be checked before
action is taken. LLMs are brilliant interns who happen to have read every
financial document ever written — but who have never actually traded a single
day in their lives, and who have no memory of yesterday.

---

# PART X — THE HUMAN COGNITIVE SOVEREIGN

## §10.1 · What a Human CIO Uniquely Possesses

The argument for keeping the human CIO in the decision loop is not sentimental.
It is not anti-technology. It is a factual statement about what properties are
required for reliable financial decision-making, and which entities currently
possess them.

| Required Property | LLM | DRL Agent | Deterministic System | Human CIO |
|-------------------|-----|-----------|---------------------|-----------|
| Genuine temporal awareness | ❌ | ✅ (numerical) | ✅ (by clock) | ✅ (lived experience) |
| Causal model of market mechanics | ❌ | ✅ (learned) | ✅ (encoded) | ✅ (understood) |
| Contextual institutional memory | ❌ | ❌ | ✅ (logged) | ✅ (experienced) |
| Accountability for outcomes | ❌ | ❌ | ❌ | ✅ (bears consequences) |
| Adaptability to novel regimes | ❌ (statistical) | ⚠️ (generalisation) | ❌ (rule-bound) | ✅ (reasoning) |
| Ethical judgment | ❌ | ❌ | ❌ | ✅ |
| Sentience | ❌ | ❌ | ❌ | ✅ |

The human CIO is the only entity in any financial system that simultaneously
possesses: temporal awareness, causal understanding, institutional memory,
accountability, ethical judgment, and sentience.

These are not minor advantages. They are the core prerequisites for the kind
of judgment that financial markets demand.

## §10.2 · The Correct Role of Technology in Investment Intelligence

Technology — including LLMs, DRL agents, Bayesian engines, deterministic
operators — serves one legitimate function in investment intelligence:

**To amplify the informational capacity of the human CIO without displacing
the CIO's cognitive sovereignty.**

This means:
- Technology processes 50+ data sources so the CIO does not have to
- Technology applies Bayesian mathematics so the CIO receives calibrated probabilities
- Technology runs 315 regression tests so the CIO can trust the pipeline
- Technology synthesises 9 agent reports so the CIO receives structured analysis
- Technology publishes the dashboard so the CIO can monitor in real time

But:
- Technology does **not** decide what the thesis probability means for action
- Technology does **not** decide which thesis to kill
- Technology does **not** decide position size without the CIO's review
- Technology does **not** execute a single trade

The human CIO is not a bottleneck in this architecture. The human CIO is the
**purpose** of this architecture. Everything the technology does is in service
of the CIO's decision — not in replacement of it.

## §10.3 · Why This Architecture Is More Robust Than Autonomous Systems

The BlueLotus V3 architecture has demonstrated a specific kind of robustness
through the Computex Failure event. When the system produced false confidence
from incomplete data, the response was not to add more automation — it was to
add more human cognitive controls (the Blind Spot Doctrine, the Causal Chain
Test, the 8-Lens Framework).

These controls work because they encode human epistemic standards into the
system's operating procedure. They represent accumulated human wisdom about
how to reason under uncertainty — not statistical pattern matching from training
data, but principles derived from real experience of real failures.

An autonomous system that failed in the Computex pattern would need its training
data updated, its reward function modified, its weights retrained. The process
takes time, requires data, and may introduce new failure modes.

A human CIO who failed in the Computex pattern wrote a doctrine on the day of
the failure, implemented new controls the following week, and carried the
lesson forward as institutional memory — forever.

**That is the advantage of sentience.**

---

# PART XI — CONCLUSION

## §11.1 · Summary of Findings

This thesis has established:

1. **LLMs are next-token predictors, not temporal reasoners.** Their training
   objective produces sophisticated text prediction — not causal models of
   market dynamics, not temporal awareness, not genuine understanding.

2. **LLMs perform close to random on causal inference tasks** (arXiv:2510.13985).
   They mistake statistical co-occurrence for causation — exactly the error
   that financial analysis most needs to avoid.

3. **LLMs hallucinate in financial tasks at a 41% rate** (arXiv:2311.15548).
   In a 65-step pipeline, this produces a catastrophic volume of fabricated
   analytical inputs if LLMs are placed in the analytical decision layer.

4. **The Computex Failure Pattern illustrates the structural parallel** between
   a reactive intelligence system that mistakes data abundance for causal
   understanding, and an LLM that mistakes statistical co-occurrence for causal
   analysis. Both produce the same failure: confident, fluent, wrong outputs.

5. **Automation bias amplifies all of the above** (International AI Safety
   Report 2026, arXiv:2602.21012). Human users of LLM-based systems tend to
   over-trust outputs that are fluent and confident — even when those outputs
   are causally ungrounded.

6. **The correct deployment boundary for LLMs in financial intelligence is
   text synthesis only** — wrapping pre-computed numerical results in readable
   prose for CIO consumption.

7. **The human CIO is irreplaceable** — not because technology is insufficient,
   but because the CIO uniquely possesses temporal awareness, causal
   understanding, accountability, and sentience.

## §11.2 · A Message to Developers

This thesis is addressed, in its final paragraphs, directly to developers
building AI systems for financial applications.

LLMs are magnificent instruments. They represent a genuine breakthrough in
computational linguistics. They can do things that would have seemed impossible
ten years ago. They deserve the excitement they have received.

They are not sentient. They are not temporally aware. They do not understand
markets. They do not understand time. They do not understand cause and effect.
They understand text. They are very, very good at text.

When you build a financial intelligence system that deploys an LLM in the
analytical decision layer — that asks an LLM to update thesis probabilities,
to identify regime changes, to attribute market moves to causes, to size
positions, to trigger execution — you are asking a text predictor to be a
market analyst. You are asking a stochastic parrot to be a portfolio manager.

The parrot will answer. It will answer fluently. It will answer confidently.
It will answer in the language of finance, with all the right vocabulary and
all the right stylistic conventions.

And it may be wrong 41% of the time, in ways that look exactly like it is right.

Be careful. The intelligence layer of a financial system is not a place for
tools that cannot know when they are wrong.

**Keep the human in the loop. Not as a rubber stamp. As the sovereign.**

Strategic thinking is human. Planning is human. Execution is human. The judgment
call — the final, consequential, accountable, *I-will-bear-the-consequences-of-this*
judgment call — must always be human.

LLMs are wonderful tools. Use them as tools. Do not let them use you as a proxy
for their statistical predictions.

## §11.3 · The BlueLotus Thesis

BlueLotus V3 was built on a simple premise: a single human CIO, equipped with
the right institutional intelligence infrastructure, can navigate complex global
markets with the precision of a quant fund — while retaining the judgment of
a human being.

That infrastructure includes:
- Deterministic Bayesian mathematics for probability updating
- Reinforcement learning for empirical sizing optimisation
- Formal governance doctrines enforced in code
- Causal blind spot detection protocols
- Human-in-the-loop at every consequential decision point

And it explicitly excludes:
- LLMs in the analytical decision layer
- Automated execution without human confirmation
- Any system that cannot fully account for what it calculated and why

This is not a limitation of ambition. It is an expression of understanding.

Understanding what the tools are. Understanding what the human is.
Understanding where each belongs.

*The tools compute. The CIO decides. That order is not negotiable.*

---

# PART XII — REFERENCES

1. Bender, E.M., Koller, A. (2020). *Climbing to NLU: On Meaning, Form, and
   Understanding in the Age of Data.* Proceedings of the 58th Annual Meeting of
   the Association for Computational Linguistics. ACL 2020.

2. Bender, E.M., Gebru, T., McMillan-Major, A., Shmitchell, S. (2021).
   *On the Dangers of Stochastic Parrots: Can Language Models Be Too Big?*
   FAccT 2021. [The foundational "stochastic parrot" paper.]

3. Yu, C. et al. (2023). *Temporal Data Meets LLM — Explainable Financial Time
   Series Forecasting.* EMNLP 2023 Industry Track. arXiv:2306.11025.

4. Anonymous (2023). *Deficiency of Large Language Models in Finance: An
   Empirical Examination of Hallucination.* arXiv:2311.15548.
   [41% hallucination rate finding.]

5. Kang, M. et al. (2025). *PHANTOM: A Benchmark for Hallucination Detection
   in Financial Long-Context QA.* OpenReview, 2025.

6. Anonymous (2025). *FAITH: A Framework for Assessing Intrinsic Tabular
   Hallucinations in Finance.* arXiv:2508.05201.

7. Bengio, Y. et al. (2026). *International AI Safety Report 2026.*
   arXiv:2602.21012. [100+ AI experts, 30+ nations.]

8. Anonymous (2024). *LLMs Are Prone to Fallacies in Causal Inference.*
   arXiv:2406.12158.

9. Anonymous (2024). *Do Large Language Models Show Biases in Causal Learning?
   Insights from Contingency Judgment.* arXiv:2510.13985.
   [LLMs perform close to random on causal inference.]

10. Anonymous (2025). *Correlation or Causation: Analyzing the Causal Structures
    of LLM and LRM Reasoning Process.* arXiv:2509.17380.
    [LLMs exhibit statistical rather than causal reasoning.]

11. Anonymous (2025). *Mitigating Spurious Correlations in LLMs via Causality.*
    arXiv:2506.09433.

12. Anonymous (2025). *A Survey of Reasoning and Agentic Systems in Time Series
    with Large Language Models.* arXiv:2509.11575.

13. Anonymous (2025). *Profit Mirage: Revisiting Information Leakage in
    LLM-based Financial Agents.* arXiv:2510.07920.

14. Anonymous (2025). *The Agentic Regulator: Risks for AI in Finance and a
    Proposed Agent-based Framework for Governance.* arXiv:2512.11933.

15. Anonymous (2025). *Toward Reasoning-Centric Time-Series Analysis.*
    arXiv:2510.13029.

16. Anonymous (2025). *Deanthropomorphising NLP: Can a Language Model Be
    Conscious?* arXiv:2211.11483. PMC11617003.

17. ESRB Advisory Scientific Committee (December 2025). *AI and Systemic Risk.*
    Advisory Scientific Committee Report No. 16. European Systemic Risk Board.

18. IOSCO (March 2025). *Artificial Intelligence in Financial Markets.*
    CR/01/2025. International Organization of Securities Commissions.

19. BayTech Consulting (2025). *Hidden Dangers of AI Hallucinations in
    Financial Services.* Industry Report.

20. Anonymous (2025). *Human-in-the-Loop AI: Enhancing Transparency and
    Accountability.* ResearchGate, 2025.

21. Anonymous (2024). *Putting a Human in the Loop: Increasing Uptake, but
    Decreasing Accuracy of Automated Decision-Making.* PMC10857587.

22. Soh, W.K. (2026). *BlueLotus V2 Thesis: Self-Learning Digital Institutional
    Intelligence Cognitive System.* Internal Research Document, 3 June 2026.
    BlueLotus Fund, Singapore.

23. Soh, W.K., Claude Code, Dr. (2026). *BlueLotus NITE-PEI Engine: Integrated
    Thesis.* BlueLotus Research Repository. June 2026.

24. Soh, W.K., Claude Code, Dr. (2026). *BlueLotus V3 Upgrade Path Thesis V2.0:
    LLM Integration Rejected — Two Validated Upgrades.* BlueLotus Research
    Repository. 22 June 2026.

---

<div align="center">

*This thesis is submitted to the public record of the BlueLotus Research
Repository as a permanent contribution to the responsible development of
AI-assisted investment intelligence systems.*

*Soh Wee Kian · CIO · BlueLotus Fund Singapore · 22 June 2026*

---

```
CIO_ONLY_MANUAL: TRUE · ORDER_ROUTING: DISABLED · LLM: TEXT SYNTHESIS ONLY
HUMAN COGNITIVE SOVEREIGNTY: PERMANENT AND NON-NEGOTIABLE · 🌸
```

</div>
