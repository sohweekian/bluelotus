# 🪷 BlueLotus V3 — Live Dashboard

> *Deterministic capital-markets research dashboard. Contradiction-mapped intelligence for CIO review — not a trading bot.*

[![Live Site](https://img.shields.io/badge/Live-sohweekian.github.io%2Fbluelotus-4fc3f7?style=flat-square)](https://sohweekian.github.io/bluelotus/)
[![Chief Clerk](https://img.shields.io/badge/Chief_Clerk-Deterministic_Zone_A-533483?style=flat-square)](https://sohweekian.github.io/bluelotus/chief-strategist.html)
[![Engine](https://img.shields.io/badge/pip-bluelotus--engine-e94560?style=flat-square)](https://github.com/sohweekian/bluelotus-engine)
[![License](https://img.shields.io/badge/License-MIT-8b93a7?style=flat-square)](LICENSE)

---

## What is this repo?

This repository is the **published dashboard surface** for BlueLotus V3 — HTML, JSON data, and CIO correspondence pushed from the private pipeline via `bluelotus_publisher.py`.

It is **not** the full engine. For the open research software:

```bash
pip install bluelotus-engine
```

Source: [github.com/sohweekian/bluelotus-engine](https://github.com/sohweekian/bluelotus-engine)

---

## Production posture (June 2026)

| Principle | Value |
|-----------|--------|
| Execution | `CIO_ONLY_MANUAL` |
| Order routing | Disabled |
| Production intelligence | **Deterministic Chief Clerk** (Zone A) |
| LLM agent council | Quarantined — not authoritative |
| Research only | No advice · no automatic orders |

The **Chief Clerk page** (`chief-strategist.html`) is entirely deterministic — computed from report bundle, governance gate, operators, and portfolio math. No Qwen council in the production path.

---

## Key pages

| Page | URL |
|------|-----|
| Command Center | [/bluelotus/](https://sohweekian.github.io/bluelotus/) |
| Chief Clerk (Zone A) | [/chief-strategist.html](https://sohweekian.github.io/bluelotus/chief-strategist.html) |
| CIO Letter | [/cio-letter.html](https://sohweekian.github.io/bluelotus/cio-letter.html) |

---

## Why agents were removed

Live field evaluation (June 2026) found LLM agents unfit for production clerk duty: temporal blindness, partial-read hallucination, non-reproducible outputs.

Details: [bluelotus-engine-docs](https://github.com/sohweekian/bluelotus-engine-docs) · [DETERMINISTIC_TRANSITION.md](https://github.com/sohweekian/bluelotus-research/blob/main/DETERMINISTIC_TRANSITION.md)

---

## Related repos

- **bluelotus-engine** — pip-installable sanitized engine (no publish, no telegram)
- **bluelotus-engine-docs** — architecture narrative
- **bluelotus-research** — theses & doctrines
- **sohweekian** — profile README

---

*Research only. All execution requires independent human review.*
