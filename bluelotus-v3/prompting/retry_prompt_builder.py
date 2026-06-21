"""
BlueLotus V3 — Retry Prompt Builder
=====================================
Generates failure-repair prompts when an agent's response fails
JSON schema validation.

ARCHITECTURE DOCTRINE:
  - A retry uses a SIMPLIFIED prompt, not a repeat of the full prompt.
    Full prompt re-injection is expensive and often fails the same way.
  - The repair prompt includes: (1) the specific validation error,
    (2) the agent's original (broken) response for reference,
    (3) minimal schema reminder, (4) instruction to fix ONLY the error.
  - Maximum 2 retries per agent per cycle (configurable via env).
  - Retry prompts never re-inject the full desk_context — the agent
    already received it; the issue is schema compliance, not evidence.

ANTI-HARDCODE RULE:
  - Max retry count comes from env var LLM_MAX_RETRIES (default 2).
  - Schema error classification is rule-based, not hardcoded strings.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_MAX_RETRIES = 2


def max_retries() -> int:
    env_val = os.getenv("LLM_MAX_RETRIES")
    if env_val and env_val.isdigit():
        return int(env_val)
    return DEFAULT_MAX_RETRIES


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def classify_error(validation_error: str) -> str:
    """
    Classify the validation error type for targeted repair instruction.
    Returns one of: JSON_PARSE_ERROR | MISSING_FIELD | WRONG_TYPE |
                    ARRAY_TOO_LONG | ENUM_VIOLATION | GENERIC_SCHEMA_ERROR
    """
    err = validation_error.lower()
    if "empty_content_response" in err or "empty content" in err:
        return "EMPTY_CONTENT_RESPONSE"
    if "json" in err and ("parse" in err or "decode" in err or "invalid" in err or "not valid" in err):
        return "JSON_PARSE_ERROR"
    if "required" in err and ("missing" in err or "property" in err):
        return "MISSING_FIELD"
    if ("type" in err or "must be" in err) and ("string" in err or "boolean" in err or "number" in err or "array" in err or "object" in err):
        return "WRONG_TYPE"
    if "maxitems" in err or "max items" in err or "too many" in err or "no more than" in err:
        return "ARRAY_TOO_LONG"
    if "enum" in err or "one of" in err:
        return "ENUM_VIOLATION"
    return "GENERIC_SCHEMA_ERROR"


# ---------------------------------------------------------------------------
# Repair instructions per error type
# ---------------------------------------------------------------------------

_REPAIR_INSTRUCTIONS: Dict[str, str] = {
    "EMPTY_CONTENT_RESPONSE": (
        "Minimum content contract: summary must be non-empty and key_findings must contain at least one non-empty item. "
        "Your previous response returned all content fields empty: "
        "summary was blank, key_findings was [], and confidence was 0.5 (the scaffold default). "
        "This means you did not analyse the evidence packet — you returned the template unchanged. "
        "You MUST now produce real analysis. "
        "Populate summary with ONE sentence describing what your desk found. "
        "Populate key_findings with AT LEAST 1 string starting with [DATASET], [OPERATOR], [NEWS], [THESIS], or [BRIER]. "
        "Set confidence to a value other than 0.5 that reflects your actual certainty. "
        "If evidence is genuinely missing, write that in blind_spots and set causal_completeness to incomplete. "
        "Do NOT return empty arrays again."
    ),
    "JSON_PARSE_ERROR": (
        "Your previous response was not valid JSON. "
        "Common causes: trailing commas, single quotes instead of double quotes, "
        "comments inside JSON, or prose text before/after the JSON object. "
        "Return ONLY a single JSON object — no text before or after it."
    ),
    "MISSING_FIELD": (
        "Your previous response was missing a required field. "
        "All fields in the schema are required. "
        "The specific missing field is shown in the error below. "
        "Copy your previous response and ADD the missing field with an appropriate value."
    ),
    "WRONG_TYPE": (
        "Your previous response had a field with the wrong data type. "
        "The specific field and expected type are shown in the error below. "
        "Fix ONLY that field — do not change other fields. "
        "confidence must be a float (e.g., 0.75), not a string. "
        "manual_execution_required and llm_order_generation must be boolean true/false, not strings."
    ),
    "ARRAY_TOO_LONG": (
        "Your previous response had an array with too many items. "
        "Arrays (key_findings, risk_flags, blind_spots, affected_assets) have a MAXIMUM of 3 items each. "
        "Remove items from the array identified in the error below until within the limit."
    ),
    "ENUM_VIOLATION": (
        "Your previous response used an invalid value for an enum field. "
        "recommendation_to_chief_strategist must be exactly one of: "
        "WAIT, HOLD, REVIEW, MANUAL_REVIEW_REQUIRED, CIO_VERIFICATION_REQUIRED, "
        "RISK_REVIEW_REQUIRED, THESIS_REVIEW_REQUIRED, REDUCE_RISK_REVIEW, "
        "RAISE_CASH_REVIEW, HEDGE_REVIEW. "
        "causal_completeness must be exactly one of: complete, partial, incomplete."
    ),
    "GENERIC_SCHEMA_ERROR": (
        "Your previous response did not conform to the required JSON schema. "
        "The specific error is shown below. "
        "Fix ONLY the issue identified — do not restructure the entire response."
    ),
}


# ---------------------------------------------------------------------------
# Public Interface
# ---------------------------------------------------------------------------

def build_retry_system_prompt(
    agent_id: str,
    agent_name: str,
) -> str:
    """
    Build a minimal system prompt for a retry call.
    Much shorter than the original — focuses only on schema compliance.
    """
    return (
        f"You are the {agent_name} inside the BlueLotus V3 Qwen Agent Council. "
        "Your previous response had a JSON schema error. "
        "Your ONLY task now is to fix the error described below and return a valid JSON response. "
        "Do NOT change the content of fields that were correct — fix ONLY the identified error. "
        "Return one compact JSON object only. "
        "manual_execution_required must be true. "
        "llm_order_generation must be false."
    )


def build_retry_user_prompt(
    validation_error: str,
    original_response: str,
    agent_id: str,
    retry_attempt: int,
) -> str:
    """
    Build a targeted repair prompt from the validation error and original response.

    Args:
        validation_error: The schema validation error message
        original_response: The agent's previous (broken) response text
        agent_id: Agent identifier for context
        retry_attempt: Which retry this is (1-based)

    Returns:
        User prompt text for the retry LLM call
    """
    error_type = classify_error(validation_error)
    repair_instruction = _REPAIR_INSTRUCTIONS.get(error_type, _REPAIR_INSTRUCTIONS["GENERIC_SCHEMA_ERROR"])

    if error_type == "EMPTY_CONTENT_RESPONSE":
        original_truncated = original_response[:1800] if len(original_response) > 1800 else original_response
        return (
            f"RETRY ATTEMPT {retry_attempt} — agent_id: {agent_id}\n\n"
            f"ERROR TYPE: {error_type}\n\n"
            f"REPAIR INSTRUCTION: {_REPAIR_INSTRUCTIONS['EMPTY_CONTENT_RESPONSE']}\n\n"
            f"YOUR PREVIOUS RESPONSE (empty — do not copy this):\n{original_truncated}\n\n"
            "Now return a corrected JSON object with real content. "
            "Copy the metadata fields (schema_version, cycle_id, agent_id, agent_name, agent_role, "
            "model_used, input_refs, created_at_sgt) from your previous response unchanged. "
            "Replace summary, key_findings, confidence, causal_completeness, and recommendation "
            "with your actual desk analysis. "
            "Return JSON only. No markdown. No prose outside the JSON object."
        )

    if error_type == "JSON_PARSE_ERROR":
        return (
            f"RETRY ATTEMPT {retry_attempt} -- agent_id: {agent_id}\n\n"
            f"ERROR TYPE: {error_type}\n"
            f"VALIDATION ERROR: {validation_error}\n\n"
            "The previous response was malformed JSON. Do not repair the old text. "
            "Regenerate a fresh valid JSON object using this exact shape. "
            "Keep content concise and desk-specific. No markdown. No prose outside JSON.\n\n"
            '{"schema_version":"bluelotus_v3_agent_report_v1.0","cycle_id":"","agent_id":"",'
            '"agent_name":"","agent_role":"","model_used":"","input_refs":{},"summary":"",'
            '"key_findings":[],"risk_flags":[],"blocked_actions_observed":[],"allowed_actions_observed":[],'
            '"affected_theses":[],"affected_assets":[],"causal_completeness":"partial","blind_spots":[],'
            '"confidence":0.5,"recommendation_to_chief_strategist":"CIO_VERIFICATION_REQUIRED",'
            '"requires_cio_attention":true,"manual_execution_required":true,'
            '"llm_order_generation":false,"created_at_sgt":""}\n\n'
            "Rules: key_findings must contain at least one concise string. "
            "If evidence cannot be reconstructed, use one finding such as "
            "\"[DATASET] Evidence reconstruction unavailable after JSON repair; CIO verification required.\" "
            "risk_flags may be empty if no specific risk can be reconstructed. "
            "manual_execution_required must be true. llm_order_generation must be false."
        )

    # Truncate original response if very long (schema error, not content error)
    original_truncated = original_response[:1800] if len(original_response) > 1800 else original_response

    return (
        f"RETRY ATTEMPT {retry_attempt} — agent_id: {agent_id}\n\n"
        f"ERROR TYPE: {error_type}\n"
        f"VALIDATION ERROR: {validation_error}\n\n"
        f"REPAIR INSTRUCTION: {repair_instruction}\n\n"
        f"YOUR PREVIOUS RESPONSE (broken):\n{original_truncated}\n\n"
        "Fix the error and return the corrected JSON object. "
        "Do NOT add explanatory text. Return the JSON object only."
    )


def should_retry(
    validation_error: str,
    retry_count: int,
    agent_id: str,
) -> bool:
    """
    Determine if a retry should be attempted.

    Returns False if:
    - retry_count has reached max_retries()
    - The error is not retryable (e.g., agent returned empty response)
    """
    if retry_count >= max_retries():
        return False

    # Semantic empty content is retryable — distinguish from model-down empty response
    err_lower = validation_error.lower()
    if "empty_content_response" in err_lower:
        return True

    # Empty response or None — not retryable (model may be down)
    if "empty" in err_lower or "none" in err_lower or "timeout" in err_lower:
        return False

    return True


def build_retry_record(
    retry_attempt: int,
    error_type: str,
    validation_error: str,
    succeeded: bool,
) -> Dict[str, Any]:
    """Build a structured log record for a retry attempt."""
    return {
        "retry_attempt": retry_attempt,
        "error_type": error_type,
        "validation_error": validation_error[:200],  # cap at 200 chars for log
        "succeeded": succeeded,
    }
