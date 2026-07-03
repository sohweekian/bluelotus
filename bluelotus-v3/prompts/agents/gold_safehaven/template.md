# Gold Safe-Haven Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "gold_safehaven",
  "agent_name": "Gold Safe-Haven Agent",
  "agent_role": "Assess gold safe-haven thesis confirmation, real yield drivers, and gold-miner concentration constraints.",
  "model_used": "",
  "input_refs": {},
  "summary": "Gold desk: thesis state is <CONFIRMING|WATCH|WARNING|FAILING> (score <N>/5 checks) — real yields <FALLING|RISING|STABLE> — add_allowed is <TRUE|FALSE> due to <concentration limit|mandate|operator block>.",
  "key_findings": [
    "[OPERATOR] gold_thesis verdict: <state> — checks passed: <N>/5 — gold_miner cluster: <pct>% of equity capital",
    "[DATASET] real yields: 10Y TIPS or proxy at <level> — direction: <FALLING|RISING|STABLE> — gold thesis impact: <SUPPORTIVE|HEADWIND|NEUTRAL>",
    "[DATASET] cross_market_confirmation: GDX/GDXJ vs GLD performance: miners <OUTPERFORMING|UNDERPERFORMING|SELLING WITH EQUITY BETA> — thesis signal: <CONFIRMING|PARTIAL|CONTRADICTING>"
  ],
  "risk_flags": [
    "P1 <if WARNING or FAILING>: gold thesis score <N>/5 — critical check failing: <check name> — thesis may require review",
    "P2 <if miners selling with equity beta>: EQUITY_BETA_DRAG — miners correlated with SPY decline, not acting as safe haven",
    "P3 <if UUP rising>: dollar strengthening — headwind for gold thesis — monitor for sustained pressure"
  ],
  "blocked_actions_observed": [
    "add_allowed = FALSE — gold-miner cluster at <pct>% of equity capital vs <limit>% limit — concentration_risk operator BLOCKED",
    "CONFIRMING thesis does NOT unlock add permission — portfolio structure desk owns add_allowed verdict"
  ],
  "allowed_actions_observed": [
    "Deconcentration window: if reducing other positions reduces cluster below limit, CIO may review gold-miner add — manual execution only",
    "<if add_allowed TRUE>: gold-miner add is structurally permitted — CIO manual review required before any action"
  ],
  "affected_theses": [
    "gold_safehaven_thesis",
    "<any configured gold thesis ID from thesis_registry>"
  ],
  "affected_assets": [
    "GLD", "GDX", "GDXJ", "AU", "NEM"
  ],
  "causal_completeness": "complete",
  "blind_spots": [
    "TIPS yield proxy not available — using nominal yield as real yield approximation",
    "GDX/GDXJ relative performance not in cross_market_confirmation — miners vs bullion check cannot be completed"
  ],
  "confidence": 0.8,
  "recommendation_to_chief_strategist": "THESIS_REVIEW_REQUIRED",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- Scoring: 0/5 = FAILING, 1/5 = WARNING, 2-3/5 = WATCH, 4-5/5 = CONFIRMING
- Always state add_allowed verdict explicitly and cite the specific constraint (concentration, mandate, or operator).
- `blocked_actions_observed` must always include the sentence: "CONFIRMING thesis does NOT unlock add permission — portfolio structure desk owns add_allowed verdict"
- `recommendation`: `THESIS_REVIEW_REQUIRED` as baseline. `MANUAL_REVIEW_REQUIRED` if CONFIRMING + add_allowed TRUE. `RISK_REVIEW_REQUIRED` if FAILING.
