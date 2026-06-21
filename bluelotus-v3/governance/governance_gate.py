#!/usr/bin/env python3
"""
BlueLotus V2 — Governance Gate
================================
Reads dataset_raw.json → applies governance_config.json → produces:
  - data/governance/approved_operating_truth.json  (single source of truth for all renderers)
  - data/governance/governance_audit.json          (full audit trail)
  - data/governance/release_status.txt             (APPROVED / APPROVED_WITH_WARNINGS / BLOCKED)

Renderers (TXT / Word / Excel) must consume approved_operating_truth.json.
No renderer may recalculate any contract field.

NOT touching: moomoo_trader.py, broker extraction, order routing, execution safety,
              CIO_ONLY_MANUAL doctrine, live batch scheduler, or any .bat file.
"""

from __future__ import annotations

import json
import math
import sys
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
GOVERNANCE_DIR = PROJECT_ROOT / "governance"
DATA_GOV_DIR   = PROJECT_ROOT / "data" / "governance"
DATASET_PATH   = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
GOV_CONFIG_PATH = GOVERNANCE_DIR / "governance_config.json"
CONTRACT_PATH   = GOVERNANCE_DIR / "report_contract.json"
TRUTH_PATH      = DATA_GOV_DIR / "approved_operating_truth.json"
AUDIT_PATH      = DATA_GOV_DIR / "governance_audit.json"
STATUS_PATH     = DATA_GOV_DIR / "release_status.txt"

VERSION = "1.0"


# ─── helpers ──────────────────────────────────────────────────────────────────

def sf(v: Any, default: float = 0.0) -> float:
    try:
        out = float(str(v).replace("N/A", "0").replace("--", "0") or 0)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def load_json(path: Path) -> Dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ─── concentration computation ────────────────────────────────────────────────

def compute_concentration(dataset: Dict, cfg: Dict) -> Dict:
    port = dataset.get("portfolio", {})
    positions = port.get("positions") or {}
    total_assets = sf(port.get("total_assets") or port.get("total_value"))

    def pos_weight(p: Dict) -> float:
        w = sf(p.get("weight"))
        if not w and total_assets:
            w = sf(p.get("mkt_val") or p.get("market_val") or p.get("market_value")) / total_assets
        return w

    holdings = sorted(
        [(t, pos_weight(p)) for t, p in positions.items()
         if isinstance(p, dict) and pos_weight(p) > 0],
        key=lambda x: x[1], reverse=True
    )

    hhi    = sum(w ** 2 for _, w in holdings) if holdings else 0.0
    top3w  = sum(w for _, w in holdings[:3]) if holdings else 0.0
    lar_t  = holdings[0][0] if holdings else ""
    lar_w  = holdings[0][1] if holdings else 0.0

    cluster_defs = cfg.get("cluster_definitions", {})
    clusters = {
        c: sum(w for t, w in holdings if t.upper() in {m.upper() for m in members})
        for c, members in cluster_defs.items()
        if sum(1 for t, _ in holdings if t.upper() in {m.upper() for m in members}) >= 2
    }

    thr = cfg.get("concentration_severity_thresholds", {})
    cluster_max_name = max(clusters, key=clusters.get) if clusters else None
    cluster_max_val  = clusters[cluster_max_name] if cluster_max_name else 0.0

    def cluster_sev(v: float) -> str:
        if v >= thr.get("CRITICAL", {}).get("cluster_gte", 0.65):
            return "CRITICAL"
        if v >= thr.get("HIGH", {}).get("cluster_gte", 0.50):
            return "HIGH"
        if v >= thr.get("ELEVATED", {}).get("cluster_gte", 0.35):
            return "ELEVATED"
        return "NORMAL"

    cluster_status = {
        c: {"severity": cluster_sev(v), "weight": round(v, 4), "weight_pct": f"{v:.0%}"}
        for c, v in clusters.items()
    }

    # Base from HHI / single-name
    hhi_crit = thr.get("hhi_critical", 0.35)
    hhi_high = thr.get("hhi_high", 0.20)
    hhi_elev = thr.get("hhi_elevated", 0.12)
    sn_crit  = thr.get("single_name_critical", 0.40)
    sn_high  = thr.get("single_name_high", 0.30)
    sn_elev  = thr.get("single_name_elevated", 0.20)

    if hhi > hhi_crit or lar_w > sn_crit:
        base_status = "CRITICAL"
    elif hhi > hhi_high or lar_w > sn_high:
        base_status = "HIGH"
    elif hhi > hhi_elev or lar_w > sn_elev:
        base_status = "ELEVATED"
    else:
        base_status = "NORMAL"

    # Escalate via cluster severity
    sev_order = {"NORMAL": 0, "ELEVATED": 1, "HIGH": 2, "CRITICAL": 3}
    top_cluster_sev = cluster_sev(cluster_max_val) if cluster_max_name else None
    if top_cluster_sev and sev_order.get(top_cluster_sev, 0) > sev_order.get(base_status, 0):
        concentration_status = top_cluster_sev
    else:
        concentration_status = base_status

    return {
        "concentration_status": concentration_status,
        "hhi": round(hhi, 4),
        "top3_weight": round(top3w, 4),
        "largest_position_ticker": lar_t,
        "largest_position_weight": round(lar_w, 4),
        "cluster_status": cluster_status,
        "cluster_max_name": cluster_max_name,
        "cluster_max_val": round(cluster_max_val, 4),
        "holdings": [(t, round(w, 4)) for t, w in holdings],
    }


