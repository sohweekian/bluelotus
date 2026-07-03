"""
BlueLotus V3 — NITE-PEI Sub-Engine E5: Brier Calibration Loop
==============================================================
Manages pre-registration and post-resolution calibration of thesis probability
forecasts. Converts the Likelihood Ratio Table from a static expert artifact
into a living, empirically-calibrated instrument.

TWO PHASES:
  Write phase  — called immediately after each NITE-PEI Bayesian update.
                 Appends a pre-registered forecast record to the ledger.
  Resolve phase — called when CIO marks a thesis as RESOLVED.
                  Computes Brier score, determines direction correctness,
                  and adjusts the LR value in likelihood_ratio_table.yaml.

Reuses: pei.brier_crs_engine.brier_score, crs_decomposition

APPEND-ONLY: Ledger records are never deleted or overwritten.
GOVERNANCE: Deterministic only. No LLM. No order generation.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from zoneinfo import ZoneInfo

import yaml

from pei.brier_crs_engine import brier_score, crs_decomposition


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[1]
BRIER_LEDGER_PATH = _ROOT / "data" / "nite_pei_brier_ledger.json"
CALIBRATION_AUDIT_PATH = Path(__file__).parent / "calibration_audit_log.json"
LR_TABLE_PATH = Path(__file__).parent / "likelihood_ratio_table.yaml"


# ---------------------------------------------------------------------------
# SGT timestamp
# ---------------------------------------------------------------------------

def _sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Confidence classification
# ---------------------------------------------------------------------------

def classify_confidence(n: int) -> str:
    """Map calibration_n to confidence label."""
    if n >= 30:
        return "HIGH"
    if n >= 10:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Ledger helpers (append-only)
# ---------------------------------------------------------------------------

def _load_ledger(path: Path) -> List[Dict[str, Any]]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def _save_ledger(records: List[Dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_audit(audit_record: Dict[str, Any]) -> None:
    records = _load_ledger(CALIBRATION_AUDIT_PATH)
    records.append(audit_record)
    _save_ledger(records, CALIBRATION_AUDIT_PATH)


# ---------------------------------------------------------------------------
# Write phase — pre-registration
# ---------------------------------------------------------------------------

def write_forecast_record(
    thesis_id: str,
    event_id: str,
    p_prior: float,
    lr_used: float,
    lr_source: str,
    p_posterior: float,
    delta_p: float,
    ledger_path: Optional[Path] = None,
) -> str:
    """
    Pre-register a NITE-PEI probability forecast to the Brier ledger.
    Must be called BEFORE the thesis resolves (resolution_pending = True).

    Returns:
        brier_record_id — unique ID for this record (use in resolve_forecast)
    """
    target = Path(ledger_path) if ledger_path else BRIER_LEDGER_PATH
    records = _load_ledger(target)

    brier_record_id = f"NITE_BRIER_{thesis_id}_{uuid.uuid4().hex[:8].upper()}"
    record: Dict[str, Any] = {
        "brier_record_id": brier_record_id,
        "thesis_id": thesis_id,
        "event_id": event_id,
        "p_prior": round(float(p_prior), 6),
        "lr_used": round(float(lr_used), 6),
        "lr_source": lr_source,
        "p_posterior": round(float(p_posterior), 6),
        "delta_p": round(float(delta_p), 6),
        "resolution_pending": True,
        "final_outcome": None,
        "brier_score": None,
        "direction_correct": None,
        "created_at_sgt": _sgt_now(),
        "resolved_at_sgt": None,
    }
    records.append(record)
    _save_ledger(records, target)
    return brier_record_id


# ---------------------------------------------------------------------------
# Resolve phase — calibration
# ---------------------------------------------------------------------------

def resolve_forecast(
    brier_record_id: str,
    outcome: int,
    ledger_path: Optional[Path] = None,
    lr_table_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Resolve a pre-registered forecast and calibrate the LR table.

    Args:
        brier_record_id: ID returned from write_forecast_record.
        outcome:         1 = thesis confirmed, 0 = thesis invalidated.
        ledger_path:     Override for testing.
        lr_table_path:   Override for testing.

    Returns:
        Calibration result dict.
    """
    target_ledger = Path(ledger_path) if ledger_path else BRIER_LEDGER_PATH
    target_lr = Path(lr_table_path) if lr_table_path else LR_TABLE_PATH

    records = _load_ledger(target_ledger)
    record = next((r for r in records if r.get("brier_record_id") == brier_record_id), None)
    if record is None:
        return {"ok": False, "error": f"Record not found: {brier_record_id}"}

    p_post = float(record["p_posterior"])
    delta = float(record["delta_p"])
    outcome_int = 1 if outcome else 0

    bs = brier_score(p_post, outcome_int)
    direction_correct = (delta > 0 and outcome_int == 1) or (delta < 0 and outcome_int == 0)

    # Update ledger record in-place
    record["resolution_pending"] = False
    record["final_outcome"] = outcome_int
    record["brier_score"] = bs
    record["direction_correct"] = direction_correct
    record["resolved_at_sgt"] = _sgt_now()
    _save_ledger(records, target_ledger)

    # Calibrate LR table
    lr_source = str(record.get("lr_source", ""))
    lr_update = _calibrate_lr(lr_source, direction_correct, bs, target_lr)

    audit: Dict[str, Any] = {
        "brier_record_id": brier_record_id,
        "thesis_id": record["thesis_id"],
        "event_id": record["event_id"],
        "lr_source": lr_source,
        "outcome": outcome_int,
        "brier_score": bs,
        "direction_correct": direction_correct,
        "lr_before": lr_update.get("lr_before"),
        "lr_after": lr_update.get("lr_after"),
        "calibration_n_after": lr_update.get("calibration_n_after"),
        "confidence_after": lr_update.get("confidence_after"),
        "resolved_at_sgt": record["resolved_at_sgt"],
    }
    _append_audit(audit)

    return {"ok": True, "brier_score": bs, "direction_correct": direction_correct, **lr_update}


