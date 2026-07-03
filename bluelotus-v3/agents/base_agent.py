from __future__ import annotations

import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from zoneinfo import ZoneInfo

import yaml

from llm_clients.config_loader import env_bool, env_int, load_dotenv, resolve_project_path
from llm_clients.ollama_client import chat_with_model
from prompting.context_builder import build_desk_context
from prompting.memory_retriever import retrieve_memory
from prompting.prompt_compiler import compile_prompts
from prompting.retry_prompt_builder import (
    build_retry_record,
    build_retry_system_prompt,
    build_retry_user_prompt,
    classify_error,
    should_retry,
)


class BaseAgent:
    def __init__(self, agent_config: Dict[str, Any]) -> None:
        self.config = agent_config

    @property
    def agent_id(self) -> str:
        return str(self.config["agent_id"])

    @property
    def display_name(self) -> str:
        return str(self.config["display_name"])

    def run(self, cycle_context: Dict[str, Any]) -> Dict[str, Any]:
        load_dotenv()
        if self.use_new_prompt_architecture():
            return self.run_new_prompt_architecture(cycle_context)
        return self.run_legacy_prompt_path(cycle_context)

    def use_new_prompt_architecture(self) -> bool:
        if not env_bool("USE_NEW_PROMPT_ARCH", False):
            return False
        test_agent = os.getenv("PROMPT_ARCH_TEST_AGENT", "").strip()
        return not test_agent or test_agent == self.agent_id

    def run_legacy_prompt_path(self, cycle_context: Dict[str, Any]) -> Dict[str, Any]:
        model_role = str(self.config["model_role"])
        result = chat_with_model(
            model_role=model_role,
            system_prompt=self.system_prompt(),
            user_prompt=self.user_prompt(cycle_context),
            require_json=True,
            schema_env="AGENT_REPORT_SCHEMA_PATH",
        )
        retry_records = []
        retry_count = 0
        # Semantic content gate: if model returned valid JSON but all content fields
        # are at scaffold defaults, synthesise an EMPTY_CONTENT_RESPONSE error so
        # the retry loop fires. qwen3:4b tends to return the template verbatim.
        if result.get("ok") and isinstance(result.get("parsed"), dict):
            _p = result["parsed"]
            if semantic_content_error(_p):
                result = {
                    "ok": False,
                    "error": (
                        "EMPTY_CONTENT_RESPONSE: agent returned scaffold defaults only — "
                        "summary empty, key_findings=[], confidence=0.5. "
                        "Model must populate findings from evidence packet."
                    ),
                    "response_text": json.dumps(_p),
                }
        while not result.get("ok") and self.retry_allowed(str(result.get("error", "")), retry_count):
            retry_count += 1
            failed_text = str(result.get("response_text") or result.get("error") or "")
            self.write_failed_attempt(cycle_context, retry_count, failed_text)
            error_type = classify_error(str(result.get("error", "")))
            retry_system_prompt = build_retry_system_prompt(self.agent_id, self.display_name)
            retry_user_prompt = build_retry_user_prompt(
                str(result.get("error", "")),
                failed_text,
                self.agent_id,
                retry_count,
            )
            result = chat_with_model(
                model_role=model_role,
                system_prompt=retry_system_prompt,
                user_prompt=retry_user_prompt,
                require_json=True,
                schema_env="AGENT_REPORT_SCHEMA_PATH",
            )
            # Re-apply semantic content gate on retry responses too
            if result.get("ok") and isinstance(result.get("parsed"), dict):
                _p = result["parsed"]
                if semantic_content_error(_p):
                    result = {
                        "ok": False,
                        "error": (
                            "EMPTY_CONTENT_RESPONSE: retry also returned scaffold defaults — "
                            "summary empty, key_findings=[], confidence=0.5."
                        ),
                        "response_text": json.dumps(_p),
                    }
            retry_records.append(
                build_retry_record(
                    retry_count,
                    error_type,
                    str(result.get("error", "")) if not result.get("ok") else "",
                    bool(result.get("ok")),
                )
            )

        if retry_records:
            self.write_retry_record(cycle_context, retry_records)

        if not result.get("ok"):
            raise RuntimeError(str(result.get("error", "Agent LLM call failed.")))
        report = self.finalize_report(result["parsed"], cycle_context)
        report["prompt_architecture_enabled"] = False
        report["prompt_architecture_version"] = "legacy"
        report["retry_count"] = retry_count
        return report

    def run_new_prompt_architecture(self, cycle_context: Dict[str, Any]) -> Dict[str, Any]:
        model_role = str(self.config["model_role"])
        desk_context = build_desk_context(self.agent_id, cycle_context)
        memory_context = retrieve_memory(self.agent_id, str(cycle_context["cycle_id"]))
        system_prompt, user_prompt = compile_prompts(
            self.agent_id,
            self.config,
            desk_context,
            memory_context,
            cycle_context,
        )
        self.write_prompt_audit(cycle_context, system_prompt, user_prompt, desk_context, memory_context)

        result = chat_with_model(
            model_role=model_role,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            require_json=True,
            schema_env="AGENT_REPORT_SCHEMA_PATH",
        )

        retry_records = []
        retry_count = 0
        # Semantic content gate (new prompt architecture path)
        if result.get("ok") and isinstance(result.get("parsed"), dict):
            _p = result["parsed"]
            if semantic_content_error(_p):
                result = {
                    "ok": False,
                    "error": (
                        "EMPTY_CONTENT_RESPONSE: agent returned scaffold defaults only — "
                        "summary empty, key_findings=[], confidence=0.5. "
                        "Model must populate findings from evidence packet."
                    ),
                    "response_text": json.dumps(_p),
                }
        while not result.get("ok") and self.retry_allowed(str(result.get("error", "")), retry_count):
            retry_count += 1
            failed_text = str(result.get("response_text") or result.get("error") or "")
            self.write_failed_attempt(cycle_context, retry_count, failed_text)
            error_type = classify_error(str(result.get("error", "")))
            retry_system_prompt = build_retry_system_prompt(self.agent_id, self.display_name)
            retry_user_prompt = build_retry_user_prompt(
                str(result.get("error", "")),
                failed_text,
                self.agent_id,
                retry_count,
            )
            result = chat_with_model(
                model_role=model_role,
                system_prompt=retry_system_prompt,
                user_prompt=retry_user_prompt,
                require_json=True,
                schema_env="AGENT_REPORT_SCHEMA_PATH",
            )
            # Re-apply semantic content gate on retry responses too
            if result.get("ok") and isinstance(result.get("parsed"), dict):
                _p = result["parsed"]
                if semantic_content_error(_p):
                    result = {
                        "ok": False,
                        "error": (
                            "EMPTY_CONTENT_RESPONSE: retry also returned scaffold defaults — "
                            "summary empty, key_findings=[], confidence=0.5."
                        ),
                        "response_text": json.dumps(_p),
                    }
            retry_records.append(
                build_retry_record(
                    retry_count,
                    error_type,
                    str(result.get("error", "")) if not result.get("ok") else "",
                    bool(result.get("ok")),
                )
            )

        if retry_records:
            self.write_retry_record(cycle_context, retry_records)

        if not result.get("ok"):
            raise RuntimeError(str(result.get("error", "Agent LLM call failed.")))

        report = self.finalize_report(result["parsed"], cycle_context)
        normalizations = normalize_agent_report_format(report)
        report["prompt_architecture_enabled"] = True
        report["prompt_architecture_version"] = "v2"
        report["retry_count"] = retry_count
        report["memory_snippets_used"] = memory_snippet_count(memory_context)
        report["format_normalizations_applied"] = normalizations
        return report

    def retry_allowed(self, validation_error: str, retry_count: int) -> bool:
        if not should_retry(validation_error, retry_count, self.agent_id):
            return False
        policy = self.config.get("_retry_policy", {})
        max_retries = env_int("LLM_MAX_RETRIES", int(policy.get("max_retries", 2) or 2))
        if retry_count >= max_retries:
            return False
        error_type = classify_error(validation_error)
        if error_type == "JSON_PARSE_ERROR":
            return bool(policy.get("retry_on_json_parse_error", True))
        return bool(policy.get("retry_on_schema_failure", True))

    def finalize_report(self, report: Dict[str, Any], cycle_context: Dict[str, Any]) -> Dict[str, Any]:
        report["cycle_id"] = str(cycle_context["cycle_id"])
        report["agent_id"] = self.agent_id
        report["agent_name"] = self.display_name
        report["agent_role"] = str(self.config["agent_role"])
        report["model_used"] = str(cycle_context.get("model_used", ""))
        report["input_refs"] = cycle_context["input_refs"]
        report["manual_execution_required"] = True
        report["llm_order_generation"] = False
        report["created_at_sgt"] = sgt_now()
        return report

    def write_failed_attempt(self, cycle_context: Dict[str, Any], attempt: int, text: str) -> None:
        cycle_dir = cycle_dir_from_context(cycle_context)
        if cycle_dir is None:
            return
        path = cycle_dir / f"agent_{self.agent_id}_raw_failed_attempt_{attempt}.txt"
        path.write_text(text, encoding="utf-8")

    def write_retry_record(self, cycle_context: Dict[str, Any], records: list[Dict[str, Any]]) -> None:
        cycle_dir = cycle_dir_from_context(cycle_context)
        if cycle_dir is None:
            return
        path = cycle_dir / f"agent_{self.agent_id}_retry_record.json"
        path.write_text(json.dumps({"agent_id": self.agent_id, "records": records}, indent=2, ensure_ascii=False), encoding="utf-8")

    def write_prompt_audit(
        self,
        cycle_context: Dict[str, Any],
        system_prompt: str,
        user_prompt: str,
        desk_context: Dict[str, Any],
        memory_context: Dict[str, Any] | None,
    ) -> None:
        cycle_dir = cycle_dir_from_context(cycle_context)
        if cycle_dir is None:
            return
        audit = {
            "cycle_id": str(cycle_context["cycle_id"]),
            "agent_id": self.agent_id,
            "prompt_architecture_version": "v2",
            "prompt_registry_version": config_schema_version("PROMPT_REGISTRY_PATH", "config/prompt_registry.yaml"),
            "context_map_version": config_schema_version("AGENT_CONTEXT_MAP_PATH", "config/agent_context_map.yaml"),
            "memory_policy_version": config_schema_version("MEMORY_RETRIEVAL_POLICY_PATH", "config/memory_retrieval_policy.yaml"),
            "system_prompt_hash": sha256_text(system_prompt),
            "user_prompt_hash": sha256_text(user_prompt),
            "system_prompt_chars": len(system_prompt),
            "user_prompt_chars": len(user_prompt),
            "desk_context_chars": json_chars(desk_context),
            "memory_context_chars": json_chars(memory_context or {}),
            "memory_snippets_used": memory_snippet_count(memory_context),
            "config_files_used": {
                "prompt_registry": os.getenv("PROMPT_REGISTRY_PATH", "config/prompt_registry.yaml"),
                "agent_context_map": os.getenv("AGENT_CONTEXT_MAP_PATH", "config/agent_context_map.yaml"),
                "memory_retrieval_policy": os.getenv("MEMORY_RETRIEVAL_POLICY_PATH", "config/memory_retrieval_policy.yaml"),
            },
            "feature_flag_status": {
                "USE_NEW_PROMPT_ARCH": env_bool("USE_NEW_PROMPT_ARCH", False),
                "PROMPT_ARCH_TEST_AGENT": os.getenv("PROMPT_ARCH_TEST_AGENT", ""),
                "SAVE_COMPILED_PROMPTS_FOR_AUDIT": env_bool("SAVE_COMPILED_PROMPTS_FOR_AUDIT", False),
            },
            "model_role": str(self.config.get("model_role", "")),
            "schema_path": os.getenv("AGENT_REPORT_SCHEMA_PATH", ""),
            "created_at_sgt": sgt_now(),
        }
        path = cycle_dir / f"prompt_audit_{self.agent_id}.json"
        path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        if env_bool("SAVE_COMPILED_PROMPTS_FOR_AUDIT", False):
            private_dir = cycle_dir / "prompt_audit_private"
            private_dir.mkdir(parents=True, exist_ok=True)
            (private_dir / f"{self.agent_id}_system_prompt.txt").write_text(system_prompt, encoding="utf-8")
            (private_dir / f"{self.agent_id}_user_prompt.txt").write_text(user_prompt, encoding="utf-8")

    def system_prompt(self) -> str:
        role_memory = str(self.config.get("role_memory", "")).strip()
        out_of_scope = self.config.get("out_of_scope", [])
        out_of_scope_text = "; ".join(str(item) for item in out_of_scope) if isinstance(out_of_scope, list) else str(out_of_scope)
        return (
            f"You are the {self.display_name} inside the BlueLotus V3 Qwen Agent Council. "
            "You have no memory between calls; this prompt is your complete operating memory. "
            f"Your permanent desk mandate is: {self.config['agent_role']} "
            f"{role_memory} "
            "Role-play the desk deeply, but stay evidence-bound. Do not imitate other desks. "
            "Do not produce generic market commentary. Do not invent facts not present in the supplied context. "
            f"Out of scope for this desk: {out_of_scope_text or 'anything outside the desk mandate'}. "
            "Respect deterministic operator blocks. CIO manual execution is required. "
            "Never recommend, route, draft, or imply executable broker orders. "
            "Return one compact JSON object only."
        )

    def user_prompt(self, cycle_context: Dict[str, Any]) -> str:
        if env_bool("COMPACT_QWEN_AGENT_PROMPTS", True):
            return self.compact_user_prompt(cycle_context)
        evidence_priority = self.config.get("evidence_priority", [])
        must_answer = self.config.get("must_answer", [])
        distinctive_behavior = str(self.config.get("distinctive_behavior", "")).strip()
        desk_context = self.desk_context(cycle_context)
        payload = {
            "cycle_id": cycle_context["cycle_id"],
            "agent_id": self.agent_id,
            "agent_name": self.display_name,
            "agent_role": self.config["agent_role"],
            "focus_areas": self.config.get("focus_areas", []),
            "role_memory": self.config.get("role_memory", ""),
            "evidence_priority": evidence_priority,
            "must_answer": must_answer,
            "distinctive_behavior": distinctive_behavior,
            "desk_context": desk_context,
            "input_refs": cycle_context["input_refs"],
        }
        return (
            "Produce a BlueLotus V3 agent report using this JSON schema version: "
            "bluelotus_v3_agent_report_v1.0. Keep arrays short. Confidence must be a number from 0 to 1. "
            "Every array item must be a short string, never an object. Use at most three items per array. "
            "summary must be one sentence and must name this desk's specific lens. "
            "Each key_findings item must start with one evidence tag: [DATASET], [OPERATOR], [NEWS], [THESIS], or [BRIER]. "
            "Each risk_flags item must start with P1, P2, or P3. "
            "Do not reuse another desk's wording. If evidence is insufficient, say so in blind_spots instead of filling space. "
            "The desk_context object is your only evidence packet. Do not infer from missing shared context. "
            "Only discuss the desk mandate, evidence_priority, and must_answer questions supplied below. "
            "If live news is not in your evidence_priority, do not make live-news findings unless desk_context explicitly contains them. "
            "causal_completeness must be complete, partial, or incomplete. "
            "recommendation_to_chief_strategist must be one of WAIT, HOLD, REVIEW, "
            "MANUAL_REVIEW_REQUIRED, CIO_VERIFICATION_REQUIRED, RISK_REVIEW_REQUIRED, "
            "THESIS_REVIEW_REQUIRED, REDUCE_RISK_REVIEW, RAISE_CASH_REVIEW, HEDGE_REVIEW. "
            "manual_execution_required must be true and llm_order_generation must be false. "
            "Use the supplied cycle_id and agent_id. Context follows:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    def compact_user_prompt(self, cycle_context: Dict[str, Any]) -> str:
        """Small-model prompt for local Qwen with environment-governed evidence budgets."""
        must_answer_chars = env_int("QWEN_AGENT_MUST_ANSWER_CHARS", 360)
        desk_context_chars = env_int("QWEN_AGENT_DESK_CONTEXT_CHARS", 1300)
        input_refs_chars = env_int("QWEN_AGENT_INPUT_REFS_CHARS", 360)
        max_prompt_chars = env_int("QWEN_AGENT_MAX_PROMPT_CHARS", 30000)
        payload = {
            "cycle_id": cycle_context["cycle_id"],
            "agent_id": self.agent_id,
            "agent_name": self.display_name,
            "agent_role": self.config["agent_role"],
            "role_memory": compact(self.config.get("role_memory", ""), env_int("QWEN_AGENT_ROLE_MEMORY_CHARS", 1400)),
            "focus_areas": compact(self.config.get("focus_areas", []), env_int("QWEN_AGENT_FOCUS_AREAS_CHARS", 1200)),
            "evidence_priority": compact(self.config.get("evidence_priority", []), env_int("QWEN_AGENT_EVIDENCE_PRIORITY_CHARS", 1200)),
            "must_answer": compact(self.config.get("must_answer", []), must_answer_chars),
            "distinctive_behavior": compact(self.config.get("distinctive_behavior", ""), env_int("QWEN_AGENT_DISTINCTIVE_BEHAVIOR_CHARS", 1200)),
            "desk_context": compact(self.desk_context(cycle_context), desk_context_chars),
            "input_refs": compact(cycle_context["input_refs"], input_refs_chars),
        }
        prompt = (
            "You are one BlueLotus V3 desk. Return ONE valid JSON object only. "
            "No markdown. No prose outside JSON. Use only the evidence packet.\n"
            "Required schema_version: bluelotus_v3_agent_report_v1.0. "
            "Use the supplied cycle_id and agent_id. "
            "key_findings, risk_flags, blocked_actions_observed, allowed_actions_observed, "
            "affected_theses, affected_assets, blind_spots are arrays of short strings, max 3 each. "
            "key_findings strings must start with [DATASET], [OPERATOR], [NEWS], [THESIS], or [BRIER]. "
            "risk_flags strings must start with P1, P2, or P3. "
            "causal_completeness must be complete, partial, or incomplete. "
            "recommendation_to_chief_strategist must be WAIT, HOLD, REVIEW, "
            "MANUAL_REVIEW_REQUIRED, CIO_VERIFICATION_REQUIRED, RISK_REVIEW_REQUIRED, "
            "THESIS_REVIEW_REQUIRED, REDUCE_RISK_REVIEW, RAISE_CASH_REVIEW, or HEDGE_REVIEW. "
            "manual_execution_required must be true. llm_order_generation must be false. "
            "confidence must be a number from 0 to 1.\n"
            "Return this shape exactly with your desk-specific content:\n"
            '{"schema_version":"bluelotus_v3_agent_report_v1.0","cycle_id":"","agent_id":"",'
            '"agent_name":"","agent_role":"","model_used":"","input_refs":{},"summary":"",'
            '"key_findings":[],"risk_flags":[],"blocked_actions_observed":[],"allowed_actions_observed":[],'
            '"affected_theses":[],"affected_assets":[],"causal_completeness":"partial","blind_spots":[],'
            '"confidence":0.5,"recommendation_to_chief_strategist":"WAIT",'
            '"requires_cio_attention":false,"manual_execution_required":true,'
            '"llm_order_generation":false,"created_at_sgt":""}\n'
            "Evidence packet:\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )
        if len(prompt) > max_prompt_chars:
            reduced_payload = {
                **payload,
                "desk_context": compact(payload["desk_context"], max(1000, desk_context_chars // 2)),
                "input_refs": compact(payload["input_refs"], max(300, input_refs_chars // 2)),
                "prompt_budget_reduction": {
                    "reason": "QWEN_AGENT_MAX_PROMPT_CHARS exceeded",
                    "original_prompt_chars": len(prompt),
                    "max_prompt_chars": max_prompt_chars,
                },
            }
            prompt = prompt.split("Evidence packet:\n", 1)[0] + "Evidence packet:\n" + json.dumps(reduced_payload, ensure_ascii=False, separators=(",", ":"))
        return prompt

    def desk_context(self, cycle_context: Dict[str, Any]) -> Dict[str, Any]:
        dataset = load_json_path(str(cycle_context.get("dataset_summary", {}).get("path", "")))
        operator_source = parse_summary_excerpt(cycle_context.get("operator_verdict_pack", {}).get("source_summary", {}))
        live_news = parse_summary_excerpt(cycle_context.get("live_news_summary", {}))
        brier = parse_summary_excerpt(cycle_context.get("brier_summary", {}))
        thesis_registry = cycle_context.get("thesis_registry", {})
        agent_id = self.agent_id
        common = {
            "operator_summary": compact(operator_source.get("summary", {})),
            "blocked_actions": compact(cycle_context.get("operator_verdict_pack", {}).get("blocked_actions", [])),
            "allowed_actions": compact(cycle_context.get("operator_verdict_pack", {}).get("allowed_actions", [])),
        }
        if agent_id == "data_integrity":
            return {
                **common,
                "meta": compact(dataset.get("meta", {})),
                "source_health": compact(dataset.get("source_health", {})),
                "data_quality_sla": compact(dataset.get("data_quality_sla", {})),
                "freshness_recovery": compact(dataset.get("freshness_recovery", {})),
                "archive_status": compact({
                    "dataset_snapshot_archive": dataset.get("dataset_snapshot_archive", {}),
                    "data_lineage": dataset.get("data_lineage", {}),
                }),
                "relevant_operators": compact(select_operators(operator_source, ["freshness_governor", "archive_mismatch"])),
            }
        if agent_id == "macro_strategist":
            return {
                **common,
                "regime": compact(dataset.get("regime", {})),
                "fear_greed": compact(dataset.get("fear_greed", {})),
                "treasury_yields": compact(dataset.get("treasury_yields", {})),
                "cross_market_confirmation": compact(dataset.get("cross_market_confirmation", {})),
                "macro_event_risks": compact(dataset.get("macro_event_risks", {})),
                "relevant_operators": compact(select_operators(operator_source, ["macro_regime", "freshness_governor"])),
            }
        if agent_id == "portfolio_structure":
            return {
                **common,
                "portfolio": compact(dataset.get("portfolio", {})),
                "portfolio_readonly": compact(dataset.get("portfolio_readonly", {})),
                "risk_metrics": compact(dataset.get("risk_metrics", {})),
                "portfolio_constraints": compact(dataset.get("portfolio_constraints", {})),
                "portfolio_mandates": compact(dataset.get("portfolio_mandates", {})),
                "relevant_operators": compact(select_operators(operator_source, ["concentration_risk", "portfolio_mandate", "execution_safety"])),
            }
        if agent_id == "catalyst_intelligence":
            return {
                **common,
                "live_news": compact(live_news),
                "catalyst_calendar": compact(dataset.get("catalyst_calendar", {})),
                "conference_calendar": compact(dataset.get("conference_calendar", {})),
                "ceo_appearances": compact(dataset.get("ceo_appearances", {})),
                "macro_event_risks": compact(dataset.get("macro_event_risks", {})),
                "priority_intelligence": compact(dataset.get("priority_intelligence", {})),
                "relevant_operators": compact(select_operators(operator_source, ["catalyst_intelligence", "macro_regime"])),
            }
        if agent_id == "thesis_lifecycle":
            return {
                **common,
                "thesis_registry": compact(thesis_registry),
                "thesis_lifecycle": compact(dataset.get("thesis_lifecycle", {})),
                "priority_intelligence": compact(dataset.get("priority_intelligence", {})),
                "relevant_operators": compact(select_operators(operator_source, ["thesis_lifecycle", "gold_thesis", "archive_mismatch"])),
            }
        if agent_id == "risk_challenger":
            return {
                **common,
                "governance_risk": compact({
                    "risk_metrics": dataset.get("risk_metrics", {}),
                    "portfolio_constraints": dataset.get("portfolio_constraints", {}),
                    "monitoring": dataset.get("monitoring", {}),
                    "signal_validation": dataset.get("signal_validation", {}),
                }),
                "dirty_or_weak_evidence": compact({
                    "ticker_sentiment": dataset.get("ticker_sentiment", {}),
                    "event_correlations": dataset.get("event_correlations", {}),
                }),
                "relevant_operators": compact(operator_source.get("operators", {})),
            }
        if agent_id == "forecasting_brier":
            return {
                **common,
                "brier_summary": compact(brier),
                "research_forecasting": compact(dataset.get("research_forecasting", {})),
                "backtest_results": compact(dataset.get("backtest_results", {})),
                "signal_validation": compact(dataset.get("signal_validation", {})),
                "relevant_operators": compact(select_operators(operator_source, ["macro_regime", "catalyst_intelligence"])),
            }
        if agent_id == "sector_specialist":
            return {
                **common,
                "event_correlations": compact(dataset.get("event_correlations", {})),
                "event_correlations_all": compact(dataset.get("event_correlations_all", {})),
                "sector_inputs": compact({
                    "capital_flow": dataset.get("capital_flow", {}),
                    "tech_pub_signals": dataset.get("tech_pub_signals", {}),
                    "institutional_quant": dataset.get("institutional_quant", {}),
                }),
                "relevant_operators": compact(select_operators(operator_source, ["macro_regime", "concentration_risk", "catalyst_intelligence"])),
            }
        if agent_id == "sentiment_narrative":
            return {
                **common,
                "ticker_sentiment": compact(dataset.get("ticker_sentiment", {})),
                "source_health": compact(dataset.get("source_health", {})),
                "live_news": compact(live_news),
                "relevant_operators": compact(select_operators(operator_source, ["macro_regime", "catalyst_intelligence"])),
            }
        return common


def sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


def load_json_path(path_text: str) -> Dict[str, Any]:
    if not path_text:
        return {}
    path = Path(path_text)
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def parse_summary_excerpt(summary: Any) -> Dict[str, Any]:
    if not isinstance(summary, dict):
        return {}
    excerpt = summary.get("excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        return {}
    try:
        parsed = json.loads(excerpt)
    except Exception:
        return {"excerpt": excerpt[:env_int("QWEN_AGENT_TEXT_EXCERPT_CHARS", 2000)]}
    return compact(parsed, env_int("QWEN_AGENT_SUMMARY_EXCERPT_CHARS", 2500)) if isinstance(parsed, dict) else {"excerpt": excerpt[:env_int("QWEN_AGENT_TEXT_EXCERPT_CHARS", 2000)]}


def select_operators(operator_source: Dict[str, Any], names: list[str]) -> Dict[str, Any]:
    operators = operator_source.get("operators", {}) if isinstance(operator_source, dict) else {}
    if not isinstance(operators, dict):
        return {}
    return {name: operators.get(name) for name in names if name in operators}


def compact(value: Any, max_chars: int | None = None) -> Any:
    if max_chars is None:
        max_chars = env_int("QWEN_AGENT_CONTEXT_FIELD_CHARS", 2200)
    text = json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    if len(text) <= max_chars:
        return value
    return {"truncated": True, "excerpt": text[:max_chars]}


def cycle_dir_from_context(cycle_context: Dict[str, Any]) -> Path | None:
    path_text = str(cycle_context.get("cycle_dir", "")).strip()
    if not path_text:
        return None
    path = Path(path_text)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def json_chars(value: Any) -> int:
    return len(json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":")))


def memory_snippet_count(memory_context: Dict[str, Any] | None) -> int:
    if not isinstance(memory_context, dict):
        return 0
    entries = memory_context.get("entries")
    return len(entries) if isinstance(entries, list) else 0


def config_schema_version(env_name: str, default_path: str) -> str:
    path_text = os.getenv(env_name, "").strip() or default_path
    try:
        path = resolve_project_path(path_text)
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return "unknown"
    if not isinstance(data, dict):
        return "unknown"
    return str(data.get("schema_version") or data.get("version") or "unknown")


VALID_EVIDENCE_TAGS = ("[DATASET]", "[OPERATOR]", "[NEWS]", "[THESIS]", "[BRIER]", "[MEMORY]")


def semantic_content_error(report: Dict[str, Any]) -> bool:
    """Return True when a schema-valid agent report is too empty to publish normally."""
    summary = str(report.get("summary") or "").strip()
    key_findings = report.get("key_findings")
    if not summary:
        return True
    if not isinstance(key_findings, list):
        return True
    return not any(str(item).strip() for item in key_findings)


def normalize_agent_report_format(report: Dict[str, Any]) -> Dict[str, int]:
    """Apply deterministic output-contract formatting without changing analysis."""
    key_findings = report.get("key_findings")
    risk_flags = report.get("risk_flags")
    normalizations = {"key_findings_evidence_tags": 0, "risk_flag_priorities": 0}

    if isinstance(key_findings, list):
        updated = []
        for item in key_findings:
            text = str(item).strip()
            if text and not text.startswith(VALID_EVIDENCE_TAGS):
                text = f"{infer_evidence_tag(text)} {text}"
                normalizations["key_findings_evidence_tags"] += 1
            updated.append(text)
        report["key_findings"] = updated

    if isinstance(risk_flags, list):
        updated = []
        for item in risk_flags:
            text = str(item).strip()
            if text and not text.startswith(("P1", "P2", "P3")):
                text = f"{infer_risk_priority(text)} {text}"
                normalizations["risk_flag_priorities"] += 1
            updated.append(text)
        report["risk_flags"] = updated

    return normalizations


def infer_evidence_tag(text: str) -> str:
    lower = text.lower()
    if "operator" in lower or "blocked" in lower or "allowed" in lower:
        return "[OPERATOR]"
    if "news" in lower or "headline" in lower or "catalyst" in lower:
        return "[NEWS]"
    if "thesis" in lower:
        return "[THESIS]"
    if "brier" in lower or "forecast" in lower or "calibration" in lower:
        return "[BRIER]"
    if "memory" in lower or "prior cycle" in lower:
        return "[MEMORY]"
    return "[DATASET]"


def infer_risk_priority(text: str) -> str:
    lower = text.lower()
    p1_terms = ("breach", "conflict", "fail", "blocked", "concentrated", "integrity", "stale")
    return "P1" if any(term in lower for term in p1_terms) else "P2"