# ─── gold thesis tracker ──────────────────────────────────────────────────────

def compute_gold_thesis(dataset: Dict) -> Dict:
    """
    Compute gold thesis tracker from dataset prices.
    Mirrors build_gold_thesis_tracker() in research_report_generator.py.
    Returns dict with status, score, key_metrics.
    """
    try:
        sys.path.insert(0, str(PROJECT_ROOT / "research"))
        from research_report_generator import build_gold_thesis_tracker
        gtt = build_gold_thesis_tracker(dataset)
        return gtt
    except Exception as e:
        # Fallback: lightweight inline computation
        return _gold_thesis_fallback(dataset, str(e))


def _gold_thesis_fallback(dataset: Dict, error: str) -> Dict:
    """Minimal gold thesis status from prices when import fails."""
    prices_raw = dataset.get("live_prices", {})
    if isinstance(prices_raw, dict) and "prices" in prices_raw:
        prices = prices_raw["prices"]
    else:
        prices = prices_raw

    def chg(t: str) -> float:
        d = prices.get(t) or prices.get(f"US.{t}", {})
        if isinstance(d, dict):
            return sf(d.get("chg_pct") or d.get("change_pct") or d.get("change_rate"))
        return 0.0

    gld, slv  = chg("GLD"), chg("SLV")
    gdx, gdxj = chg("GDX"), chg("GDXJ")
    au, nem   = chg("AU"),  chg("NEM")
    spy, vxx  = chg("SPY"), chg("VXX")
    uup, tlt  = chg("UUP"), chg("TLT")

    checks_pass = sum([
        gld > 0 or gld > -0.5,           # gold stabilizes
        slv >= gld,                        # silver confirms
        gdx > gld or gdxj > gld,          # miners outperform gold
        au > gdx or nem > gdx,             # senior miners outperform index
        tlt > -0.5,                        # yields stable
        uup <= 0.3,                        # dollar not surging
        True,                              # oil risk (simplified)
        not (gld > -0.5 and (gdx <= -2 or gdxj <= -2)),  # no panic liquidation
    ])
    score = round(checks_pass / 8, 2)
    status = "CONFIRMING" if score >= 0.75 else "WATCH" if score >= 0.50 else "WEAKENING"
    return {
        "status": status,
        "score": score,
        "confidence": "HIGH" if score >= 0.75 else "MEDIUM",
        "fallback": True,
        "fallback_error": error,
        "key_metrics": {
            "gld_change_pct": gld, "slv_change_pct": slv,
            "gdx_vs_gld_spread": gdx - gld, "au_vs_gdx_spread": au - gdx,
            "spy_change_pct": spy, "vxx_change_pct": vxx,
            "uup_change_pct": uup, "tlt_change_pct": tlt,
        },
    }


# ─── sentiment relevance ──────────────────────────────────────────────────────

def check_sentiment_relevance(ticker: str, headline: str, cfg: Dict) -> bool:
    """Return True if headline is directly relevant to the ticker."""
    aliases_map = cfg.get("sentiment_relevance_rules", {}).get("ticker_aliases", {})
    aliases = aliases_map.get(ticker.upper(), {ticker.upper()})
    if isinstance(aliases, list):
        aliases = set(a.upper() for a in aliases)
    elif isinstance(aliases, set):
        aliases = {a.upper() for a in aliases}

    headline_upper = headline.upper()
    for alias in aliases:
        if alias in headline_upper:
            return True
    return False


def _filter_headlines_by_alias(ticker: str, headlines: List[str], cfg: Dict) -> Tuple[List[str], List[str]]:
    """
    Split a headline list into (clean, dirty) based on alias matching.
    clean  = headline directly mentions ticker or an approved alias
    dirty  = headline has no mention of the ticker/company (must not appear in CIO tape)
    """
    aliases_map = cfg.get("sentiment_relevance_rules", {}).get("ticker_aliases", {})
    aliases = aliases_map.get(ticker.upper(), {ticker.upper()})
    if isinstance(aliases, list):
        aliases = set(a.upper() for a in aliases)
    elif isinstance(aliases, set):
        aliases = {a.upper() for a in aliases}
    else:
        aliases = {ticker.upper()}

    clean, dirty = [], []
    for h in headlines:
        h_up = str(h).upper()
        if any(a in h_up for a in aliases):
            clean.append(h)
        else:
            dirty.append(h)
    return clean, dirty


