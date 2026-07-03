import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.v3_db_writers import persist_cycle_archive
from llm_clients.config_loader import env_required, load_dotenv, resolve_project_path


def main() -> None:
    load_dotenv()
    cycle_id = "test_v3_db_writer_cycle"
    root = resolve_project_path(env_required("V3_CYCLE_OUTPUT_DIR")) / cycle_id
    report_dir = root / "agent_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    write_cycle_fixture(root, report_dir, cycle_id)
    result = persist_cycle_archive(root, health={"checked_at_sgt": "test", "gpu_runtime_confirmed": False})
    assert result["ok"]
    assert result["agent_reports"] == 1
    print("PASS v3 db writers")


def write_cycle_fixture(root: Path, report_dir: Path, cycle_id: str) -> None:
    operator = {
        "schema_version": "bluelotus_v3_operator_verdict_pack_v1.0",
        "cycle_id": cycle_id,
        "operator_pack_id": "test_operator_pack",
        "blocked_actions": [],
        "allowed_actions": ["WAIT", "HOLD", "REVIEW"],
        "manual_execution_required": True,
        "llm_order_generation": False,
    }
    report = {
        "schema_version": "bluelotus_v3_agent_report_v1.0",
        "cycle_id": cycle_id,
        "agent_id": "data_integrity",
        "agent_name": "Data Integrity Agent",
        "agent_role": "Test",
        "model_used": "configured",
        "input_refs": {
            "dataset_snapshot_id": "test_dataset",
            "operator_pack_id": "test_operator_pack",
            "thesis_registry_version": "test",
            "live_news_brief_timestamp": "test_news",
        },
        "summary": "Test report.",
        "key_findings": ["Test finding"],
        "risk_flags": [],
        "blocked_actions_observed": [],
        "allowed_actions_observed": ["WAIT"],
        "affected_theses": [],
        "affected_assets": [],
        "causal_completeness": "partial",
        "blind_spots": [],
        "confidence": 0.5,
        "recommendation_to_chief_strategist": "WAIT",
        "requires_cio_attention": False,
        "manual_execution_required": True,
        "llm_order_generation": False,
        "created_at_sgt": "test",
    }
    briefing = {
        "schema_version": "bluelotus_v3_chief_strategist_briefing_v1.0",
        "cycle_id": cycle_id,
        "summary": "Test briefing.",
        "recommended_posture": "WAIT",
        "operator_blocks": [],
        "agent_consensus": ["Data Integrity Agent: WAIT"],
        "disagreements": [],
        "cio_attention_items": [],
        "manual_execution_required": True,
        "llm_order_generation": False,
        "created_at_sgt": "test",
    }
    (root / "operator_verdict_pack.json").write_text(json.dumps(operator), encoding="utf-8")
    (report_dir / "data_integrity.json").write_text(json.dumps(report), encoding="utf-8")
    (report_dir / "data_integrity.txt").write_text("Test report.", encoding="utf-8")
    (root / "chief_strategist_briefing.json").write_text(json.dumps(briefing), encoding="utf-8")
    (root / "chief_strategist_report.txt").write_text("Test briefing.", encoding="utf-8")
    (root / "cio_action_menu.md").write_text("Manual execution required: YES\nNo automatic orders generated.", encoding="utf-8")
    (root / "disagreement_log.json").write_text(json.dumps({"cycle_id": cycle_id, "disagreements": []}), encoding="utf-8")
    (root / "learning_loop_snapshot.json").write_text(json.dumps({"cycle_id": cycle_id, "agent_errors": []}), encoding="utf-8")


if __name__ == "__main__":
    main()