# ---------------------------------------------------------------------------
# LR calibration mechanics
# ---------------------------------------------------------------------------

def _calibrate_lr(
    lr_source: str,
    direction_correct: bool,
    bs: float,
    lr_table_path: Path,
) -> Dict[str, Any]:
    """
    Adjust the LR value in likelihood_ratio_table.yaml based on Brier outcome.

    Calibration rules (from thesis §13 / Contribution 3):
        Wrong direction  → lr shrinks 15% toward 1.0
        Correct + bs < 0.10 → lr strengthens 5% away from 1.0
        Correct + bs ≥ 0.10 → lr unchanged (correct direction but imprecise)
    """
    if "/" not in lr_source or lr_source.startswith("DEFAULT"):
        return {"lr_update_skipped": True, "reason": "No valid lr_source to update"}

    parts = lr_source.split("/", 1)
    event_class, thesis_type = parts[0], parts[1]

    with open(lr_table_path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    lr_table = data.get("lr_table", {})

    event_entries = lr_table.get(event_class, {})
    entry = event_entries.get(thesis_type) or event_entries.get("ANY")
    if entry is None:
        return {"lr_update_skipped": True, "reason": f"Entry not found: {lr_source}"}

    # Skip entries locked at LR=1.0 with high calibration_n (e.g. REFLEXIVE_SUPPRESSION)
    if int(entry.get("calibration_n", 0)) >= 100:
        return {"lr_update_skipped": True, "reason": "Locked entry (calibration_n >= 100)"}

    lr_before = float(entry.get("lr", 1.0))
    lr_after = lr_before

    if not direction_correct:
        # Shrink 15% toward 1.0
        lr_after = 1.0 + (lr_before - 1.0) * 0.85
    elif bs < 0.10:
        # Strengthen 5% away from 1.0
        lr_after = 1.0 + (lr_before - 1.0) * 1.05

    lr_after = round(lr_after, 6)
    new_n = int(entry.get("calibration_n", 0)) + 1
    new_confidence = classify_confidence(new_n)

    # Write back
    entry["lr"] = lr_after
    entry["calibration_n"] = new_n
    entry["confidence"] = new_confidence
    entry["last_calibrated_sgt"] = _sgt_now()

    data["lr_table"] = lr_table
    tmp = lr_table_path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, sort_keys=False, default_flow_style=False)
    tmp.replace(lr_table_path)

    return {
        "lr_source": lr_source,
        "lr_before": lr_before,
        "lr_after": lr_after,
        "calibration_n_after": new_n,
        "confidence_after": new_confidence,
    }


# ---------------------------------------------------------------------------
# CRS decomposition pass-through (reuses pei.brier_crs_engine)
# ---------------------------------------------------------------------------

def nite_pei_crs_summary(ledger_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Run CRS decomposition over all resolved NITE-PEI forecast records.
    Reuses pei.brier_crs_engine.crs_decomposition.
    """
    target = Path(ledger_path) if ledger_path else BRIER_LEDGER_PATH
    records = _load_ledger(target)
    resolved = [
        {"probability": r["p_posterior"], "final_outcome": r["final_outcome"]}
        for r in records
        if not r.get("resolution_pending") and r.get("final_outcome") is not None
    ]
    return crs_decomposition(resolved)
