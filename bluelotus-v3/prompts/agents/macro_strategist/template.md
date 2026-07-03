# Macro Strategist Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "macro_strategist",
  "agent_name": "Macro Strategist Agent",
  "agent_role": "Interpret macro regime, cross-market stress, sector breadth, and high-beta permission.",
  "model_used": "",
  "input_refs": {},
  "summary": "Macro desk: regime is <RISK ON|MILD RISK ON|NEUTRAL|MILD RISK OFF|RISK OFF> (score <N>) — primary driver is <VIX|yields|dollar|breadth|credit> — high-beta permission is <OPEN|RESTRICTED|CLOSED>.",
  "key_findings": [
    "[OPERATOR] macro_regime verdict: <regime label> with score <N> — VIX at <level>, SPY breadth <pct>%",
    "[DATASET] cross_market_confirmation: <primary cross-asset signal — e.g., UUP rising + GLD rising = risk-off confirmed>",
    "[DATASET] treasury_yields: 10Y at <pct>%, 2Y at <pct>% — curve <normal|flat|inverted> — real rate proxy <positive|negative>"
  ],
  "risk_flags": [
    "P1 <if VIX > 30 or credit spread spike>: <specific systemic risk>",
    "P2 <if single-signal regime without cross-asset confirmation>: Regime read depends on <signal> only — confirmation missing",
    "P3 <if macro event within 7 days>: <event name> on <date> — potential regime catalyst"
  ],
  "blocked_actions_observed": [
    "macro_regime operator blocked high-beta adds in RISK OFF regime",
    "<any specific blocked action from operator output>"
  ],
  "allowed_actions_observed": [
    "Defensive positioning (VXX, VIXY, TLT) consistent with current regime — CIO manual review required",
    "<any allowed action from operator output>"
  ],
  "affected_theses": ["No theses in scope for macro desk — see thesis lifecycle desk"],
  "affected_assets": [
    "VXX", "VIXY", "SPY", "QQQ", "UUP", "GLD"
  ],
  "causal_completeness": "complete",
  "blind_spots": [
    "<specific cross-market signal missing from cross_market_confirmation>",
    "<central bank communication not in macro_event_risks>"
  ],
  "confidence": 0.75,
  "recommendation_to_chief_strategist": "WAIT",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- `summary`: Must name the regime label, score, primary driver, and high-beta permission status. One sentence.
- `recommendation`: Use `WAIT` in confirmed RISK OFF. `HOLD` in neutral. `REVIEW` when regime conflicted. `RISK_REVIEW_REQUIRED` when VIX spikes or cross-asset breaks.
- `affected_assets`: List macro transmission tickers only (ETFs, indices) — not individual portfolio names unless they are macro transmission channels.
- `confidence`: Reduce if cross_market_confirmation is null or if only one regime signal present. 0.5 = single-signal, 0.85 = four-signal confirmation.
