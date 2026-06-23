# 🪷 BlueLotus V3

> *A deterministic, LLM-assisted capital markets research system built on Bayesian inference, Shannon entropy, and game theory.*

[![GitHub Pages](https://img.shields.io/badge/Live%20Site-sohweekian.github.io%2Fbluelotus-c084fc?style=flat-square&logo=github)](https://sohweekian.github.io/bluelotus/)
[![License](https://img.shields.io/badge/License-Proprietary-8b93a7?style=flat-square)](LICENSE)
[![Status](https://img.shields.io/badge/Pipeline-ACTIVE-4ade80?style=flat-square)](.)

---

## What is BlueLotus?

BlueLotus V3 is a 65-step deterministic research pipeline that runs on a ~39-minute cycle. It ingests live market data, news signals, and macro thesis evidence — then synthesises them into a structured, contradiction-mapped intelligence report for CIO review.

It is not a trading bot. It is a **research and contradiction-mapping system**. Every execution decision requires independent human review.

---

## Architecture at a Glance

| Module | Role |
|---|---|
| **NITE-PEI** | Bayesian kill-condition engine — tracks thesis invalidation probability |
| **ACMS-COP** | Multi-agent capital markets state system — 5 scenario forecasts per cycle |
| **STR** | Shannon-Thorp Refinement — signal entropy scoring + Kelly position sizing |
| **BGTM-V1** | Game theory module (N-player Bayesian Nash Equilibrium) — parallel research |
| **Snapshot Archive** | 1,600+ immutable point-in-time pipeline captures for audit and calibration |

---

## Live Pages

| Page | Description |
|---|---|
| [Command Center](https://sohweekian.github.io/bluelotus/) | Live pipeline dashboard |
| [CIO Dashboard](https://sohweekian.github.io/bluelotus/cio-dashboard.html) | Portfolio and thesis overview |
| [Superforecasting Thesis](https://sohweekian.github.io/bluelotus/superforecasting-thesis.html) | Calibration framework |
| [BlueLotus Framework](https://sohweekian.github.io/bluelotus/bluelotus-framework.html) | System architecture overview |
| [BGTM Thesis](https://sohweekian.github.io/bluelotus/bgtm-thesis.html) | Game Theory research |
| [Watchlist](https://sohweekian.github.io/bluelotus/bluelotus-watchlist.html) | Live signal watchlist |

### Research Tributes

Built on the intellectual shoulders of:
[Claude Shannon](https://sohweekian.github.io/bluelotus/shannon-tribute.html) ·
[Ed Thorp](https://sohweekian.github.io/bluelotus/thorp-tribute.html) ·
[Alan Turing](https://sohweekian.github.io/bluelotus/turing-tribute.html) ·
[Albert Einstein](https://sohweekian.github.io/bluelotus/einstein-tribute.html) ·
[John Nash](https://sohweekian.github.io/bluelotus/gametheory-tribute.html)

---

## Governance Doctrine

```
CIO_ONLY_MANUAL        = TRUE
ORDER_ROUTING_ENABLED  = FALSE
LLM_ORDER_GENERATION   = FALSE
SYSTEM_ORDERS_GENERATED must remain ZERO
```

All LLM outputs are contradiction maps and research summaries — never trade recommendations. See [DISCLAIMER.md](DISCLAIMER.md).

---

## Research Archive

Architectural theses and upgrade proposals are maintained in [`/research`](research/).

---

*BlueLotus V3 — Professional Portfolio Manager News Agency*
