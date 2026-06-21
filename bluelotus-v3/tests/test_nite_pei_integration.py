"""
BlueLotus V3 - NITE-PEI integration regression tests.

These tests cover the durability defects found by Dr. Codex audit:
live event extraction, duplicate event guard, Brier preregistration, and
pipeline ordering.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import scripts.run_nite_pei_cycle as runner
from scripts.run_nite_pei_cycle import extract_live_events, prior_event_ids, run


def test_runner_no_static_real_events_operating_feed():
    source = (_ROOT / "scripts" / "run_nite_pei_cycle.py").read_text(encoding="utf-8")
    assert "REAL_EVENTS =" not in source


def test_extract_live_events_from_dataset_shape():
    dataset = {
        "signals_latest": [
            {
                "id": 1001,
                "source": "UnitTestNews",
                "quality_score": 0.95,
                "raw_text": "Fed hawkish statement signals higher for longer",
                "ticker_tags": ["TLT"],
                "received_at": "2026-06-21T00:00:00",
            }
        ],
        "macro_event_risks": [
            {"category": "Macro", "event": "BOJ hawkish yen carry risk", "event_date": "2026-06-21", "impact_class": "MACRO_RATE_FX"}
        ],
        "ticker_sentiment": {
            "GLD": {
                "cycle_ts": "2026-06-21 00:00:00",
                "headlines": ["Gold falls as peace deal lowers safe-haven demand"],
            }
        },
    }
    events = extract_live_events(dataset)
    ids = [event["event_id"] for event in events]
    assert len(events) >= 3
    assert len(ids) == len(set(ids))
    assert any(event["event_id"] == "signal:1001" for event in events)


def test_prior_event_ids_reads_legacy_and_new_history_shapes():
    thesis = {
        "probability_history": [
            {"event_id": "legacy:1"},
            {"event_ids": ["new:1", "new:2"]},
            {"applied_event_ids": ["old:1"]},
        ]
    }
    assert prior_event_ids(thesis) == {"legacy:1", "new:1", "new:2", "old:1"}


def test_nite_pei_run_writes_block_and_brier_record(tmp_path, monkeypatch):
    dataset_path = tmp_path / "dataset_raw.json"
    registry_path = tmp_path / "thesis_registry.yaml"
    cycle_dir = tmp_path / "v3_cycle_test"
    report_dir = cycle_dir / "agent_reports"
    report_dir.mkdir(parents=True)
    (report_dir / "risk_challenger.json").write_text(
        json.dumps({"agent_id": "risk_challenger", "risk_flags": ["P2: test"], "recommendation_to_chief_strategist": "WAIT"}),
        encoding="utf-8",
    )

    dataset_path.write_text(
        json.dumps({
            "portfolio": {"total_value": 100000, "positions": {"TLT": {"market_value": 1000}}},
            "signals_latest": [
                {
                    "id": 2001,
                    "source": "UnitTestNews",
                    "quality_score": 0.95,
                    "raw_text": "Fed hawkish statement signals higher for longer",
                    "ticker_tags": ["TLT"],
                    "received_at": "2026-06-21T00:00:00",
                }
            ],
            "macro_event_risks": [],
            "ticker_sentiment": {},
        }),
        encoding="utf-8",
    )
    registry_path.write_text(
        yaml.safe_dump({
            "theses": {
                "HAWKISH_WARSH_THESIS": {
                    "status": "watch",
                    "thesis_type": "HAWKISH_WARSH_THESIS",
                    "mapped_assets": ["TLT"],
                    "current_probability": 0.50,
                    "probability_history": [],
                    "kill_conditions": [
                        {
                            "kill_id": "WARSH_KC_TEST",
                            "kill_weight": 1.0,
                            "P_kill": 0.05,
                            "current_state": "INACTIVE",
                            "event_classes_that_trigger": ["CENTRAL_BANK_DOVISH"],
                        }
                    ],
                }
            }
        }, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        runner,
        "write_forecast_record",
        lambda thesis_id, event_id, p_prior, lr_used, lr_source, p_posterior, delta_p: f"NITE_BRIER_{thesis_id}_TEST",
    )
    monkeypatch.setattr(runner, "write_risk_state", lambda ckri_result: None)

    block = run(dataset_path=dataset_path, registry_path=registry_path, cycle_dir=cycle_dir)
    written = json.loads((cycle_dir / "nite_pei_block.json").read_text(encoding="utf-8"))
    updated_registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    hist = updated_registry["theses"]["HAWKISH_WARSH_THESIS"]["probability_history"]

    assert block["source_cycle_id"] == "v3_cycle_test"
    assert written["event_extraction"]["applied_events"] >= 1
    assert hist
    assert hist[-1]["event_ids"] == ["signal:2001"]
    assert hist[-1]["brier_record_id"].startswith("NITE_BRIER_")
    assert written["thesis_probability_snapshots"][0]["brier_record_id"].startswith("NITE_BRIER_")


def test_pipeline_runs_grand_cycle_then_nite_pei_then_publisher():
    config = yaml.safe_load((_ROOT / "config" / "v3_pipeline.yaml").read_text(encoding="utf-8"))
    labels = []
    for step in config["steps"]:
        labels.append(step.get("module") or step.get("script"))
    grand = labels.index("orchestration.run_v3_grand_cycle")
    nite = labels.index("scripts.run_nite_pei_cycle")
    publisher = labels.index("bluelotus_publisher.py")
    assert grand < nite < publisher