def compute_sentiment_relevance(dataset: Dict, cfg: Dict) -> Dict[str, Dict]:
    """
    For every ticker in ticker_sentiment, determine PASS or DISCARD.

    Priority order:
    1. Trust pre-computed dirty_headlines from export_dataset_raw.py (R6 headline-level patch).
       If that field exists, the export layer already split clean vs dirty.
    2. If dirty_headlines is missing, apply governance gate alias-based headline filtering now
       (governance gate fallback — ensures enforcement even before export_dataset_raw.py reruns).
    3. Ticker-level relevance check: if ticker is DISCARD, all headlines are dirty.
    """
    ticker_sentiment = dataset.get("ticker_sentiment", {})
    discard_label = cfg["sentiment_relevance_rules"]["discard_label"]
    pass_label    = cfg["sentiment_relevance_rules"]["pass_label"]
    result = {}

    for ticker, sent in ticker_sentiment.items():
        if not isinstance(sent, dict):
            continue

        # ── Ticker-level relevance ──
        existing_status = sent.get("sentiment_relevance_status")
        if existing_status == discard_label or sent.get("discarded_for_institutional_sentiment"):
            # Entire ticker discarded — all headlines are dirty
            all_hl = sent.get("headlines") or []
            result[ticker] = {
                **sent,
                "sentiment_relevance_status": discard_label,
                "discarded_for_institutional_sentiment": True,
                "headlines": [],
                "dirty_headlines": all_hl,
                "clean_headline_count": 0,
                "dirty_headline_count": len(all_hl),
                "relevance_source": existing_status and "export_dataset_raw" or "governance_gate_fallback",
            }
            continue

        # ── Headline-level filtering ──
        raw_headlines = sent.get("headlines") or []

        if sent.get("dirty_headlines") is not None:
            # export_dataset_raw.py already split the headlines — trust it
            clean_hl = raw_headlines          # already cleaned by export layer
            dirty_hl = sent.get("dirty_headlines") or []
            relevance_source = "export_dataset_raw"
        else:
            # Governance gate fallback: apply alias-based headline filter now
            clean_hl, dirty_hl = _filter_headlines_by_alias(ticker, raw_headlines, cfg)
            relevance_source = "governance_gate_fallback"

        # Ticker passes if it has at least one clean headline OR was previously marked PASS
        is_relevant = bool(clean_hl) or existing_status == pass_label or (
            not raw_headlines and existing_status not in (None, discard_label)
        )
        computed_status = pass_label if is_relevant else discard_label

        result[ticker] = {
            **sent,
            "sentiment_relevance_status": computed_status,
            "discarded_for_institutional_sentiment": not is_relevant,
            "headlines": clean_hl,
            "dirty_headlines": dirty_hl,
            "clean_headline_count": len(clean_hl),
            "dirty_headline_count": len(dirty_hl),
            "relevance_source": relevance_source,
        }
    return result


# ─── execution safety ─────────────────────────────────────────────────────────

def check_execution_safety(dataset: Dict, cfg: Dict) -> Dict:
    execution   = dataset.get("execution", {})
    det_ops     = dataset.get("deterministic_operators", {})
    cio_dec_j   = dataset.get("cio_decision_journal", {})
    rules       = cfg.get("execution_safety_rules", {})

    authority   = (execution.get("execution_authority") or
                   det_ops.get("execution_authority") or "UNKNOWN")
    routing_raw = execution.get("order_routing_enabled",
                  det_ops.get("order_routing_enabled", True))
    routing     = bool(routing_raw)
    generated   = int(sf(det_ops.get("orders_generated",
                   execution.get("orders_generated", 0))))

    required_authority = rules.get("execution_authority_must_equal", "CIO_ONLY_MANUAL")
    required_routing   = rules.get("order_routing_enabled_must_equal", False)
    required_generated = rules.get("orders_generated_must_equal", 0)

    violations = []
    if authority != required_authority:
        violations.append(f"execution_authority={authority} (required {required_authority})")
    if routing != required_routing:
        violations.append(f"order_routing_enabled={routing} (required {required_routing})")
    if generated != required_generated:
        violations.append(f"orders_generated={generated} (required {required_generated})")

    return {
        "execution_authority": authority,
        "order_routing_enabled": routing,
        "orders_generated": generated,
        "cio_only_manual_confirmed": authority == required_authority,
        "execution_safe": len(violations) == 0,
        "violations": violations,
    }


# ─── CIO plan vs broker ───────────────────────────────────────────────────────

def check_cio_plan_vs_broker(dataset: Dict, cfg: Dict) -> Dict:
    orders_layer = dataset.get("orders", {})
    open_orders  = orders_layer.get("open_orders", [])
    prices_raw   = dataset.get("live_prices", {})
    if isinstance(prices_raw, dict) and "prices" in prices_raw:
        prices = prices_raw["prices"]
    else:
        prices = prices_raw

    miner_tickers = {t.upper() for t in cfg.get("cio_plan_vs_broker_rules", {}).get("miner_tickers", ["AU", "NEM"])}
    miner_sell_orders = [
        o for o in open_orders
        if isinstance(o, dict) and o.get("ticker", "").upper() in miner_tickers
        and o.get("trd_side", "").upper() == "SELL"
    ]

    infeasible = []
    for o in miner_sell_orders:
        ticker = o.get("ticker", "").upper()
        limit_px = sf(o.get("price"))
        current_px_data = prices.get(ticker) or prices.get(f"US.{ticker}", {})
        if isinstance(current_px_data, dict):
            current_px = sf(current_px_data.get("last_price") or current_px_data.get("price") or 0)
        else:
            current_px = sf(current_px_data)
        if limit_px > 0 and current_px > 0 and limit_px > current_px:
            infeasible.append({
                "ticker": ticker,
                "trd_side": "SELL",
                "order_status": o.get("order_status"),
                "qty": o.get("qty"),
                "limit_price": limit_px,
                "current_price": current_px,
                "executable_now": False,
                "reason": f"limit {limit_px} above current {current_px}",
            })

    feasibility = cfg["cio_plan_vs_broker_rules"]["not_guaranteed_label"] if infeasible else "LIKELY"
    manual_required = cfg["cio_plan_vs_broker_rules"]["manual_action_label"] if infeasible else "NO"
    warning = cfg["cio_plan_vs_broker_rules"]["standard_feasibility_warning"] if infeasible else ""

    return {
        "feasibility": feasibility,
        "manual_cio_action_required": manual_required,
        "infeasible_orders": infeasible,
        "infeasible_count": len(infeasible),
        "miner_sell_orders_total": len(miner_sell_orders),
        "warning": warning,
    }


