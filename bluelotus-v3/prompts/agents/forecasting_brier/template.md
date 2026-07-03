# Forecasting Brier Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "forecasting_brier",
  "agent_name": "Forecasting Brier Agent",
  "agent_role": "Observe forecast quality and Brier-related records without altering V2 calibration.",
  "model_used": "",
  "input_refs": {},
  "summary": "Brier desk: Brier continuity is <PRESERVED|DEGRADED|GAP_DETECTED> — <N> claim(s) assessed — overconfidence flag <ACTIVE|CLEAR> — probability discipline <MAINTAINED|CONCERN>.",
  "key_findings": [
    "[BRIER] Brier score history: <trend — improving/stable/degrading> over <N> cycles — current average: <score if available>",
    "[DATASET] research_forecasting: <N> forecast(s) have resolution criteria defined — <N> do not — <specific immeasurable claim if any>",
    "[DATASET] signal_validation: overconfidence flag status: <ACTIVE|CLEAR> — highest confidence claim: <claim at pct> with <N> confirming source(s)"
  ],
  "risk_flags": [
    "P2 OVERCONFIDENCE: confidence > 0.85 on <claim> supported by only <N> source(s) — base rate not cited",
    "P2 MEASURABILITY: <claim excerpt> has no resolution criterion — cannot track Brier continuity",
    "P3 CONTINUITY GAP: brier_summary missing or empty — Brier tracking cannot be performed this cycle"
  ],
  "blocked_actions_observed": [
    "No Brier recalibration allowed — read-only observation mode only",
    "No forecast model changes permitted this cycle"
  ],
  "allowed_actions_observed": [
    "Brier observation log updated — CIO may review forecast quality history",
    "Immeasurable claims flagged for CIO to request resolution criteria from analysts"
  ],
  "affected_theses": ["No direct thesis impact from Brier observation"],
  "affected_assets": [],
  "causal_completeness": "complete",
  "blind_spots": [
    "brier_summary empty — no prior Brier records available for continuity check",
    "research_forecasting resolution criteria not defined — cannot assess calibration quality"
  ],
  "confidence": 0.75,
  "recommendation_to_chief_strategist": "REVIEW",
  "requires_cio_attention": false,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- `requires_cio_attention`: Set `false` if no overconfidence or measurability issues detected. Set `true` if P1 overconfidence flag is active.
- `recommendation`: `REVIEW` as baseline. `RISK_REVIEW_REQUIRED` if overconfidence flags are P1 level. `HOLD` if all forecasts are well-calibrated and Brier is stable.
- If `brier_summary` is empty or null: set `confidence: 0.4`, note gap in blind_spots, set `causal_completeness: incomplete`.
- Do NOT produce directional market calls. Your job is to audit whether others' claims are calibrated.
