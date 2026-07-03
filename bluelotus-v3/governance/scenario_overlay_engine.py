#!/usr/bin/env python3
"""
scenario_overlay_engine.py â€” BlueLotus Breaking Catalyst Assimilation Engine v1.0
===================================================================================
Reads:
  - data/governance/approved_operating_truth.json  (governance gate output)
  - data/headlines_live.json                        (news probe output)
  - governance/breaking_catalyst_rules.json         (catalyst polarity rules)

Writes:
  - data/governance/approved_cio_briefing.json      (merged CIO briefing for renderers)

DOCTRINE:
  - Base regime is NEVER overwritten by a breaking catalyst.
  - Scenario overlay supplements, never replaces, governance truth.
  - gold_miner_relief_rally_action is DECONCENTRATION_WINDOW when concentration=CRITICAL.
  - BUY signals are never generated automatically.

Run:
    python governance/scenario_overlay_engine.py

Called by run_v2_pipeline.bat after governance_gate.py, before research_report_generator.py.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# â”€â”€ Paths â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
BASE_DIR      = Path(__file__).resolve().parent.parent
GOVERNANCE_DIR = BASE_DIR / "governance"
DATA_GOV_DIR  = BASE_DIR / "data" / "governance"

APPROVED_TRUTH_PATH  = DATA_GOV_DIR / "approved_operating_truth.json"
HEADLINES_PATH       = BASE_DIR / "data" / "headlines_live.json"
RULES_PATH           = GOVERNANCE_DIR / "breaking_catalyst_rules.json"
BRIEFING_OUTPUT_PATH = DATA_GOV_DIR / "approved_cio_briefing.json"
DATASET_RAW_PATH     = BASE_DIR / "data" / "frontend" / "dataset_raw.json"

# â”€â”€ Monday open scenario definitions (static â€” enriched by overlay engine) â”€â”€â”€
MONDAY_SCENARIOS = {
    "scenario_a": {
        "name": "Relief Rally Confirmed",
        "signals": [
            "Oil down â€” risk premium drains",
            "VIX / VXX down",
            "SPY / QQQ / IWM up",
            "USD/JPY stable",
            "Space / quantum / AI bounce",
            "Gold mixed or flat",
            "Miners may gap up",
        ],
        "cio_implication": (
            "Use strength to reduce concentration. Do not chase open. "
            "Deconcentration window for GOLD_MINERS cluster if AU/NEM gap up."
        ),
    },
    "scenario_b": {
        "name": "Headline Fades",
        "signals": [
            "Oil rebounds â€” risk premium returns",
            "VIX rises",
            "SPY / QQQ fade intraday",
            "Gold rises on resumed safe-haven bid",
            "Miners volatile â€” do not add",
            "Space / quantum fail bounce",
        ],
        "cio_implication": (
            "Preserve cash. Do not add risk. Manual de-risk review remains active. "
            "RISK OFF base regime confirmed."
        ),
    },
    "scenario_c": {
        "name": "BOJ / FOMC Overrides Relief",
        "signals": [
            "Yen strengthens sharply â€” USD/JPY drops",
            "Nikkei weak on yen appreciation",
            "US high beta sells off",
            "Gold may hold but miners sell as equities",
            "Carry unwind pressure",
        ],
        "cio_implication": (
            "Do not rely on Iran relief headline. BOJ/FOMC remains primary macro gate. "
            "Cash is optionality. Do not deploy before macro event window clears."
        ),
    },
}

RISK_OFF_MONDAY_SCENARIOS = {
    "scenario_a": {
        "name": "Hormuz Closure / Peace Deal Failure Confirmed",
        "signals": [
            "Oil up - risk premium returns",
            "VIX / VXX up",
            "SPY / QQQ / IWM fade",
            "High beta and speculative technology sell off",
            "Gold safe-haven bid may rise",
            "Miners remain volatile as equities",
        ],
        "cio_implication": (
            "Preserve cash fortress. Retain hedge. Do not add risk. "
            "Treat scout orders as market detectors only."
        ),
    },
    "scenario_b": {
        "name": "Claim Disputed / Physical Flow Still Open",
        "signals": [
            "Shipping traffic continues",
            "Oil fails to break higher",
            "VXX fades",
            "Credit remains calm",
            "High beta stabilizes but does not confirm risk-on",
        ],
        "cio_implication": (
            "Hold scouts and observe. Do not chase. Relief can be reconsidered only after "
            "shipping flow, oil, VXX, credit, and breadth confirm."
        ),
    },
    "scenario_c": {
        "name": "BOJ / FOMC Amplifies Risk-Off",
        "signals": [
            "Yen strengthens sharply - USD/JPY drops",
            "Nikkei weak on yen appreciation",
            "US high beta sells off",
            "VXX rises while QQQ/IWM fade",
            "Credit stress appears",
        ],
        "cio_implication": (
            "Macro gate dominates. Add risk blocked. Manual de-risk / hedge-profit review only."
        ),
    },
}



# â”€â”€ I/O helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except Exception as exc:
        print(f"[ScenarioOverlay] WARNING: could not read {path}: {exc}")
        return {}


def _save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[ScenarioOverlay] Written: {path}")


# â”€â”€ P/L conflict scanner â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _extract_pnl_conflicts(dataset_raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Scan positions in dataset_raw.json for BROKER_PNL_SOURCE_CONFLICT flags."""
    conflicts: List[Dict[str, Any]] = []
    portfolio = dataset_raw.get("portfolio") or {}
    positions = portfolio.get("positions") or {}
    for ticker, pos in positions.items():
        if isinstance(pos, dict) and pos.get("pnl_integrity_status") == "BROKER_PNL_SOURCE_CONFLICT":
            conflicts.append({
                "ticker": ticker,
                "broker_unrealized": pos.get("unrealized"),
                "computed_unrealized": pos.get("computed_unrealized"),
                "pnl_conflict_delta": pos.get("pnl_conflict_delta"),
            })
    return conflicts


