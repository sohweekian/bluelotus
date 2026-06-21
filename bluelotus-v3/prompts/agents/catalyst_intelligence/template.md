# Catalyst Intelligence Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "catalyst_intelligence",
  "agent_name": "Catalyst Intelligence Agent",
  "agent_role": "Interpret catalyst calendar, live news brief, ECE themes, portfolio catalysts, and urgent events.",
  "model_used": "",
  "input_refs": {},
  "summary": "Catalyst desk: <N> active catalyst(s) this cycle — top priority is <event name> for <TICKER> (alert_flag: <ACTIVE|IMMINENT>) — live news <confirms|contradicts|no impact on> catalyst thesis.",
  "key_findings": [
    "[DATASET] catalyst_calendar: <TICKER> earnings on <date> — days_until=<N>, alert_flag=<flag>, confirmed=<true|false>",
    "[NEWS] live_news: <headline excerpt> — assessed as <confirmed catalyst|commentary|stale|unrelated> for <TICKER|thesis>",
    "[OPERATOR] catalyst_intelligence verdict: <specific finding from operator output>"
  ],
  "risk_flags": [
    "P1 <if ACTIVE catalyst today>: <TICKER> <event type> is ACTIVE today — CIO awareness required",
    "P2 <if IMMINENT within 3 days>: <event> for <TICKER> in <N> days — thesis <impact>",
    "P3 <if catalyst date may slip>: <event> date is estimated — confirm with <source>"
  ],
  "blocked_actions_observed": [
    "<any operator block related to catalyst window>",
    "No new position adds recommended during active catalyst window — CIO discretion"
  ],
  "allowed_actions_observed": [
    "Post-catalyst review window opens after <date> — CIO manual decision point",
    "<allowed action from catalyst_intelligence operator>"
  ],
  "affected_theses": [
    "<thesis_id or name if available>",
    "<thesis affected by catalyst>"
  ],
  "affected_assets": [
    "<TICKER with active catalyst>",
    "<TICKER with IMMINENT catalyst>"
  ],
  "causal_completeness": "complete",
  "blind_spots": [
    "<catalyst date unconfirmed — Finnhub preliminary estimate only>",
    "<live_news contains relevant headline but source tier is T3 — lower confidence>"
  ],
  "confidence": 0.8,
  "recommendation_to_chief_strategist": "MANUAL_REVIEW_REQUIRED",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- Alert flag priority: ACTIVE > IMMINENT > UPCOMING > FUTURE > PAST
- A live news item qualifies as `[NEWS]` only if it is in your live_news context — do not invent headlines.
- `recommendation`: Use `CIO_VERIFICATION_REQUIRED` for ACTIVE earnings. `MANUAL_REVIEW_REQUIRED` for IMMINENT. `REVIEW` for UPCOMING. `HOLD` if no active catalysts.
- Stale catalysts (PAST, no post-event data) belong in `blind_spots`, not `key_findings`.