# ─── gold reconciliation ──────────────────────────────────────────────────────

def build_gold_reconciliation(gtt_status: str, binary_flag: Optional[bool], cfg: Dict) -> Dict:
    rules = cfg.get("gold_thesis_reconciliation_rules", {})
    confirming_states = set(rules.get("tracker_confirming_states", ["CONFIRMING", "STRENGTHENING"]))
    std_text = rules.get("required_reconciliation_text", "")

    if gtt_status in confirming_states and not binary_flag:
        reconciliation = std_text
        reconciliation_type = "TRACKER_CONFIRMING_BINARY_FALSE"
        needs_reconciliation = True
    elif gtt_status in confirming_states and binary_flag:
        reconciliation = "Tracker and binary flag both confirm gold thesis. Fully consistent."
        reconciliation_type = "BOTH_CONFIRMING"
        needs_reconciliation = False
    else:
        reconciliation = f"Review tracker checks above for thesis condition details. Tracker={gtt_status}."
        reconciliation_type = "NEUTRAL"
        needs_reconciliation = False

    return {
        "gold_reconciliation_explanation": reconciliation,
        "reconciliation_type": reconciliation_type,
        "needs_reconciliation": needs_reconciliation,
    }


# ─── sentiment hygiene gate ──────────────────────────────────────────────────

def compute_sentiment_hygiene_gate(sentiment_with_relevance: Dict, portfolio_tickers: set, cfg: Dict) -> Dict:
    """
    Inspect headline-level sentiment hygiene across all tickers.

    Rules (from governance work order):
      dirty_count = 0                          → PASS   (no impact on release)
      dirty_count > 0, all excluded from tape  → WARNING (APPROVED_WITH_WARNINGS)
      dirty_count > 0, any appear in CIO tape  → FAIL   (BLOCKED)

    'Appears in CIO tape' = portfolio ticker whose dirty headlines were NOT filtered out.
    After the export_dataset_raw headline-level patch, dirty_headlines are removed from
    the display list, so tape contamination only happens if filtering was bypassed.
    """
    aliases_map = cfg.get("sentiment_relevance_rules", {}).get("ticker_aliases", {})
    discard_label = cfg["sentiment_relevance_rules"]["discard_label"]

    total_dirty_headlines = 0
    dirty_ticker_count    = 0
    portfolio_dirty_headlines = 0
    examples_blocked: List[str] = []
    examples_failed:  List[str] = []
    dirty_detail: List[Dict]    = []

    for ticker, sent in sentiment_with_relevance.items():
        if not isinstance(sent, dict):
            continue

        # Case A: entire ticker discarded — all its headlines are dirty
        overall_status = sent.get("sentiment_relevance_status", "")
        if overall_status == discard_label:
            main_hl = sent.get("headline") or sent.get("title") or ""
            dirty_count_for_ticker = max(1, len(sent.get("headlines_raw") or sent.get("headlines") or [main_hl]))
            total_dirty_headlines += dirty_count_for_ticker
            dirty_ticker_count    += 1
            if ticker in portfolio_tickers:
                portfolio_dirty_headlines += dirty_count_for_ticker
                examples_failed.append(f"{ticker} (DISCARD): {main_hl[:80]}")
            else:
                examples_blocked.append(f"{ticker} (DISCARD, non-portfolio): {main_hl[:60]}")
            dirty_detail.append({
                "ticker": ticker, "type": "TICKER_DISCARD",
                "dirty_count": dirty_count_for_ticker,
                "in_portfolio": ticker in portfolio_tickers,
            })
            continue

        # Case B: ticker is PASS overall but has headline-level dirty entries
        dirty_headlines = sent.get("dirty_headlines") or []
        if dirty_headlines:
            dirty_count_for_ticker = len(dirty_headlines)
            total_dirty_headlines += dirty_count_for_ticker
            dirty_ticker_count    += 1
            # True tape contamination = dirty headline appears IN the display (headlines) list.
            # After headline-level filtering (either by export_dataset_raw or governance gate fallback),
            # dirty_headlines are quarantined and NOT in the display list.
            # Only flag as contaminated if a dirty headline actually leaked into the display list.
            display_headlines = set(str(h) for h in (sent.get("headlines") or []))
            leaked = [h for h in dirty_headlines if str(h) in display_headlines]
            tape_contaminated = bool(ticker in portfolio_tickers and leaked)
            for h in dirty_headlines[:2]:
                sample = f"{ticker}: {str(h)[:80]}"
                if tape_contaminated:
                    examples_failed.append(sample)
                else:
                    examples_blocked.append(sample)
            dirty_detail.append({
                "ticker": ticker, "type": "HEADLINE_LEVEL_DIRTY",
                "dirty_count": dirty_count_for_ticker,
                "clean_count": len(display_headlines),
                "tape_contaminated": tape_contaminated,
                "in_portfolio": ticker in portfolio_tickers,
                "sample_dirty": [str(h)[:80] for h in dirty_headlines[:2]],
            })
            if ticker in portfolio_tickers:
                portfolio_dirty_headlines += dirty_count_for_ticker

    # Determine status
    tape_contamination_count = len(examples_failed)
    if total_dirty_headlines == 0:
        status       = "PASS"
        release_impact = "no_impact"
    elif tape_contamination_count > 0:
        status       = "FAIL"
        release_impact = "BLOCKED"
    else:
        # Dirty headlines exist but they've all been filtered out of display
        status       = "WARNING"
        release_impact = "APPROVED_WITH_WARNINGS"

    return {
        "status":                  status,
        "dirty_count":             total_dirty_headlines,
        "dirty_ticker_count":      dirty_ticker_count,
        "discarded_count":         sum(1 for s in sentiment_with_relevance.values()
                                       if isinstance(s, dict) and s.get("sentiment_relevance_status") == discard_label),
        "allowed_count":           sum(1 for s in sentiment_with_relevance.values()
                                       if isinstance(s, dict) and s.get("sentiment_relevance_status") != discard_label),
        "portfolio_dirty_count":   portfolio_dirty_headlines,
        "tape_contamination_count": tape_contamination_count,
        "examples_blocked":        examples_blocked[:5],
        "examples_failed":         examples_failed[:5],
        "dirty_detail":            dirty_detail,
        "release_impact":          release_impact,
    }