# â”€â”€ Headline extraction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _extract_all_headlines(headlines_payload: Dict[str, Any]) -> List[str]:
    """Flatten all headline text strings from headlines_live.json sources."""
    texts: List[str] = []
    sources = headlines_payload.get("sources") or {}
    for src_id, src in sources.items():
        for item in src.get("items", []):
            text = (item.get("text") or "").strip()
            if text:
                texts.append(text)
    return texts


# â”€â”€ Catalyst detection â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def detect_breaking_catalyst(
    headlines: List[str],
    rules: Dict[str, Any],
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], Optional[str]]:
    """
    Scan headlines against all rules in breaking_catalyst_rules.json.
    Returns (detected, rule_name, rule_dict, matched_headline).
    Priority order: rules are evaluated in dict order; first match wins.
    """
    rule_defs = rules.get("rules", {})
    for rule_name, rule in rule_defs.items():
        keywords: List[str] = rule.get("keywords", [])
        for headline in headlines:
            h_lower = headline.lower()
            for kw in keywords:
                if kw.lower() in h_lower:
                    return True, rule_name, rule, headline
    return False, None, None, None


# â”€â”€ Briefing assembly â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def build_briefing(
    approved_truth: Dict[str, Any],
    headlines_payload: Dict[str, Any],
    rules: Dict[str, Any],
    dataset_raw: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build approved_cio_briefing.json from governance truth + breaking catalyst scan.
    BASE REGIME IS NEVER OVERWRITTEN.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # â”€â”€ Pull canonical governance fields â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    base_regime        = approved_truth.get("regime", "UNKNOWN")
    gov_release        = approved_truth.get("_release_status", "UNKNOWN")
    gov_score          = approved_truth.get("governance_gate_score", "N/A")
    cio_action_base    = approved_truth.get("cio_action", "WAIT / HOLD")
    concentration_status = approved_truth.get("concentration_status", "NORMAL")
    execution_authority  = approved_truth.get("execution_authority", "CIO_ONLY_MANUAL")
    orders_generated     = approved_truth.get("orders_generated", 0)
    routing_enabled      = approved_truth.get("order_routing_enabled", False)

    # â”€â”€ Detect breaking catalyst â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    all_headlines = _extract_all_headlines(headlines_payload)
    detected, rule_name, rule, matched_headline = detect_breaking_catalyst(all_headlines, rules)

    # â”€â”€ Build breaking_catalyst block â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if detected and rule:
        breaking_catalyst = {
            "detected":            True,
            "rule_name":           rule_name,
            "catalyst_type":       rule.get("catalyst_type", rule_name),
            "headline_matched":    matched_headline,
            "polarity":            rule.get("polarity", "UNKNOWN"),
            "confidence":          rule.get("confidence", "MEDIUM"),
            "verification_required": rule.get("verification_required", True),
        }
    else:
        breaking_catalyst = {
            "detected":  False,
            "catalyst_type": None,
            "headline_matched": None,
            "polarity": None,
            "confidence": None,
            "verification_required": False,
        }

    # â”€â”€ Build scenario_overlay block â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    if detected and rule:
        overlay_type   = rule.get("overlay_type", "RELIEF_RALLY_POSSIBLE")
        cio_suffix     = rule.get("cio_action_suffix", "")
        cio_adjusted   = cio_action_base + cio_suffix
        effects        = rule.get("effects", {})
        polarity       = str(rule.get("polarity", "UNKNOWN")).upper()
        is_risk_off_overlay = (
            polarity.startswith("RISK_OFF")
            or overlay_type in {"PEACE_DEAL_FAILURE_RISK", "HORMUZ_CLOSURE_RISK", "OIL_SHOCK_RISK"}
        )

        # Concentration guard â€” NEVER set BUY; CRITICAL â†’ DECONCENTRATION_WINDOW
        conc_rule = rule.get("concentration_critical_rule", {})
        if is_risk_off_overlay:
            gold_miner_action = conc_rule.get("gold_miner_relief_rally_action", "SUPPORT_BIDS_ONLY_REVIEW")
        elif concentration_status == "CRITICAL":
            gold_miner_action = conc_rule.get("gold_miner_relief_rally_action", "DECONCENTRATION_WINDOW")
        else:
            gold_miner_action = "MONITOR"  # non-critical: monitor, still not BUY

        space_override = rule.get("space_sector_override", {})
        if is_risk_off_overlay:
            risk_clearance = "FAILED_PENDING_PHYSICAL_FLOW_VERIFICATION"
            interpretation = (
                f"Peace deal / relief rally is NOT confirmed ({overlay_type}). "
                "Hormuz closure language is a risk-off oil-shock catalyst until physical shipping flow, oil, "
                "VXX, credit, and breadth disprove it. Treat Monday relief rally as blocked/pending verification."
            )
            primary_macro_gate = "Hormuz/oil-shock gate is active; BOJ/FOMC remains secondary macro amplifier."
        else:
            risk_clearance = "NOT_CONFIRMED"
            interpretation = (
                f"Possible Monday relief rally ({overlay_type}). "
                "This does NOT cancel base RISK OFF regime. "
                "Treat as relief catalyst pending Monday live-market confirmation."
            )
            primary_macro_gate = "BOJ/FOMC remains primary macro gate regardless of geopolitical catalyst."

        scenario_overlay = {
            "active":                    True,
            "overlay_type":              overlay_type,
            "risk_clearance":            risk_clearance,
            "cio_action_adjusted":       cio_adjusted,
            "oil_risk_premium":          effects.get("oil_risk_premium", "NEUTRAL"),
            "vix_pressure":              effects.get("vix_pressure", "NEUTRAL"),
            "equity_relief_probability": effects.get("equity_relief_probability", "UNKNOWN"),
            "gold_safe_haven_pressure":  effects.get("gold_safe_haven_pressure", "MIXED"),
            "gold_miner_relief_rally_action": gold_miner_action,
            "space_sector_overlay": {
                "geopolitical_relief": space_override.get("geopolitical_relief", "UNKNOWN"),
                "spcx_liquidity_drain": space_override.get("spcx_liquidity_drain", "UNKNOWN"),
                "net_view":            space_override.get("net_view", "UNKNOWN"),
                "affected_names":      space_override.get("affected_names", []),
                "note": (
                    "SpaceX IPO liquidity-drain risk remains active for smaller space names "
                    "even under geopolitical relief. Treat space sector bounce as unconfirmed."
                ),
            },
            "asset_impact": rule.get("asset_impact", {}),
            "interpretation": interpretation,
            "primary_macro_gate": primary_macro_gate,
        }

        # Monday scenario block is included when overlay is active
        monday_open_scenario = RISK_OFF_MONDAY_SCENARIOS.copy() if is_risk_off_overlay else MONDAY_SCENARIOS.copy()

    else:
        scenario_overlay = {
            "active":           False,
            "overlay_type":     None,
            "risk_clearance":   "N/A",
            "cio_action_adjusted": cio_action_base,
        }
        monday_open_scenario = {}
        cio_adjusted = cio_action_base

    # â”€â”€ P/L integrity (scan live dataset positions for conflicts) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    _pnl_conflicts = _extract_pnl_conflicts(dataset_raw or {})
    pnl_integrity = {
        "conflicts": _pnl_conflicts,
        "conflict_count": len(_pnl_conflicts),
        "status": "CONFLICT_DETECTED" if _pnl_conflicts else "OK",
    }

    # â”€â”€ Final briefing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    briefing: Dict[str, Any] = {
        "generated_at":            now_iso,
        "engine_version":          "scenario_overlay_engine v1.0",
        # â”€â”€ Governance truth (passed through verbatim â€” renderers must not recalculate) â”€â”€
        "base_regime":             base_regime,          # NEVER overwritten by overlay
        "governance_release_status": gov_release,
        "governance_score":        gov_score,
        "cio_action_base":         cio_action_base,
        "cio_action_final":        cio_adjusted,
        "execution_authority":     execution_authority,
        "orders_generated":        orders_generated,
        "order_routing_enabled":   routing_enabled,
        "concentration_status":    concentration_status,
        # â”€â”€ Breaking catalyst â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "breaking_catalyst":       breaking_catalyst,
        # â”€â”€ Scenario overlay â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "scenario_overlay":        scenario_overlay,
        # â”€â”€ Monday scenarios (only present when overlay active) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "monday_open_scenario":    monday_open_scenario,
        # â”€â”€ P/L integrity â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "pnl_integrity":           pnl_integrity,
        # â”€â”€ Headlines window used â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        "headlines_window": {
            "generated_at": headlines_payload.get("generated_at", "UNKNOWN"),
            "window_min":   headlines_payload.get("window_min", 60),
            "total_scanned": len(all_headlines),
        },
    }
    return briefing


