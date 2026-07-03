from __future__ import annotations

import importlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from archive.agent_report_archive import write_agent_error, write_agent_report
from archive.disagreement_archive import write_disagreement_log
from archive.learning_loop_archive import write_learning_loop_snapshot
from archive.strategist_archive import write_json, write_text
from chief_strategist.cio_briefing_generator import build_cio_action_menu, render_cio_action_menu
from chief_strategist.disagreement_resolver import resolve_disagreements
from chief_strategist.strategist_report_generator import render_strategist_report
from chief_strategist.synthesis_engine import synthesize
from governance.contradiction_governance import build_contradiction_governance, write_contradiction_governance
from llm_clients.config_loader import append_log, env_bool, env_required, load_dotenv, load_main_config
from llm_clients.json_response_validator import validate_json_response
from orchestration.agent_execution_queue import load_execution_queue, ordered_agent_configs
from orchestration.cycle_context_builder import build_cycle_context, cycle_output_root
from quality.agent_quality_scorer import QualityReport, score_agent_report, summarise_cycle_quality


class LinearAgentOrchestrator:
    def __init__(self) -> None:
        self._llm_call_active = False

    def run_cycle(self, cycle_id: str | None = None) -> Dict[str, Any]:
        load_dotenv()
        cycle_context = build_cycle_context(cycle_id)
        cycle_dir = cycle_output_root(str(cycle_context["cycle_id"]))
        cycle_dir.mkdir(parents=True, exist_ok=True)
        cycle_context["cycle_dir"] = str(cycle_dir)
        queue = load_execution_queue()
        retry_policy = queue.get("retry_policy", {}) if isinstance(queue.get("retry_policy"), dict) else {}
        operator_pack = cycle_context["operator_verdict_pack"]
        validate_json_response(json.dumps(operator_pack), "OPERATOR_VERDICT_PACK_SCHEMA_PATH", save_failed=False)
        write_json(cycle_dir, "operator_verdict_pack.json", operator_pack)

        reports: List[Dict[str, Any]] = []
        errors: List[Dict[str, str]] = []
        quality_reports: Dict[str, QualityReport] = {}
        comparison_reports: List[Dict[str, Any]] = []
        for raw_agent_config in ordered_agent_configs():
            agent_config = dict(raw_agent_config)
            agent_config["_retry_policy"] = retry_policy
            agent_id = str(agent_config["agent_id"])
            agent_had_error = False
            try:
                report = self.run_one_agent(agent_config, cycle_context)
                validate_json_response(json.dumps(report), "AGENT_REPORT_SCHEMA_PATH", save_failed=False)
                write_agent_report(cycle_dir, report)
                quality = score_agent_report(agent_id, report, agent_config)
                quality_reports[agent_id] = quality
                write_json(cycle_dir, f"quality_{agent_id}.json", quality.summary())
                comparison = self.run_comparison_if_enabled(agent_config, cycle_context, report, quality)
                if comparison:
                    comparison_reports.append(comparison)
                reports.append(report)
            except Exception as exc:
                agent_had_error = True
                error_path = write_agent_error(cycle_dir, agent_id, str(exc))
                errors.append({"agent_id": agent_id, "error": str(exc), "path": error_path})
            finally:
                self.settle_llm_runner_between_agents(queue, cycle_context, agent_id, force_stop=agent_had_error)

        quality_summary = summarise_cycle_quality(quality_reports)
        write_json(cycle_dir, "cycle_quality_summary.json", quality_summary)
        if comparison_reports:
            write_json(cycle_dir, "prompt_arch_comparison_report.json", {"comparisons": comparison_reports})

        disagreement_log = resolve_disagreements(str(cycle_context["cycle_id"]), reports)
        write_disagreement_log(cycle_dir, disagreement_log)

        briefing = synthesize(cycle_context, reports)
        validate_json_response(json.dumps(briefing), "CHIEF_STRATEGIST_BRIEFING_SCHEMA_PATH", save_failed=False)
        menu = build_cio_action_menu(briefing)
        validate_json_response(json.dumps(menu), "CIO_ACTION_MENU_SCHEMA_PATH", save_failed=False)
        write_json(cycle_dir, "chief_strategist_briefing.json", briefing)
        write_text(cycle_dir, "chief_strategist_report.txt", render_strategist_report(briefing))
        write_text(cycle_dir, "cio_action_menu.md", render_cio_action_menu(menu, briefing))
        contradiction_governance = build_contradiction_governance(
            cycle_context,
            reports,
            briefing,
            quality_summary,
            errors,
        )
        contradiction_paths = write_contradiction_governance(cycle_dir, contradiction_governance)
        write_learning_loop_snapshot(cycle_dir, {
            "cycle_id": cycle_context["cycle_id"],
            "validated_agent_reports": len(reports),
            "agent_errors": errors,
            "quality_summary": quality_summary,
            "contradiction_governance": {
                "contradiction_count": contradiction_governance["contradiction_register"]["contradiction_count"],
                "p1_count": contradiction_governance["contradiction_register"]["p1_count"],
                "p2_count": contradiction_governance["contradiction_register"]["p2_count"],
                "p3_count": contradiction_governance["contradiction_register"]["p3_count"],
                "cio_decision_strip": contradiction_paths["cycle_cio_decision_strip"],
            },
            "prompt_architecture_enabled": env_bool("USE_NEW_PROMPT_ARCH", False),
            "manual_execution_required": True,
            "llm_order_generation": False,
        })

        return {
            "ok": True,
            "cycle_id": cycle_context["cycle_id"],
            "cycle_dir": str(cycle_dir),
            "validated_agent_reports": len(reports),
            "agent_errors": errors,
            "quality_summary": quality_summary,
            "comparison_reports": str(cycle_dir / "prompt_arch_comparison_report.json") if comparison_reports else "",
            "chief_strategist_briefing": str(cycle_dir / "chief_strategist_briefing.json"),
            "cio_action_menu": str(cycle_dir / "cio_action_menu.md"),
            "contradiction_register": contradiction_paths["cycle_contradiction_register"],
            "cio_decision_strip": contradiction_paths["cycle_cio_decision_strip"],
        }

    def run_one_agent(self, agent_config: Dict[str, Any], cycle_context: Dict[str, Any]) -> Dict[str, Any]:
        if self._llm_call_active:
            raise RuntimeError("Parallel LLM call blocked by linear orchestrator.")
        self._llm_call_active = True
        try:
            agent = instantiate_agent(agent_config)
            return agent.run(cycle_context)
        finally:
            self._llm_call_active = False

    def settle_llm_runner_between_agents(
        self,
        queue: Dict[str, Any],
        cycle_context: Dict[str, Any],
        agent_id: str,
        force_stop: bool = False,
    ) -> None:
        """Enforce physical Ollama quiescence between linear agent calls."""
        if not bool(queue.get("clear_between_agents", False)):
            return
        model_name = str(cycle_context.get("model_used", "")).strip()
        if force_stop and model_name:
            try:
                main_config = load_main_config()
                ollama_config = main_config.get("ollama", {}) if isinstance(main_config.get("ollama"), dict) else {}
                cli_env = str(ollama_config.get("cli_path_env") or "")
                cli_path = env_required(cli_env) if cli_env else "ollama"
                completed = subprocess.run(
                    [cli_path, "stop", model_name],
                    cwd=str(Path(__file__).resolve().parents[1]),
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=30,
                )
                if completed.returncode != 0:
                    append_log(
                        "v3_llm_runner_settle.log",
                        f"{cycle_context.get('cycle_id')} {agent_id}: ollama stop returned "
                        f"{completed.returncode}: {completed.stderr.strip()}",
                    )
            except Exception as exc:
                append_log("v3_llm_runner_settle.log", f"{cycle_context.get('cycle_id')} {agent_id}: settle failed: {exc}")
            if bool(queue.get("kill_llama_server_on_agent_error", False)):
                self.kill_llama_server_workers(cycle_context, agent_id)
        delay = queue.get("llm_settle_seconds", 2)
        try:
            time.sleep(max(0, float(delay)))
        except Exception:
            time.sleep(2)

    def kill_llama_server_workers(self, cycle_context: Dict[str, Any], agent_id: str) -> None:
        """Clean orphaned Ollama llama-server workers after a failed linear agent call."""
        if os.name != "nt":
            return
        try:
            completed = subprocess.run(
                ["taskkill", "/IM", "llama-server.exe", "/F"],
                cwd=str(Path(__file__).resolve().parents[1]),
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            append_log(
                "v3_llm_runner_settle.log",
                f"{cycle_context.get('cycle_id')} {agent_id}: taskkill llama-server return "
                f"{completed.returncode}: {(completed.stdout or completed.stderr).strip()}",
            )
        except Exception as exc:
            append_log("v3_llm_runner_settle.log", f"{cycle_context.get('cycle_id')} {agent_id}: llama-server cleanup failed: {exc}")

    def run_comparison_if_enabled(
        self,
        agent_config: Dict[str, Any],
        cycle_context: Dict[str, Any],
        production_report: Dict[str, Any],
        production_quality: QualityReport,
    ) -> Dict[str, Any] | None:
        if not env_bool("RUN_PROMPT_ARCH_COMPARISON", False):
            return None
        agent_id = str(agent_config["agent_id"])
        target = os.getenv("PROMPT_ARCH_COMPARISON_AGENT", "").strip()
        if target and target != agent_id:
            return None
        if self._llm_call_active:
            raise RuntimeError("Parallel LLM call blocked by linear orchestrator.")
        self._llm_call_active = True
        try:
            agent = instantiate_agent(agent_config)
            comparison_dir = Path(str(cycle_context["cycle_dir"])) / "prompt_arch_comparison" / agent_id
            comparison_context = dict(cycle_context)
            comparison_context["cycle_dir"] = str(comparison_dir)
            if production_report.get("prompt_architecture_enabled") is True:
                alternate_report = agent.run_legacy_prompt_path(comparison_context)
                old_report, new_report = alternate_report, production_report
            else:
                alternate_report = agent.run_new_prompt_architecture(comparison_context)
                old_report, new_report = production_report, alternate_report
            validate_json_response(json.dumps(alternate_report), "AGENT_REPORT_SCHEMA_PATH", save_failed=False)
            old_quality = score_agent_report(agent_id, old_report, agent_config)
            new_quality = score_agent_report(agent_id, new_report, agent_config)
            comparison_dir.mkdir(parents=True, exist_ok=True)
            write_json(comparison_dir, "old_quality.json", old_quality.summary())
            write_json(comparison_dir, "new_quality.json", new_quality.summary())
            write_json(comparison_dir, "alternate_report.json", alternate_report)
            return {
                "agent_id": agent_id,
                "old_quality_score": round(old_quality.pct_score, 1),
                "new_quality_score": round(new_quality.pct_score, 1),
                "old_json_valid": True,
                "new_json_valid": True,
                "old_generic_flags": old_quality.dimension_scores.get("D2").notes if old_quality.dimension_scores.get("D2") else [],
                "new_generic_flags": new_quality.dimension_scores.get("D2").notes if new_quality.dimension_scores.get("D2") else [],
                "old_governance_flags": old_quality.dimension_scores.get("D10").notes if old_quality.dimension_scores.get("D10") else [],
                "new_governance_flags": new_quality.dimension_scores.get("D10").notes if new_quality.dimension_scores.get("D10") else [],
                "improvement_detected": new_quality.pct_score > old_quality.pct_score,
                "regression_detected": new_quality.pct_score < old_quality.pct_score,
                "notes": "Single-agent comparison executed without feeding alternate output into Chief Strategist.",
            }
        except Exception as exc:
            return {
                "agent_id": agent_id,
                "old_json_valid": production_report.get("prompt_architecture_enabled") is False,
                "new_json_valid": production_report.get("prompt_architecture_enabled") is True,
                "error": str(exc),
                "regression_detected": True,
                "notes": "Comparison alternate path failed; production path was not replaced.",
            }
        finally:
            self._llm_call_active = False


def instantiate_agent(agent_config: Dict[str, Any]):
    module = importlib.import_module(str(agent_config["module"]))
    cls = getattr(module, str(agent_config["class_name"]))
    return cls(agent_config)