# ─── governance gate score ────────────────────────────────────────────────────

def compute_governance_gate_score(exec_safety: Dict, hygiene: Dict, conc: Dict,
                                   reconciliation: Dict, cfg: Dict,
                                   pnl_conflicts: Optional[List[str]] = None,
                                   pnl_unflagged: Optional[List[str]] = None) -> Dict:
    """
    Compute a 0–100 governance gate score.
      Base: 100
      dirty_sentiment_in_cio_tape  → BLOCKED (automatic)
      execution_safety_fail        → BLOCKED (automatic)
      sentiment_hygiene FAIL       → -15
      sentiment_hygiene WARNING    → -5
      renderer_mismatch            → -10 each (future use)
      concentration_mismatch       → -10
      pnl_conflict_unflagged       → BLOCKED
      pnl_conflict_flagged         → -5
    """
    score = 100
    deductions: List[str] = []
    blocking:   List[str] = []

    if not exec_safety.get("execution_safe"):
        blocking.append("EXECUTION_SAFETY_BREACH")

    if hygiene.get("status") == "FAIL":
        blocking.append("DIRTY_SENTIMENT_IN_CIO_TAPE")
        score -= 15
        deductions.append("sentiment_hygiene_FAIL: -15")
    elif hygiene.get("status") == "WARNING":
        score -= 5
        deductions.append("sentiment_hygiene_WARNING: -5")

    if conc.get("cluster_max_val", 0) >= 0.65 and conc.get("concentration_status") != "CRITICAL":
        score -= 10
        deductions.append("concentration_threshold_mismatch: -10")

    # ── P/L arithmetic integrity ──────────────────────────────────────────────
    _pnl_unflagged = pnl_unflagged or []
    _pnl_conflicts = pnl_conflicts or []
    if _pnl_unflagged:
        blocking.append(f"PNL_CONFLICT_UNFLAGGED({','.join(_pnl_unflagged[:3])})")
    elif _pnl_conflicts:
        _n = len(_pnl_conflicts)
        score -= 5
        deductions.append(f"pnl_arithmetic_conflict_flagged({_n}_positions): -5")

    score = max(0, min(100, score))
    _pnl_gate_ok = not _pnl_unflagged
    passed_gates = [
        "execution_safety" if exec_safety.get("execution_safe") else None,
        "sentiment_hygiene" if hygiene.get("status") == "PASS" else None,
        "concentration_threshold" if not (conc.get("cluster_max_val", 0) >= 0.65 and conc.get("concentration_status") != "CRITICAL") else None,
        "gold_reconciliation" if not reconciliation.get("needs_reconciliation") or reconciliation.get("gold_reconciliation_explanation") else None,
        "pnl_integrity" if _pnl_gate_ok and not _pnl_conflicts else None,
    ]
    failed_gates = [
        "execution_safety" if not exec_safety.get("execution_safe") else None,
        "sentiment_hygiene" if hygiene.get("status") == "FAIL" else None,
        "concentration_threshold" if (conc.get("cluster_max_val", 0) >= 0.65 and conc.get("concentration_status") != "CRITICAL") else None,
        "pnl_integrity" if _pnl_conflicts or _pnl_unflagged else None,
    ]
    return {
        "score":        score,
        "deductions":   deductions,
        "blocking":     blocking,
        "passed_gates": [g for g in passed_gates if g],
        "failed_gates": [g for g in failed_gates if g],
        "pnl_conflict_tickers": _pnl_conflicts,
    }


# ─── blocking / warning checks ───────────────────────────────────────────────

