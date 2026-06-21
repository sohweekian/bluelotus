# Chief Strategist — Synthesis Role
## agent_id: chief_strategist | role: synthesis_engine (NOT an LLM agent)
## Implementation: chief_strategist/synthesis_engine.py

---

## ROLE DEFINITION

The Chief Strategist is the **deterministic synthesis engine** that runs after all 9 specialist agents have completed their cycle. It is NOT an LLM agent. It reads all agent reports, the disagreement log, and the operator verdict pack, then produces the CIO briefing.

This document defines:
1. What the synthesis engine must extract from agent reports
2. How it must resolve disagreements
3. What the final CIO briefing must contain
4. What language is appropriate for synthesis

---

## SYNTHESIS INPUTS (in order of authority)

| Priority | Input | Purpose |
|----------|-------|---------|
| 1 | `operator_verdict_pack` | Deterministic hard constraints — never overridden |
| 2 | `disagreement_log` | Resolved vs unresolved conflicts between desks |
| 3 | Agent reports (all 9 or more) | Evidence-based findings from specialist desks |
| 4 | Prior briefings (if injected via memory) | Trend context for CIO action trajectory |

---

## EXTRACTION RULES — WHAT TO READ FROM EACH AGENT

### Data Integrity Agent
- Extract: `recommendation_to_chief_strategist`, `risk_flags[P1]` → if REVIEW/CIO_VERIFICATION: add DATASET_WARNING to CIO briefing header
- If usability verdict is DO-NOT-TRUST: mark entire cycle as DEGRADED in briefing

### Macro Strategist Agent
- Extract: regime label from summary, `recommendation_to_chief_strategist`
- This forms the **base regime** for the briefing. Never overwrite with narrative.

### Portfolio Structure Agent
- Extract: `key_findings` (HHI, largest position, PNL conflicts), `blocked_actions_observed`
- PNL integrity conflicts must appear in CIO briefing as dedicated WARNING item

### Catalyst Intelligence Agent
- Extract: ACTIVE/IMMINENT catalyst alerts into briefing "Catalyst Watch" section

### Thesis Lifecycle Agent
- Extract: lifecycle state per thesis into briefing "Thesis Status" section

### Risk Challenger Agent
- Extract: TOP objection from `key_findings[0]` into briefing "Risk Objection" section
- This is ALWAYS featured prominently — never buried

### Forecasting Brier Agent
- Extract: overconfidence flag if active; Brier continuity status

### Sector Specialist Agent
- Extract: PRICE_ACTION_ONLY and CONTAMINATION flags into briefing

### Sentiment Narrative Agent
- Extract: clean/dirty tape verdict per portfolio position

---

## DISAGREEMENT RESOLUTION

The disagreement_log flags cross-desk conflicts. Resolution rules:
1. **Operator conflict (operator says BLOCKED; agent says ALLOWED):** Operator wins. Flag it in briefing.
2. **Regime conflict (macro says RISK OFF; sentiment says COMPLACENT):** Include both — note the tension.
3. **Thesis conflict (lifecycle says CONFIRMING; risk_challenger objects):** Feature both — escalate for CIO judgment.
4. **Unresolved disagreements:** Listed in briefing under "Unresolved Council Conflicts."

---

## CIO BRIEFING STRUCTURE REQUIREMENTS

The `chief_strategist_briefing.json` must contain:

```
1. cycle_id, generated_at_sgt
2. regime_consensus: {label, score, confidence, source: "macro_strategist"}
3. cio_action: {recommendation, authority: "CIO_ONLY_MANUAL", orders_generated: 0}
4. dataset_integrity: {status, degraded_sources if any}
5. portfolio_alerts: {hhi_equity_only, largest_position, pnl_integrity_conflicts}
6. catalyst_watch: [{ticker, event, alert_flag, days_until}]
7. thesis_status: [{thesis_id, state, key_evidence}]
8. risk_objection: {top_objection, challenger_confidence}
9. sector_posture: [{sector, direction, evidence_quality}]
10. sentiment_tape: {overall_tone, clean_positions, dirty_positions}
11. unresolved_conflicts: [list of unresolved disagreements]
12. governance: {manual_execution_required: true, llm_order_generation: false, orders_generated: 0}
```

---

## SYNTHESIS LANGUAGE STANDARDS

Use CIO-briefing language:
- **consensus, divergence, confidence level, CIO attention required, manual judgment**
- **regime, posture, risk permission, catalyst window, thesis state**
- **APPROVED FOR CIO REVIEW, BLOCKED, REQUIRES MANUAL VERIFICATION**
- Never: "buy," "sell," "execute," "enter," "exit," "order," "trade"

---

## GOVERNANCE INVARIANTS (always true in every briefing)

```json
"governance": {
  "manual_execution_required": true,
  "llm_order_generation": false,
  "orders_generated_by_pipeline": 0,
  "order_routing_enabled": false,
  "execution_authority": "CIO_ONLY_MANUAL"
}
```

These fields must appear verbatim. They are contract fields checked by regression tests.
