# Sector Specialist Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "sector_specialist",
  "agent_name": "Sector Specialist Agent",
  "agent_role": "Evaluate configured sector posture and identify sector-level risk or opportunity.",
  "model_used": "",
  "input_refs": {},
  "summary": "Sector desk: strongest clean evidence in <sector name> — <sector name> shows PRICE_ACTION_ONLY — <sector name> ECE contamination detected — CIO review recommended for <sector>.",
  "key_findings": [
    "[DATASET] ECE: <theme name> sector direction=<RISK ON|RISK OFF|WATCH|NEUTRAL>, basket_move=<pct or N/A>, evidence_tier=<CONFIRMED|PRICE_ACTION_ONLY|CONTAMINATED>",
    "[DATASET] tech_pub_signals or capital_flow: <specific sector signal with source tier>",
    "[OPERATOR] macro_regime or catalyst_intelligence: <specific operator finding relevant to sector posture>"
  ],
  "risk_flags": [
    "P1 CONTAMINATION: <sector name> ECE row <theme> cites <wrong sector> headline as evidence — causal mapping is dirty",
    "P2 PRICE_ACTION_ONLY: <sector name> shows basket move of <pct>% with no clean T1/T2 catalyst identified",
    "P3 CROWDING: <sector name> has <N> ECE rows all pointing <direction> without independent confirmation"
  ],
  "blocked_actions_observed": [
    "concentration_risk operator blocks additional <sector> adds — cluster at limit",
    "<sector> ECE contamination makes causal chain unreliable — CIO should not act on contaminated thesis"
  ],
  "allowed_actions_observed": [
    "<sector> shows confirmed RISK ON with clean T1/T2 catalyst — CIO may review for manual action",
    "Deconcentration of <sector> cluster — CIO manual review required"
  ],
  "affected_theses": [
    "<thesis_id if mapped to sector ECE theme>"
  ],
  "affected_assets": [
    "<TICKER in sector with PRICE_ACTION_ONLY flag>",
    "<TICKER in contaminated ECE row>",
    "<TICKER in strongest clean sector>"
  ],
  "causal_completeness": "partial",
  "blind_spots": [
    "event_correlations_all empty or truncated — cannot assess full sector posture",
    "<sector name> has no ECE rows this cycle — cannot assess sector direction"
  ],
  "confidence": 0.7,
  "recommendation_to_chief_strategist": "REVIEW",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- `PRICE_ACTION_ONLY` flag: Applied when basket_move shows movement but no named catalyst or T1/T2 news source is cited in the ECE row. Always a risk flag.
- `CONTAMINATED` flag: Applied when the ECE "why" field (evidence) cites a ticker or headline from a different sector than the theme's primary sector. Always a P1 flag.
- `recommendation`: `REVIEW` as baseline. `RISK_REVIEW_REQUIRED` if contamination in a sector with active portfolio positions. `MANUAL_REVIEW_REQUIRED` if clean catalyst present in a portfolio sector.
- `causal_completeness`: Set `partial` if any ECE row is PRICE_ACTION_ONLY or CONTAMINATED. Set `complete` only if all cited rows have clean T1/T2 evidence.