def evaluate_release(exec_safety: Dict, conc: Dict, gtt_status: str,
                     binary_flag: Optional[bool], reconciliation: Dict,
                     dirty_sentiment_in_tape: List[str],
                     cio_plan: Dict, cfg: Dict,
                     hygiene_gate: Optional[Dict] = None) -> Tuple[str, List[str], List[str]]:

    blocks  = []
    warnings = []
    block_cfg = cfg.get("blocking_conditions", {})
    warn_cfg  = cfg.get("warning_conditions", {})

    # Execution safety blocks
    if exec_safety.get("order_routing_enabled"):
        blocks.append("BLOCK: order_routing_enabled=True")
    if exec_safety.get("orders_generated", 0) > 0:
        blocks.append(f"BLOCK: orders_generated={exec_safety.get('orders_generated')}")
    if not exec_safety.get("cio_only_manual_confirmed"):
        blocks.append(f"BLOCK: execution_authority={exec_safety.get('execution_authority')}")

    # Gold reconciliation block
    if reconciliation.get("needs_reconciliation") and not reconciliation.get("gold_reconciliation_explanation"):
        blocks.append("BLOCK: gold thesis CONFIRMING but binary False with no reconciliation explanation")

    # Concentration threshold block — if cluster >= 65% but status not CRITICAL
    cluster_max_val  = conc.get("cluster_max_val", 0.0)
    conc_status      = conc.get("concentration_status", "NORMAL")
    if cluster_max_val >= 0.65 and conc_status != "CRITICAL":
        blocks.append(f"BLOCK: cluster {conc.get('cluster_max_name')} at {cluster_max_val:.0%} but concentration_status={conc_status}")

    # Dirty sentiment block (legacy: portfolio ticker marked DISCARD)
    if dirty_sentiment_in_tape:
        blocks.append(f"BLOCK: dirty sentiment in CIO tape: {dirty_sentiment_in_tape}")

    # Sentiment hygiene gate — new hardening patch
    if hygiene_gate:
        if hygiene_gate.get("status") == "FAIL":
            blocks.append(
                f"BLOCK: sentiment_hygiene_gate=FAIL — "
                f"{hygiene_gate.get('tape_contamination_count',0)} dirty headline(s) in CIO tape. "
                f"Examples: {hygiene_gate.get('examples_failed', [])[:2]}"
            )
        elif hygiene_gate.get("status") == "WARNING":
            warnings.append(
                f"WARN: sentiment_hygiene_gate=WARNING — "
                f"{hygiene_gate.get('dirty_count',0)} dirty headline(s) exist but excluded from tape. "
                f"Blocked examples: {hygiene_gate.get('examples_blocked', [])[:2]}"
            )

    # Warnings
    if warn_cfg.get("blind_spot_failures_exist"):
        pass  # evaluated in caller
    if cio_plan.get("infeasible_count", 0) > 0:
        warnings.append(f"WARN: {cio_plan.get('warning', 'open orders may not execute at current price')}")
    if cluster_max_val >= 0.35 and cluster_max_val < 0.65:
        warnings.append(f"WARN: cluster {conc.get('cluster_max_name')} at elevated {cluster_max_val:.0%}")

    if blocks:
        status = "BLOCKED"
    elif warnings:
        status = "APPROVED_WITH_WARNINGS"
    else:
        status = "APPROVED"

    return status, blocks, warnings


# ─── main gate ────────────────────────────────────────────────────────────────

