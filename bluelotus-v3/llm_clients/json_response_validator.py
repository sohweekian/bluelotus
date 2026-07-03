from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .config_loader import ConfigError, env_required, load_dotenv, resolve_project_path
from .prompt_guard import forbidden_term_matches, load_safety_policy


class ResponseValidationError(ValueError):
    pass


def validate_json_response(
    response_text: str,
    schema_filename: str,
    require_json: bool = True,
    save_failed: bool = True,
) -> Dict[str, Any]:
    try:
        parsed = json.loads(response_text)
    except Exception as exc:
        if save_failed:
            save_failed_response(response_text, "malformed_json")
        if require_json:
            raise ResponseValidationError(f"Model response is not valid JSON: {exc}") from exc
        return {"raw_text": response_text}

    schema = load_schema(schema_filename)
    parsed = repair_contract_fields(parsed, schema, schema_filename)
    errors = validate_against_schema(parsed, schema)
    policy = load_safety_policy()
    forbidden = forbidden_term_matches([json.dumps(parsed, ensure_ascii=False)], policy.get("forbidden_terms", []))
    errors.extend(forbidden)
    if errors:
        if save_failed:
            save_failed_response(response_text, "schema_or_safety_failure")
        raise ResponseValidationError("; ".join(errors))
    return parsed


def repair_contract_fields(parsed: Dict[str, Any], schema: Dict[str, Any], schema_filename: str) -> Dict[str, Any]:
    repaired = dict(parsed)
    properties = schema.get("properties", {})
    for key, rules in properties.items():
        if isinstance(rules, dict) and "const" in rules:
            repaired[key] = rules["const"]

    schema_name = schema_filename
    if schema_filename in os_environ_keys():
        schema_name = env_required(schema_filename)
    normalized_schema_name = str(schema_name).replace("\\", "/").lower()
    if normalized_schema_name.endswith("agent_report.schema.json"):
        if "recommendation_to_chief_strategist" not in repaired and "recommendation" in repaired:
            repaired["recommendation_to_chief_strategist"] = repaired.get("recommendation")
        for key in [
            "key_findings",
            "risk_flags",
            "blocked_actions_observed",
            "allowed_actions_observed",
            "affected_theses",
            "affected_assets",
            "blind_spots",
        ]:
            if key not in repaired or not isinstance(repaired.get(key), list):
                repaired[key] = []
            else:
                repaired[key] = [json.dumps(item, ensure_ascii=False) if isinstance(item, (dict, list)) else str(item) for item in repaired[key]][:3]
        repaired.setdefault("input_refs", {})
        repaired.setdefault("cycle_id", "")
        repaired.setdefault("agent_id", "")
        repaired.setdefault("agent_name", "")
        repaired.setdefault("agent_role", "")
        repaired.setdefault("model_used", "")
        if repaired.get("causal_completeness") not in {"complete", "partial", "incomplete"}:
            repaired["causal_completeness"] = "partial"
        rec = str(repaired.get("recommendation_to_chief_strategist", "WAIT")).upper()
        rec_enum = set(properties.get("recommendation_to_chief_strategist", {}).get("enum", []))
        if rec_enum and rec not in rec_enum:
            rec = "CIO_VERIFICATION_REQUIRED"
        repaired["recommendation_to_chief_strategist"] = rec
        repaired.setdefault("requires_cio_attention", rec not in {"WAIT", "HOLD"})
        repaired.setdefault("confidence", 0.5)
        repaired.setdefault("created_at_sgt", "")
    return repaired


def load_schema(schema_filename: str) -> Dict[str, Any]:
    load_dotenv()
    configured = schema_filename
    if schema_filename in os_environ_keys():
        configured = env_required(schema_filename)
    path = resolve_project_path(configured)
    if not path.exists():
        raise ConfigError(f"Schema file not found: {schema_filename}")
    return json.loads(path.read_text(encoding="utf-8"))


def os_environ_keys() -> set[str]:
    import os

    return set(os.environ.keys())


def validate_against_schema(value: Dict[str, Any], schema: Dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if schema.get("type") == "object" and not isinstance(value, dict):
        return ["Response must be a JSON object."]
    for key in schema.get("required", []):
        if key not in value:
            errors.append(f"Missing required key: {key}")
    properties = schema.get("properties", {})
    for key, rules in properties.items():
        if key not in value:
            continue
        current = value[key]
        expected_type = rules.get("type")
        if expected_type and not type_matches(current, expected_type):
            errors.append(f"Key {key} must be {expected_type}.")
        if "const" in rules and current != rules["const"]:
            errors.append(f"Key {key} must equal configured constant.")
        if "enum" in rules and current not in rules["enum"]:
            errors.append(f"Key {key} must be one of the configured enum values.")
        if expected_type == "array" and isinstance(current, list):
            max_items = rules.get("maxItems")
            if isinstance(max_items, int) and len(current) > max_items:
                errors.append(f"Key {key} must contain no more than {max_items} items.")
            item_rules = rules.get("items")
            if isinstance(item_rules, dict) and item_rules.get("type"):
                for index, item in enumerate(current):
                    if not type_matches(item, str(item_rules["type"])):
                        errors.append(f"Key {key}[{index}] must be {item_rules['type']}.")
    return errors


def type_matches(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def save_failed_response(response_text: str, reason: str) -> Path:
    out_dir = resolve_project_path(env_required("LLM_OUTPUT_DIR"))
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"failed_response_{reason}_{stamp}.txt"
    path.write_text(response_text, encoding="utf-8")
    return path
