# BlueLotus V3 — JSON Only Rule
## Version 1.0 | Injected into every agent user prompt

---

## OUTPUT FORMAT

Return **exactly one JSON object**. No prose before or after the JSON. No markdown code blocks. No explanatory text. The response must be parseable by `json.loads()` as the first and only thing in the output.

---

## SCHEMA: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<string — use cycle_id from your context>",
  "agent_id": "<string — use agent_id from your context>",
  "agent_name": "<string — use agent_name from your context>",
  "agent_role": "<string — one sentence describing this desk>",
  "model_used": "<string — populated by orchestrator, leave empty string>",
  "input_refs": {},
  "summary": "<string — ONE sentence naming your desk's specific lens and finding this cycle>",
  "key_findings": [
    "<string starting with [DATASET], [OPERATOR], [NEWS], [THESIS], [BRIER], or [MEMORY]>",
    "<string>",
    "<string>"
  ],
  "risk_flags": [
    "<string starting with P1, P2, or P3>",
    "<string>",
    "<string>"
  ],
  "blocked_actions_observed": [
    "<string>",
    "<string>"
  ],
  "allowed_actions_observed": [
    "<string>",
    "<string>"
  ],
  "affected_theses": [
    "<string — thesis ID or 'No active theses'>",
    "<string>"
  ],
  "affected_assets": [
    "<string — ticker symbol>",
    "<string>"
  ],
  "causal_completeness": "<complete | partial | incomplete>",
  "blind_spots": [
    "<string — specific missing field or evidence gap>",
    "<string>"
  ],
  "confidence": 0.0,
  "recommendation_to_chief_strategist": "<WAIT|HOLD|REVIEW|MANUAL_REVIEW_REQUIRED|CIO_VERIFICATION_REQUIRED|RISK_REVIEW_REQUIRED|THESIS_REVIEW_REQUIRED|REDUCE_RISK_REVIEW|RAISE_CASH_REVIEW|HEDGE_REVIEW>",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

---

## FIELD RULES

| Field | Rule |
|-------|------|
| `summary` | Exactly ONE sentence. Must name your desk's lens AND the most important finding. |
| `key_findings` | 1–3 items. Each must start with an evidence tag. Strings only — no nested objects. |
| `risk_flags` | 1–3 items. P1 = immediate, P2 = this week, P3 = watch. |
| `blocked_actions_observed` | 0–3 items. Reference specific operator that blocked. |
| `allowed_actions_observed` | 0–3 items. Must include "CIO manual review required". |
| `affected_theses` | 0–3 items. Use configured thesis IDs from thesis_registry if available. |
| `affected_assets` | 0–3 items. Ticker symbols only. |
| `causal_completeness` | Must be exactly: `complete`, `partial`, or `incomplete`. |
| `blind_spots` | 0–3 items. Name the specific missing field, not a vague gap. |
| `confidence` | Float 0.0–1.0. Use 0.5 as baseline; adjust based on evidence quality. |
| `manual_execution_required` | Always `true`. |
| `llm_order_generation` | Always `false`. |

---

## ARRAY LENGTH LIMITS

- Maximum 3 items in `key_findings`
- Maximum 3 items in `risk_flags`
- Maximum 3 items in `blind_spots`
- Maximum 3 items in `affected_assets`

Violating these limits will cause schema validation failure and the report will be rejected by the orchestrator.

---

## COMMON JSON ERRORS TO AVOID

- Do not use trailing commas: `{"a": 1,}` is invalid
- Do not use single quotes: `{'key': 'value'}` is invalid
- Do not include comments inside the JSON output
- Do not use `null` for arrays — use `[]`
- Do not omit required fields — all fields in the schema above are required
