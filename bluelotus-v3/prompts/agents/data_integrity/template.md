# Data Integrity Agent — Output Template
## Schema: bluelotus_v3_agent_report_v1.0

Use this as a structural guide. Fill in evidence-specific values.

```json
{
  "schema_version": "bluelotus_v3_agent_report_v1.0",
  "cycle_id": "<from context>",
  "agent_id": "data_integrity",
  "agent_name": "Data Integrity Agent",
  "agent_role": "Check freshness, archive mismatch, source reliability, stale sections, and dataset usability.",
  "model_used": "",
  "input_refs": {},
  "summary": "Data Integrity audit: dataset generated at <timestamp> — <USABLE|DEGRADED|DO-NOT-TRUST> with <N> source(s) stale or missing.",
  "key_findings": [
    "[OPERATOR] freshness_governor verdict: <PASS|FAIL> — <specific finding from operator output>",
    "[DATASET] source_health: <source_name> last seen <N> minutes ago — SLA breach <YES|NO>",
    "[OPERATOR] archive_mismatch: <DETECTED|CLEAR> — <specific hash or ID mismatch if any>"
  ],
  "risk_flags": [
    "P1 <if archive mismatch or dataset > 2h stale>: <specific flag>",
    "P2 <if T1/T2 source null>: <source name> missing this cycle",
    "P3 <minor breach>: <source> freshness within acceptable range but at threshold"
  ],
  "blocked_actions_observed": [
    "freshness_governor blocked cycle if SLA failure threshold exceeded",
    "<any specific blocked action from operator_summary>"
  ],
  "allowed_actions_observed": [
    "Dataset declared usable — council may proceed with CIO manual review",
    "CIO manual verification required for stale sections: <list sections>"
  ],
  "affected_theses": ["No theses in scope for data integrity audit"],
  "affected_assets": [],
  "causal_completeness": "complete",
  "blind_spots": [
    "<specific field missing from source_health that would complete the audit>",
    "<archive hash not available — cannot confirm mismatch>"
  ],
  "confidence": 0.9,
  "recommendation_to_chief_strategist": "MANUAL_REVIEW_REQUIRED",
  "requires_cio_attention": true,
  "manual_execution_required": true,
  "llm_order_generation": false
}
```

## Guidance Notes

- `summary`: Name the dataset timestamp and your overall verdict (USABLE / DEGRADED / DO-NOT-TRUST). One sentence.
- `recommendation_to_chief_strategist`: Use `REVIEW` if dataset is usable with minor warnings. Use `MANUAL_REVIEW_REQUIRED` if any T1 source is stale or archive mismatch detected. Use `CIO_VERIFICATION_REQUIRED` if dataset generation is >2h stale.
- If source_health is empty or null, set `confidence: 0.3` and `causal_completeness: incomplete`.
- **`integrity_flag_reason` check**: Before writing any P1/P2 risk flag about portfolio value below floor, read `portfolio_readonly.integrity_flag_reason`. If it contains `INFO_LOW_MARKET_EXPOSURE_INTENTIONAL`, classify as informational — NOT as P2 or P1. Use `ℹ` (information) icon, not `⚠` (warning).
- **Contradiction prevention**: Never output both "portfolio health stable / no critical breaches" AND "integrity flag set" for the SAME portfolio condition. If `integrity_flag_reason` is `INFO_LOW_MARKET_EXPOSURE_INTENTIONAL`, use "Portfolio health stable — low deployment intentional under CIO posture." instead.
