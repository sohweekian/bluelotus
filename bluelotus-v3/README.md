# BlueLotus V3

BlueLotus V3 is an AI-assisted investment intelligence platform for a human Chief Investment Officer. It is designed for research, governance, portfolio review, forecasting, and report generation. It is not an autonomous trading bot.

Core doctrine:

- Agents may analyze, critique, vote, and route recommendations.
- The CIO makes all final decisions.
- Trade execution is manual and external to this public package.
- Published outputs should be treated as research artifacts, not financial advice.

## Architecture

The V3 pipeline is organized around a deterministic data and governance layer, a specialist agent council, and a chief strategist synthesis layer.

1. Market intelligence data is ingested by the `mid/` layer.
2. Raw signals are normalized into internal snapshots.
3. Governance and scenario overlays run deterministic checks before agent interpretation.
4. Specialist agents generate schema-bound reports from curated evidence slices.
5. The chief strategist resolves disagreements and produces CIO-ready briefings.
6. Research, thesis, and dashboard publishing layers render the final artifacts.

Important directories:

- `agents/`: Specialist agent definitions and report logic.
- `chief_strategist/`: Synthesis, disagreement handling, and briefing generation.
- `config/`: Agent, prompt, model, thesis, widget, and pipeline configuration.
- `core/`: Database and persistence helpers.
- `governance/`: Deterministic safety, operator, and regression-test logic.
- `llm_clients/`: Local LLM routing, validation, and health checks.
- `mid/`: Market intelligence ingestion and publishing helpers.
- `news_reporter_agency/`: News extraction, classification, deduplication, and alerting modules.
- `orchestration/`: End-to-end cycle runners.
- `research/`: Thesis writeups, report generation, forecasting, and research documents.
- `reports/`: Technical reports and implementation records.
- `schemas/`: JSON schema contracts for agent and strategist outputs.
- `tests/`: Focused regression and behavior tests.
- `thesis_engine/`: Thesis lifecycle and conflict evaluation.

## Documentation And Thesis Materials

Key public writeups included in this sanitized package:

- `research/BlueLotus_V3_Architecture_Software_Writeup.md`
- `research/bluelotus_phd_thesis_signal_edge_2026.md`
- `research/BlueLotus_NITE_PEI_Integrated_Thesis.md`
- `research/Bluelotus_Prospective_Event_Intelligence_In_Adaptive_Cognitive_Market_Systems.pdf`
- `research/Bluelotus_phd_thesis_signal_edge_2026.pdf`
- `research/bluelotus_phd_thesis_2026.pdf`
- `reports/BLUELOTUS_V3_LANDMARK_ARCHITECTURE_REPORT_20260620.md`
- `documentation/Institutional_Quant_Process_Pipeline.md`
- `documentation/BlueLotus_V3_Upgrade_Report_Agentic_AI_Linear_Multi_Agency_20260615.md`

## Runtime Notes

This repository is a sanitized source and documentation upload. It does not include live `.env` files, logs, local databases, broker snapshots, generated raw datasets, account identifiers, or order books.

The provided `.env.template` documents expected environment variables. Before running locally, copy it to `.env` in a private checkout and fill in local-only values.

Common local services:

- Ollama/Qwen for local LLM inference.
- MySQL for V3 persistence.
- Moomoo OpenD for read-only market intelligence integrations.

## Safety Boundary

The public package intentionally excludes direct trading automation from the original working tree. Any brokerage execution code, live order levels, account metadata, or portfolio snapshots should remain private.

