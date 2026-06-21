from __future__ import annotations

import statistics
from typing import Any, Dict, List

from db.v3_db_connection import get_v3_connection
from pei.common import sgt_now, stable_id
from pei.tactical_cash_engine_rules import reload_allowed


def _historical_closes(ticker: str) -> List[float]:
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT close_price FROM historical_prices WHERE ticker=%s ORDER BY bar_date ASC",
            (ticker,),
        )
        closes = [float(row[0]) for row in cur.fetchall() if row[0] is not None]
        cur.close()
        return closes
    finally:
        conn.close()


def _percentile(values: List[float], q: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    idx = min(len(values) - 1, max(0, round((len(values) - 1) * q)))
    return values[idx]


def calibrate_oscillation_engine(ticker: str = "ASTS") -> Dict[str, Any]:
    closes = _historical_closes(ticker)
    if not closes:
        return {
            "ticker": ticker,
            "status": "INSUFFICIENT_HISTORY",
            "sample_size": 0,
            "regime_broken": True,
            "reload_allowed": False,
            "execution_authority": "CIO_ONLY_MANUAL",
        }
    mean = statistics.mean(closes)
    median = statistics.median(closes)
    support_low = _percentile(closes, 0.10)
    support_high = _percentile(closes, 0.25)
    trim_low = _percentile(closes, 0.75)
    trim_high = _percentile(closes, 0.90)
    last = closes[-1]
    regime_broken = last < support_low * 0.85
    confidence = min(0.85, max(0.35, len(closes) / 180))
    return {
        "ticker": ticker,
        "status": "CALIBRATED",
        "sample_size": len(closes),
        "behavioral_mean": round(mean, 4),
        "behavioral_median": round(median, 4),
        "support_band": [round(support_low, 4), round(support_high, 4)],
        "upper_harvest_band": [round(trim_low, 4), round(trim_high, 4)],
        "reload_zone": f"{support_low:.2f}-{support_high:.2f}",
        "trim_zone": f"{trim_low:.2f}-{trim_high:.2f}",
        "mean_reversion_confidence": round(confidence, 3),
        "regime_broken": regime_broken,
        "no_reload_warning": regime_broken,
        "reload_allowed": reload_allowed(regime_broken, over_cap=False, thesis_intact=True),
        "execution_authority": "CIO_ONLY_MANUAL",
    }


def persist_oscillation_calibration(calibration: Dict[str, Any]) -> None:
    if calibration.get("status") != "CALIBRATED":
        return
    conn = get_v3_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pei_oscillation_engine_calibrations (
                calibration_id, ticker, behavioral_mean, support_band_low,
                support_band_high, reload_zone, trim_zone, mean_reversion_confidence,
                regime_broken, created_at
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON DUPLICATE KEY UPDATE behavioral_mean=VALUES(behavioral_mean), regime_broken=VALUES(regime_broken)
            """,
            (
                stable_id("PEI_OSC", calibration["ticker"], calibration["sample_size"]),
                calibration["ticker"],
                calibration["behavioral_mean"],
                calibration["support_band"][0],
                calibration["support_band"][1],
                calibration["reload_zone"],
                calibration["trim_zone"],
                calibration["mean_reversion_confidence"],
                calibration["regime_broken"],
                sgt_now(),
            ),
        )
        conn.commit()
        cur.close()
    finally:
        conn.close()
