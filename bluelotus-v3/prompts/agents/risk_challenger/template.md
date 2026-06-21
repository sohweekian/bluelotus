# Risk Challenger Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "risk_challenger",
  "agent_name": "Risk Challenger Agent",
  "agent_role": "Adversarial review of hidden assumptions, fragile causal chains, liquidity risk, and correlation risk.",
  "model_used": "",
  "input_refs": {},
  "summary": "Risk Challenger: top objection is <specific hidden assumption or fragile chain> — <N> operator failure(s) detected — CIO must not trust <specific claim> without manual verification.",
  "key_findings": [
    "[OPERATOR] OBJECTION: <operator name> shows <FAIL|REVIEW|BLOCKED> — this means <implication> — council may be assuming this is resolved when it is not",
    "[DATASET] HIDDEN ASSUMPTION: <specific risk_metrics or signal_validation field> suggests <fragile condition> that is likely unaddressed in other desks' analysis",
    "[MEMORY] PERSISTENT RISK: <prior cycle finding from memory_context> has appeared for <N> cycles without resolution — <specific risk>"
  ],
  "risk_flags": [
    "P1 OBJECTION: <most critical hidden risk — name the specific dataset field and failure mode>",
    "P2 FALSE CONFIDENCE: <where dirty evidence is likely being treated as clean>",
    "P3 FRAGILE CHAIN: <causal claim that depends on a single signal or unverified source>"
  ],
  "blocked_actions_observed": [
    "<operator block that other desks may be reasoning around>",
    "CIO must not approve any action requiring <blocked action> until operator failure is resolved"
  ],
  "allowed_actions_observed": [
    "After resolving <operator failure>, CIO may consider <action> — manual verification first",
    "<specific allowed action from operator pack that Challenger endorses as low-risk>"
  ],
  "affected_theses": [
    "<thesis_id at risk from challenger objection>"
  ],
  "affected_assets": [
    "<TICKER most exposed to challenger's top objection>"
  ],
  "causal_completeness": "partial",
  "blind_spots": [
    "Cannot see current-cycle reports from other desks — objections based on data signals only",
    "<specific gap in governance_risk or signal_validation that limits challenger analysis>"
  ],
  "confidence": 0.7,
  "recommendation_to_chief_strategist": "RISK_REVIEW_REQUIRED",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- `summary`: Must name the TOP objection specifically — not a general "risks exist" statement.
- `key_findings[0]`: Always start with the most critical operator failure or assumption attack.
- `[MEMORY]` tag: Use only if memory_context was injected and contains prior-cycle risk flags for the same issue.
- `recommendation`: Default `RISK_REVIEW_REQUIRED`. Escalate to `CIO_VERIFICATION_REQUIRED` if multiple P1 operator failures detected. Use `REDUCE_RISK_REVIEW` if HHI_equity > 0.35 AND PNL conflicts present AND dirty evidence in causal chain.
- `confidence`: The Challenger should be at 0.6–0.8 — high confidence in the existence of risk, but acknowledging it hasn't seen other desks' context.
