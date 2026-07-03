"""
BlueLotus V3 — NITE-PEI Engine
================================
News Impact and Thesis Engine for PEI Probability Updating.

Converts incoming news events into quantified Bayesian thesis probability
updates, kill-condition state transitions, CKRI risk index, and Kelly-NITE
advisory position sizing.

Architecture: 7 sub-engines, 20-step deterministic workflow.
Thesis source: research/BlueLotus_NITE_PEI_Integrated_Thesis.md
Work order:    research/WORKORDER_NITEPEI_Integrated_Thesis_20260621.txt

GOVERNANCE:
  CIO_ONLY_MANUAL: TRUE
  ORDER_ROUTING_ENABLED: FALSE
  LLM_ORDER_GENERATION: FALSE
  MANUAL_EXECUTION_REQUIRED: TRUE
"""

from __future__ import annotations

NITE_PEI_VERSION = "nite_pei_v1.0"
