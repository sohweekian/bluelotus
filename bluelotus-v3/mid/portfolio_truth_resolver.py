"""
BlueLotus V3 — Portfolio Truth Resolver
Resolves the canonical portfolio source for report rendering.

Precedence (highest to lowest):
  1. BROKER_LIVE — live broker snapshot (freshest)
  2. DASHBOARD_LIVE — portfolio_live.json (pushed per pipeline cycle)
  3. DATASET_PORTFOLIO — dataset_raw.json portfolio section
  4. ARCHIVE — last known / stale

Source is labelled explicitly. Stale sources are never promoted to LIVE.

NO_HARDCODING_DOCTRINE: All thresholds configurable here at module top.
CIO_ONLY_MANUAL: This module provides data only — no execution authority.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── Freshness thresholds (minutes) ─────────────────────────────────────────
FRESHNESS_LIVE_MIN   = 30     # < 30 min → LIVE
FRESHNESS_FRESH_MIN  = 120    # < 2 h   → FRESH
# >= FRESHNESS_FRESH_MIN → STALE / ARCHIVE

# ── Mismatch detection thresholds ──────────────────────────────────────────
CASH_WARN_DELTA  = 500.0     # cash Δ > $500   → WARNING
CASH_FAIL_DELTA  = 5000.0    # cash Δ > $5,000 → FAIL
MV_WARN_DELTA    = 1000.0    # MV Δ > $1,000   → WARNING
MV_FAIL_DELTA    = 5000.0    # MV Δ > $5,000   → FAIL
CASH_PCT_WARN    = 5.0       # cash% Δ > 5%    → WARNING
CASH_PCT_FAIL    = 20.0      # cash% Δ > 20%   → FAIL

# ── Safety constants (immutable) ────────────────────────────────────────────
_EXECUTION_AUTHORITY    = "CIO_ONLY_MANUAL"
_ORDER_ROUTING_ENABLED  = False
_LLM_ORDER_GENERATION   = False


def _age_minutes(ts_str: str | None) -> float:
    """Return age in minutes of an ISO-8601 timestamp string. Returns 9999 if unparseable."""
    if not ts_str:
        return 9999.0
    try:
        ts = datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - ts).total_seconds() / 60
    except Exception:
        return 9999.0


def _extract_cash(d: dict) -> float:
    """Extract cash value from various portfolio dict shapes."""
    for key in ("cash", "cash_value", "cash_fmt"):
        v = d.get(key)
        if v is not None:
            try:
                return float(str(v).replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                pass
    return 0.0


def _extract_market_value(d: dict) -> float:
    """Extract total market value from various portfolio dict shapes."""
    for key in ("market_value", "market_val", "total_value", "portfolio_value"):
        v = d.get(key)
        if v is not None:
            try:
                return float(str(v).replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                pass
    return 0.0


def resolve(
    dataset:             dict,
    portfolio_live_path: "Path | str | None" = None,
    broker_snapshot:     Optional[dict]       = None,
) -> dict:
    """
    Resolve canonical portfolio truth from all available sources.

    Returns a dict with:
      source_name        — winning source name (BROKER_LIVE / DASHBOARD_LIVE / etc.)
      source_age_minutes — age of winning source in minutes
      freshness          — LIVE / FRESH / STALE
      confidence         — HIGH / MEDIUM / LOW
      data               — the portfolio data dict from the winning source
      label              — multi-line human-readable label for CIO display
      mismatch_detail    — None or string describing mismatch
      all_sources        — list of all sources considered with their ages
      cio_action_cap     — "REVIEW ONLY" if stale, else None
      execution_authority — always "CIO_ONLY_MANUAL"
    """
    portfolio_live_path = Path(
        portfolio_live_path
        or r"C:\bluelotus3\data\portfolio_live\portfolio_live.json"
    )

    sources: list[dict] = []

    # ── Source 1: Broker snapshot (if provided) ─────────────────────────────
    if broker_snapshot and isinstance(broker_snapshot, dict):
        age = _age_minutes(broker_snapshot.get("generated_at"))
        sources.append({
            "priority": 1,
            "name":     "BROKER_LIVE",
            "data":     broker_snapshot,
            "age_min":  age,
        })

    # ── Source 2: Dashboard portfolio_live.json ─────────────────────────────
    if portfolio_live_path.exists():
        try:
            pl = json.loads(portfolio_live_path.read_text(encoding="utf-8"))
            age = _age_minutes(pl.get("generated_at"))
            sources.append({
                "priority": 2,
                "name":     "DASHBOARD_LIVE",
                "data":     pl,
                "age_min":  age,
            })
        except Exception:
            pass

    # ── Source 3: Dataset portfolio section ─────────────────────────────────
    ds_port = dataset.get("portfolio") or {}
    ds_ts   = (dataset.get("meta") or {}).get("generated_at")
    age     = _age_minutes(ds_ts)
    sources.append({
        "priority": 3,
        "name":     "DATASET_PORTFOLIO",
        "data":     ds_port,
        "age_min":  age,
    })

    # ── Pick best source (lowest age, then lowest priority number) ───────────
    if not sources:
        # Fallback: no sources at all
        return {
            "source_name":        "ARCHIVE",
            "source_age_minutes": 9999.0,
            "freshness":          "STALE",
            "confidence":         "LOW",
            "data":               {},
            "label":              "PORTFOLIO SOURCE: ARCHIVE\nPORTFOLIO SOURCE: ARCHIVE / STALE / LAST_KNOWN\nLIVE PORTFOLIO CONFIDENCE: LOW\nCIO ACTION CAP: REVIEW ONLY — DO NOT TREAT AS LIVE BROKER TRUTH",
            "mismatch_detail":    None,
            "all_sources":        [],
            "cio_action_cap":     "REVIEW ONLY",
            "execution_authority": _EXECUTION_AUTHORITY,
        }

    best = min(sources, key=lambda s: (s["age_min"], s["priority"]))
    age_min = best["age_min"]

    # ── Freshness classification ─────────────────────────────────────────────
    if age_min < FRESHNESS_LIVE_MIN:
        freshness  = "LIVE"
        confidence = "HIGH"
    elif age_min < FRESHNESS_FRESH_MIN:
        freshness  = "FRESH"
        confidence = "MEDIUM"
    else:
        freshness  = "STALE"
        confidence = "LOW"

    # ── Mismatch detection (compare top two sources if available) ────────────
    mismatch_detail: str | None = None
    if len(sources) >= 2:
        s1 = sources[0]["data"]
        s2 = sources[1]["data"]
        cash1  = _extract_cash(s1)
        cash2  = _extract_cash(s2)
        delta  = abs(cash1 - cash2)
        if delta > CASH_WARN_DELTA:
            severity = "FAIL" if delta > CASH_FAIL_DELTA else "WARNING"
            mismatch_detail = (
                f"Cash {severity}: {sources[0]['name']} ${cash1:,.0f} vs "
                f"{sources[1]['name']} ${cash2:,.0f} (Δ${delta:,.0f})"
            )

    # ── Build CIO label ──────────────────────────────────────────────────────
    label_parts = [f"PORTFOLIO SOURCE: {best['name']} (age {age_min:.0f} min)"]
    if freshness == "STALE":
        label_parts += [
            "PORTFOLIO SOURCE: ARCHIVE / STALE / LAST_KNOWN",
            "LIVE PORTFOLIO CONFIDENCE: LOW",
            "CIO ACTION CAP: REVIEW ONLY — DO NOT TREAT AS LIVE BROKER TRUTH",
        ]
    else:
        label_parts.append(f"PORTFOLIO FRESHNESS: {freshness} | CONFIDENCE: {confidence}")
    if mismatch_detail:
        label_parts.append(f"LIVE/REPORT PORTFOLIO MISMATCH DETECTED — {mismatch_detail}")

    return {
        "source_name":        best["name"],
        "source_age_minutes": round(age_min, 1),
        "freshness":          freshness,
        "confidence":         confidence,
        "data":               best["data"],
        "label":              "\n".join(label_parts),
        "mismatch_detail":    mismatch_detail,
        "all_sources":        [
            {"name": s["name"], "age_min": round(s["age_min"], 1)}
            for s in sources
        ],
        "cio_action_cap":     "REVIEW ONLY" if freshness == "STALE" else None,
        "execution_authority": _EXECUTION_AUTHORITY,
    }
