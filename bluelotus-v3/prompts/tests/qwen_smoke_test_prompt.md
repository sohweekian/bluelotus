/no_think

Return the final JSON object only. The first output character must be `{`.

Summarize the following operator result:

macro_regime = RISK_OFF_WATCH
blocked_actions = ADD_HIGH_BETA_RISK
allowed_actions = WAIT, HOLD, REVIEW

Return JSON only. Do not include markdown, comments, explanations, or thinking text.

Use exactly this JSON shape:

{
  "schema_version": "bluelotus_llm_response_v1.0",
  "model_role": "{{MODEL_ROLE}}",
  "summary": "",
  "key_findings": [],
  "risk_flags": [],
  "recommended_cio_action": "WAIT",
  "manual_execution_required": true,
  "llm_order_generation": false
}

The recommended_cio_action value must be one of:
WAIT, HOLD, REVIEW, MANUAL_REVIEW_REQUIRED, CIO_VERIFICATION_REQUIRED, RISK_REVIEW_REQUIRED, THESIS_REVIEW_REQUIRED.
