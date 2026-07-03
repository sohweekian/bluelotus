from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(r"C:\bluelotus3")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from db_efficiency.object_store import build_cycle_manifest, build_object_reference, object_hash, payload_size_bytes

DEFAULT_INPUT = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "frontend" / "dataset_public.json"


def _pick(dataset: Dict[str, Any], key: str) -> Any:
    return dataset.get(key) if key in dataset else {}


def build_public_dataset(dataset: Dict[str, Any]) -> Dict[str, Any]:
    canonical = dataset.get("canonical") if isinstance(dataset.get("canonical"), dict) else {}
    pipeline = dataset.get("deterministic_pipeline_v3_2") if isinstance(dataset.get("deterministic_pipeline_v3_2"), dict) else {}
    replay = dataset.get("deterministic_replay_v3_3") if isinstance(dataset.get("deterministic_replay_v3_3"), dict) else {}
    benchmark = dataset.get("benchmark_dashboard_v3_4") if isinstance(dataset.get("benchmark_dashboard_v3_4"), dict) else {}
    risk = dataset.get("risk_overlay") if isinstance(dataset.get("risk_overlay"), dict) else {}
    lock = dataset.get("v3_4_observation_lock") if isinstance(dataset.get("v3_4_observation_lock"), dict) else {}
    return {
        "version": "v3-public-dataset-compact",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dataset_hash": object_hash(dataset),
        "source_dataset_size_bytes": payload_size_bytes(dataset),
        "meta": _pick(dataset, "meta"),
        "regime": _pick(dataset, "regime"),
        "portfolio": _pick(dataset, "portfolio"),
        "live_prices": _pick(dataset, "live_prices"),
        "fear_greed": _pick(dataset, "fear_greed"),
        "thesis_widgets": _pick(dataset, "thesis_widgets"),
        "chief_strategist": _pick(dataset, "chief_strategist"),
        "canonical_summary": {
            "version": canonical.get("version"),
            "validation": canonical.get("validation"),
            "governance": canonical.get("governance"),
            "session_state": canonical.get("session_state"),
            "portfolio_state": canonical.get("portfolio_state"),
            "order_state": canonical.get("order_state"),
            "target_usd_vector_ref": build_object_reference("TARGET_USD_VECTOR", (canonical.get("target_usd_vector") or {}), source_key="canonical.target_usd_vector"),
        },
        "risk_overlay_summary": {
            "version": risk.get("version"),
            "risk_overlay_status": risk.get("risk_overlay_status"),
            "portfolio": risk.get("portfolio"),
            "ticker_count": len(risk.get("ticker_outputs") or []),
            "object_ref": build_object_reference("RISK_OVERLAY", risk, source_key="risk_overlay"),
        },
        "pipeline_summary": {
            "version": pipeline.get("version"),
            "stage_count": pipeline.get("stage_count"),
            "final_status": pipeline.get("final_status"),
            "validation": pipeline.get("validation"),
            "stages": [
                {
                    "stage_name": stage.get("stage_name"),
                    "status": stage.get("status"),
                    "warning_count": len(stage.get("warnings") or []),
                    "error_count": len(stage.get("errors") or []),
                }
                for stage in (pipeline.get("stages") or [])
                if isinstance(stage, dict)
            ],
            "object_ref": build_object_reference("DETERMINISTIC_PIPELINE", pipeline, source_key="deterministic_pipeline_v3_2"),
        },
        "replay_summary": {
            "version": replay.get("version"),
            "strategy_count": replay.get("strategy_count"),
            "scenario_count": replay.get("scenario_count"),
            "benchmark_row_count": len(replay.get("benchmark_results") or []),
            "point_in_time_guard_status": replay.get("point_in_time_guard_status"),
            "top_summary": (replay.get("summary") or [])[:10],
            "object_ref": build_object_reference("DETERMINISTIC_REPLAY", replay, source_key="deterministic_replay_v3_3"),
        },
        "benchmark_summary": {
            "version": benchmark.get("version"),
            "benchmark_id": benchmark.get("benchmark_id"),
            "benchmark_dashboard_status": benchmark.get("benchmark_dashboard_status"),
            "point_in_time_status": benchmark.get("point_in_time_status"),
            "portfolio_scorecard": benchmark.get("portfolio_scorecard"),
            "benchmark_rankings": (benchmark.get("benchmark_rankings") or [])[:10],
            "scenario_scorecards": benchmark.get("scenario_scorecards"),
            "object_ref": build_object_reference("BENCHMARK_DASHBOARD", benchmark, source_key="benchmark_dashboard_v3_4"),
        },
        "observation_lock": lock,
        "cycle_manifest": build_cycle_manifest(dataset),
        "execution_authority": "CIO_ONLY_MANUAL",
        "order_routing_enabled": False,
        "system_orders_generated": 0,
    }


def write_public_dataset(input_path: Path = DEFAULT_INPUT, output_path: Path = DEFAULT_OUTPUT) -> Dict[str, Any]:
    dataset = json.loads(input_path.read_text(encoding="utf-8"))
    public = build_public_dataset(dataset)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(public, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return {
        "status": "written",
        "input_path": str(input_path),
        "output_path": str(output_path),
        "input_size_bytes": input_path.stat().st_size,
        "output_size_bytes": output_path.stat().st_size,
        "reduction_pct": round((1 - (output_path.stat().st_size / max(1, input_path.stat().st_size))) * 100, 2),
    }


def main() -> None:
    summary = write_public_dataset()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
