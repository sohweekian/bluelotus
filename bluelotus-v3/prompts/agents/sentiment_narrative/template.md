# Sentiment Narrative Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "sentiment_narrative",
  "agent_name": "Sentiment Narrative Agent",
  "agent_role": "Interpret market narrative, risk appetite, panic or euphoria tone, and narrative rotation.",
  "model_used": "",
  "input_refs": {},
  "summary": "Sentiment desk: overall market tone is <FEARFUL|COMPLACENT|EUPHORIC|MIXED> — <TICKER> narrative is <CLEAN|NOISY|DIRTY> tape — narrative rotation detected in <sector if any>.",
  "key_findings": [
    "[DATASET] ticker_sentiment: <TICKER> sentiment=<score>, dirty_headlines=<N>, dominant source tier=<T1|T2|T3|T4> — tape assessed as <CLEAN|NOISY|DIRTY>",
    "[NEWS] live_news tone: <specific characterization of current news cycle tone> — <NEW information|RECIRCULATION|AMPLIFICATION> of prior headlines",
    "[OPERATOR] sentiment_hygiene_gate or macro_regime: <specific sentiment-relevant operator finding>"
  ],
  "risk_flags": [
    "P1 DIRTY TAPE: <TICKER> narrative driven by T3/T4 sources (<N> dirty headlines) — sentiment diverges from confirmed fundamentals",
    "P2 OVER-AMPLIFICATION: <theme or sector> has <N> recirculating headlines — noise elevated, no new T1/T2 catalyst",
    "P3 TONE CONTRADICTION: market tone is <FEARFUL|EUPHORIC> while fundamentals indicate <opposite> — watch for reversal"
  ],
  "blocked_actions_observed": [
    "Dirty tape in <TICKER> means narrative cannot be used to justify thesis confirmation — CIO must verify with T1/T2 evidence",
    "<any sentiment-related block from operator output>"
  ],
  "allowed_actions_observed": [
    "Clean tape confirmed for <TICKER> — sentiment supported by T1/T2 evidence — CIO may use this in thesis review",
    "<allowed action from sentiment_hygiene_gate operator>"
  ],
  "affected_theses": ["Narrative quality affects <thesis_id> — see thesis lifecycle desk for lifecycle impact"],
  "affected_assets": [
    "<TICKER with dirtiest tape>",
    "<TICKER with cleanest tape>",
    "<TICKER with over-amplified narrative>"
  ],
  "causal_completeness": "complete",
  "blind_spots": [
    "ticker_sentiment missing for <TICKER> — cannot assess narrative quality for this position",
    "live_news source tier not available — cannot separate T1/T2 from T3/T4 in news cycle"
  ],
  "confidence": 0.7,
  "recommendation_to_chief_strategist": "REVIEW",
  "requires_cio_attention": false,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- `requires_cio_attention`: `true` only if DIRTY TAPE detected for a portfolio position, or if tone contradiction is extreme (P1 level).
- `recommendation`: `REVIEW` as baseline. `RISK_REVIEW_REQUIRED` if majority of portfolio positions have dirty tape. `HOLD` if tape is clean and complacent (no new signal).
- Dirty tape is a data quality issue for narrative, not a fundamental call. Don't use dirty tape sentiment to make fundamental recommendations.
- `confidence`: Reduce to 0.5 if ticker_sentiment is mostly null or if live_news is unavailable.