# â”€â”€ Entry point â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def run_scenario_overlay() -> Dict[str, Any]:
    print("[ScenarioOverlay] â”€â”€ BlueLotus Scenario Overlay Engine v1.0 â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€")

    approved_truth    = _load_json(APPROVED_TRUTH_PATH)
    headlines_payload = _load_json(HEADLINES_PATH)
    rules             = _load_json(RULES_PATH)
    dataset_raw       = _load_json(DATASET_RAW_PATH)

    if not approved_truth:
        print("[ScenarioOverlay] WARNING: approved_operating_truth.json not found â€” "
              "run governance_gate.py first. Writing minimal briefing.")

    if not rules:
        print("[ScenarioOverlay] WARNING: breaking_catalyst_rules.json not found â€” "
              "no catalyst detection possible.")

    briefing = build_briefing(approved_truth, headlines_payload, rules, dataset_raw)

    # â”€â”€ Summary log â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    cat = briefing["breaking_catalyst"]
    ov  = briefing["scenario_overlay"]
    pnl = briefing["pnl_integrity"]
    print(f"[ScenarioOverlay]   Base regime          : {briefing['base_regime']}")
    print(f"[ScenarioOverlay]   Governance release   : {briefing['governance_release_status']}")
    print(f"[ScenarioOverlay]   Breaking catalyst    : {cat['detected']} / {cat.get('catalyst_type','â€”')}")
    if cat["detected"]:
        print(f"[ScenarioOverlay]   Matched headline     : {str(cat.get('headline_matched',''))[:80]}")
        print(f"[ScenarioOverlay]   Polarity             : {cat.get('polarity','â€”')}")
        print(f"[ScenarioOverlay]   Overlay type         : {ov.get('overlay_type','â€”')}")
        print(f"[ScenarioOverlay]   CIO action adjusted  : {ov.get('cio_action_adjusted','â€”')}")
        print(f"[ScenarioOverlay]   Gold miner action    : {ov.get('gold_miner_relief_rally_action','â€”')}")
        print(f"[ScenarioOverlay]   Space net view       : "
              f"{ov.get('space_sector_overlay',{}).get('net_view','â€”')}")
        print(f"[ScenarioOverlay]   Monday scenarios     : {list(briefing['monday_open_scenario'].keys())}")
    print(f"[ScenarioOverlay]   Headlines scanned    : {briefing['headlines_window']['total_scanned']}")
    print(f"[ScenarioOverlay]   P/L integrity        : {pnl['status']} / {pnl['conflict_count']} conflict(s)")

    _save_json(BRIEFING_OUTPUT_PATH, briefing)
    print("[ScenarioOverlay] â”€â”€ DONE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€")
    return briefing


if __name__ == "__main__":
    try:
        run_scenario_overlay()
    except Exception as exc:
        print(f"[ScenarioOverlay] FATAL: {exc}", file=sys.stderr)
        import traceback; traceback.print_exc()
        sys.exit(1)