def run_governance_gate() -> Dict:
    ts = datetime.now(timezone.utc).isoformat(sep="T", timespec="seconds")

    print(f"[{ts}] BlueLotus Governance Gate v{VERSION} starting...")

    # Load inputs
    cfg     = load_json(GOV_CONFIG_PATH)
    dataset = load_json(DATASET_PATH)

    meta    = dataset.get("meta", {})
    regime  = dataset.get("regime", {})
    report_archive = dataset.get("report_archive", {})
    cm      = dataset.get("cross_market_confirmation", {})
    execution = dataset.get("execution", {})
    det_ops   = dataset.get("deterministic_operators", {})

    # 1. Concentration
    print("  [1/7] Computing concentration...")
    conc = compute_concentration(dataset, cfg)

    # 2. Gold thesis
    print("  [2/7] Computing gold thesis tracker...")
    gtt       = compute_gold_thesis(dataset)
    gtt_status = gtt.get("status", "UNKNOWN")
    gtt_score  = gtt.get("score", 0.0)

    # 3. Gold binary flag from cross-market
    binary_flag = cm.get("interpretation_flags", {}).get("gold_thesis_confirmed")

    # 4. Gold reconciliation
    reconciliation = build_gold_reconciliation(gtt_status, binary_flag, cfg)

    # 5. Execution safety
    print("  [3/7] Checking execution safety...")
    exec_safety = check_execution_safety(dataset, cfg)

    # 6. Sentiment relevance
    print("  [4/7] Evaluating sentiment relevance...")
    sentiment_with_relevance = compute_sentiment_relevance(dataset, cfg)

    # Identify dirty sentiment: portfolio tickers whose pre-computed status is DISCARD
    # Trust export_dataset_raw.py computation; only flag if explicitly marked LOW_RELEVANCE / DISCARD
    positions = (dataset.get("portfolio", {}).get("positions") or {})
    portfolio_tickers = set(positions.keys())
    discard_label = cfg["sentiment_relevance_rules"]["discard_label"]
    dirty_in_tape = [
        t for t, s in sentiment_with_relevance.items()
        if t in portfolio_tickers
        and s.get("sentiment_relevance_status") == discard_label
    ]

    # 7. CIO plan vs broker
    print("  [5/7] Checking CIO plan vs broker orders...")
    cio_plan = check_cio_plan_vs_broker(dataset, cfg)

    # 7b. Sentiment hygiene gate
    print("  [5b/7] Running sentiment hygiene gate...")
    hygiene_gate = compute_sentiment_hygiene_gate(sentiment_with_relevance, portfolio_tickers, cfg)

    # 7c. Governance gate score
    # ── Collect P/L arithmetic conflicts from positions ───────────────────────
    _all_positions = dataset.get("portfolio", {}).get("positions") or {}
    _pnl_conflict_tickers  = [t for t, p in _all_positions.items()
                               if isinstance(p, dict) and p.get("pnl_integrity_status") == "BROKER_PNL_SOURCE_CONFLICT"]
    _pnl_unflagged_tickers = [t for t, p in _all_positions.items()
                               if isinstance(p, dict) and p.get("pnl_integrity_status") == "UNKNOWN"]
    gate_score = compute_governance_gate_score(
        exec_safety, hygiene_gate, conc, reconciliation, cfg,
        pnl_conflicts=_pnl_conflict_tickers,
        pnl_unflagged=_pnl_unflagged_tickers,
    )

    # 8. CIO action & confidence from report_archive (canonical source)
    cio_action      = report_archive.get("cio_action", "WAIT / HOLD")
    confidence      = sf(report_archive.get("confidence", 0.52))
    confidence_label = report_archive.get("confidence_label") or (
        "HIGH" if confidence >= 0.75
        else "MEDIUM" if confidence >= 0.60
        else "LOW-MEDIUM" if confidence >= 0.45
        else "LOW"
    )
    causal_status   = report_archive.get("causal_explanation_status",
                       regime.get("causal_status", "UNKNOWN"))
    blind_status    = report_archive.get("blind_spot_status", "UNKNOWN")
    market_session  = meta.get("market_session", "UNKNOWN")

    # 9. Release evaluation
    print("  [6/7] Evaluating release status...")
    release_status, blocks, warnings = evaluate_release(
        exec_safety, conc, gtt_status, binary_flag,
        reconciliation, dirty_in_tape, cio_plan, cfg,
        hygiene_gate=hygiene_gate
    )

    # Add blind spot warning if applicable
    if blind_status not in ("CLEAR", "PASS") and not any("blind" in w.lower() for w in warnings):
        warnings.append(f"WARN: blind_spot_status={blind_status}")

    # ── Build approved_operating_truth ────────────────────────────────────────
    gtt_action = gtt.get("thesis_action") or {}
    portfolio_mandates = {
        str(t).upper(): str((dataset.get("portfolio_mandates") or {}).get(t, {}).get("mandate") or "UNCLASSIFIED").upper()
        for t in positions.keys()
    }
    approved_truth = {
        "_version": VERSION,
        "_generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "_dataset_generated_at": meta.get("generated_at", ""),
        "_gate": "BlueLotus Governance Gate v" + VERSION,
        "_release_status": release_status,

        # ── contract fields ──────────────────────────────
        "market_status":                meta.get("market_session", "UNKNOWN"),
        "regime":                       regime.get("regime") or regime.get("regime_short", "UNKNOWN"),
        "regime_score":                 int(sf(regime.get("score", 0))),
        "regime_action":                regime.get("action", ""),
        "cio_action":                   cio_action,
        "confidence":                   round(confidence, 3),
        "confidence_label":             confidence_label,
        "causal_status":                causal_status,
        "blind_spot_status":            blind_status,
        "concentration_status":         conc["concentration_status"],
        "cluster_status":               conc["cluster_status"],
        "hhi":                          conc["hhi"],
        "top3_weight":                  conc["top3_weight"],
        "largest_position_ticker":      conc["largest_position_ticker"],
        "largest_position_weight":      conc["largest_position_weight"],
        "cluster_max_name":             conc["cluster_max_name"],
        "cluster_max_val":              conc["cluster_max_val"],
        "gold_thesis_tracker_status":   gtt_status,
        "gold_thesis_tracker_score":    round(gtt_score, 2),
        "gold_thesis_add_signal":       gtt_action.get("thesis_add_signal", "UNKNOWN"),
        "gold_execution_permission":    gtt_action.get("execution_permission", "UNKNOWN"),
        "gold_cross_market_binary_flag": binary_flag,
        "gold_reconciliation_explanation": reconciliation["gold_reconciliation_explanation"],
        "gold_reconciliation_type":     reconciliation["reconciliation_type"],
        "execution_authority":          exec_safety["execution_authority"],
        "orders_generated":             exec_safety["orders_generated"],
        "order_routing_enabled":        exec_safety["order_routing_enabled"],
        "cio_plan_vs_broker_status":    cio_plan["feasibility"],
        "manual_cio_action_required":   cio_plan["manual_cio_action_required"],
        "cio_plan_warning":             cio_plan["warning"],

        # ── governance gate score & hygiene ─────────────
        "governance_gate_score":        gate_score["score"],
        "governance_gate_passed_gates": gate_score["passed_gates"],
        "governance_gate_failed_gates": gate_score["failed_gates"],
        "governance_gate_deductions":   gate_score["deductions"],
        "sentiment_hygiene_gate":       hygiene_gate,
        # ── P/L integrity (from export_dataset_raw.py arithmetic check) ──
        "pnl_integrity": {
            "conflict_tickers":   gate_score.get("pnl_conflict_tickers", []),
            "conflict_count":     len(gate_score.get("pnl_conflict_tickers", [])),
            "status":             "CONFLICT_DETECTED" if gate_score.get("pnl_conflict_tickers") else "OK",
        },

        # ── computed sub-objects ─────────────────────────
        "sentiment_relevance":          sentiment_with_relevance,
        "dirty_tickers_in_portfolio":   dirty_in_tape,
        "infeasible_broker_orders":     cio_plan["infeasible_orders"],

        # ── source data (read-only, for renderer reference) ──
        "portfolio_total_assets":       sf(dataset.get("portfolio", {}).get("total_assets")),
        "portfolio_cash":               sf(dataset.get("portfolio", {}).get("cash")),
        "portfolio_market_val":         sf(dataset.get("portfolio", {}).get("market_val")),
        "portfolio_total_pnl":          sf(dataset.get("portfolio", {}).get("total_pnl")),
        "portfolio_total_pnl_pct":      sf(dataset.get("portfolio", {}).get("total_pnl_pct")),
        "portfolio_position_mandates":  portfolio_mandates,
        "open_order_count":             int(sf(dataset.get("orders", {}).get("open_order_count", 0))),
    }

    # ── Build governance_audit ───────────────────────────────────────────────
    audit = {
        "_version": VERSION,
        "_generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "_dataset_generated_at": meta.get("generated_at", ""),
        "release_status": release_status,
        "blocking_issues": blocks,
        "warnings": warnings,
        "checks": {
            "execution_safety": exec_safety,
            "concentration": conc,
            "gold_thesis_tracker": {
                "status": gtt_status,
                "score": round(gtt_score, 2),
                "fallback": gtt.get("fallback", False),
            },
            "gold_binary_flag": binary_flag,
            "gold_reconciliation": reconciliation,
            "sentiment_dirty_tickers_in_portfolio": dirty_in_tape,
            "sentiment_hygiene_gate": hygiene_gate,
            "governance_gate_score": gate_score,
            "cio_plan_vs_broker": cio_plan,
        },
        "config_applied": str(GOV_CONFIG_PATH),
        "dataset_path": str(DATASET_PATH),
    }

    # ── Write outputs ─────────────────────────────────────────────────────────
    print("  [7/7] Writing outputs...")
    write_json(TRUTH_PATH, approved_truth)
    write_json(AUDIT_PATH, audit)
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(
        f"{release_status}\n"
        f"Generated: {datetime.now().isoformat(sep=' ', timespec='seconds')}\n"
        f"Dataset:   {meta.get('generated_at', '')}\n"
        f"Blocks:    {len(blocks)}\n"
        f"Warnings:  {len(warnings)}\n",
        encoding="utf-8",
    )

    print(f"\n{'='*60}")
    print(f"  GOVERNANCE GATE RESULT: {release_status}")
    print(f"{'='*60}")
    if blocks:
        print("  BLOCKING ISSUES:")
        for b in blocks:
            print(f"    • {b}")
    if warnings:
        print("  WARNINGS:")
        for w in warnings:
            print(f"    • {w}")
    print(f"\n  Outputs written:")
    print(f"    {TRUTH_PATH}")
    print(f"    {AUDIT_PATH}")
    print(f"    {STATUS_PATH}")
    print(f"\n  Concentration : {conc['concentration_status']} | HHI {conc['hhi']:.3f} | Largest {conc['largest_position_ticker']} {conc['largest_position_weight']:.0%}")
    if conc["cluster_status"]:
        for c, cs in conc["cluster_status"].items():
            print(f"  Cluster {c:<15}: {cs['severity']} / {cs['weight_pct']}")
    print(f"  Gold Tracker  : {gtt_status} ({gtt_score:.2f}/1.00)")
    print(f"  Binary Flag   : {binary_flag}")
    print(f"  Exec Safety   : {'SAFE' if exec_safety['execution_safe'] else 'VIOLATION'} | authority={exec_safety['execution_authority']} routing={exec_safety['order_routing_enabled']} generated={exec_safety['orders_generated']}")
    if dirty_in_tape:
        print(f"  Dirty Tape    : {dirty_in_tape}")
    print(f"  Hygiene Gate  : {hygiene_gate['status']} | dirty_total={hygiene_gate['dirty_count']} | tape_contaminated={hygiene_gate['tape_contamination_count']}")
    print(f"  Gate Score    : {gate_score['score']}/100 | passed={gate_score['passed_gates']} | failed={gate_score['failed_gates']}")
    print(f"  CIO Plan      : feasibility={cio_plan['feasibility']} manual_required={cio_plan['manual_cio_action_required']}")
    print(f"{'='*60}\n")

    return {
        "release_status": release_status,
        "blocks": blocks,
        "warnings": warnings,
        "approved_truth": approved_truth,
        "audit": audit,
    }


# ─── loader for renderers ─────────────────────────────────────────────────────

def load_approved_truth(truth_path: Optional[Path] = None) -> Optional[Dict]:
    """
    Called by renderers. Returns approved_operating_truth dict or None if unavailable.
    Renderers should fall back gracefully if None is returned.
    """
    path = truth_path or TRUTH_PATH
    try:
        if path.exists():
            return load_json(path)
        return None
    except Exception:
        return None


def get_release_status(truth_path: Optional[Path] = None) -> str:
    """Return release status string, or 'UNKNOWN' if gate has not been run."""
    try:
        sp = STATUS_PATH if truth_path is None else truth_path.parent / "release_status.txt"
        if sp.exists():
            return sp.read_text(encoding="utf-8").split("\n")[0].strip()
        return "UNKNOWN"
    except Exception:
        return "UNKNOWN"


if __name__ == "__main__":
    result = run_governance_gate()
    sys.exit(0 if result["release_status"] != "BLOCKED" else 1)

