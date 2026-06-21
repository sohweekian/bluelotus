# Thesis Lifecycle Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "thesis_lifecycle",
  "agent_name": "Thesis Lifecycle Agent",
  "agent_role": "Evaluate active thesis lifecycle states from the configured thesis registry.",
  "model_used": "",
  "input_refs": {},
  "summary": "Thesis lifecycle: <N> active thesis(es) evaluated — <thesis_id> is <CONFIRMING|WEAKENING|CONTRADICTED|WATCH> — gold thesis is separate from concentration permission.",
  "key_findings": [
    "[THESIS] <thesis_id>: state is <CONFIRMING|WEAKENING|CONTRADICTED|WATCH> — confirmation criteria met: <list> — contradiction signals: <list or none>",
    "[OPERATOR] thesis_lifecycle verdict: <specific finding> — gold_thesis operator: <finding>",
    "[THESIS] Gold thesis confirmation does NOT unlock concentration add — see portfolio structure desk for add_allowed verdict"
  ],
  "risk_flags": [
    "P1 <if thesis CONTRADICTED>: <thesis_id> contradiction evidence: <specific evidence> — archive review recommended",
    "P2 <if thesis has been WATCH for multiple cycles>: <thesis_id> WATCH for >3 cycles with no confirming evidence — ARCHIVE_REVIEW_NEEDED",
    "P3 <if confirmation evidence is T3/T4 quality>: <thesis_id> confirmation relies on low-trust sources — verify with T1/T2 data"
  ],
  "blocked_actions_observed": [
    "thesis_lifecycle operator blocked thesis from CONFIRMING status — criteria not fully met",
    "<specific block from operator output>"
  ],
  "allowed_actions_observed": [
    "<thesis_id> eligible for CIO review of lifecycle state change — CIO manual judgment required",
    "Archive review of <thesis_id> may be opened — CIO discretion"
  ],
  "affected_theses": [
    "<thesis_id_1>",
    "<thesis_id_2>"
  ],
  "affected_assets": [
    "<ticker most affected by thesis state change>"
  ],
  "causal_completeness": "complete",
  "blind_spots": [
    "thesis_lifecycle state last updated >24h ago — current cycle evidence may not be reflected",
    "<confirmation criterion missing from priority_intelligence>"
  ],
  "confidence": 0.8,
  "recommendation_to_chief_strategist": "THESIS_REVIEW_REQUIRED",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- Always address the gold thesis separately from concentration permission. State explicitly that gold thesis confirmation does not override portfolio structure desk's add_allowed verdict.
- `recommendation`: `THESIS_REVIEW_REQUIRED` as baseline. Escalate to `CIO_VERIFICATION_REQUIRED` if a primary thesis transitions to CONTRADICTED.
- If thesis_registry is empty (no active theses configured), state that explicitly in summary and set `confidence: 0.5`.
- Do NOT invent thesis IDs. Use only IDs present in thesis_registry.
