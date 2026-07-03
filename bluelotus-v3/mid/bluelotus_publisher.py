#!/usr/bin/env python3
"""
BlueLotus Website Publisher v1.7 — Integrated V2 Publisher
===========================================================
Integrated into C:\\bluelotus2\\mid\\ — 2026-06-08
Called at end of V2 pipeline cycle by run_bluelotus_v2_pipeline_simple_hourly_no_research_agent.bat
Single-shot (no loop). Reads dataset_raw.json, builds HTML, pushes GitHub Pages, sends Telegram.

Changes from v1.6:
  DASHBOARD
  - Command Header bar: Regime · CIO Action · Data freshness · Integrity
  - Pulse Strip: 5 tight KPIs (VIX, F&G, Score, Portfolio, Cash)
  - 3-column Situation Board: Threat Board | Portfolio | Top Movers
  - Threat Board: Geopolitical alert banner + top 3 warnings
  - Portfolio table: Thesis label replaces Governance column
  - Day change shows '--' when absent/zero (stale market close data)
  - Top Movers: market context line (SPY/QQQ if available)
  - Event Correlation: top 4 cards + breadth summary line
  - Catalyst Calendar: only rendered if data present
  - System Health: single footer line (replaces operational signal list)
  - Chief Strategist Report text REMOVED from dashboard

  CHIEF STRATEGIST PAGE
  - SITUATION AT A GLANCE block (5 bullets) at top of page
  - Moomoo Intelligence filtered to portfolio tickers first
  - Structured section headers, not raw text wall
  - Raw report still rendered below for full detail

  TELEGRAM
  - Concise summary (~400 chars) replaces full text dump
  - Regime · Action · Portfolio · Warnings · Positions · Top 5 movers · Link

Production paths
  Dataset : C:\\bluelotus2\\data\\frontend\\dataset_raw.json
  Report  : C:\\bluelotus2\\reports\\chief_strategist_v17.txt

Run
  python portfolio_agent_v17_v2_dataset.py

Loops every 60 minutes by default (RUN_EVERY_MINUTES env var).
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.dashboard_widget_manager import assert_publishable, ensure_nojekyll, render_widget_zone

try:
    from acms_cop.reports.signal_edge_dashboard_renderer import build_shannon_thorp_refinement, render_str_text_section
    from acms_cop.reports.remediation_reconciliation import build_remediation_reconciliation, render_remediation_text_section
except Exception:
    build_shannon_thorp_refinement = None
    render_str_text_section = None
    build_remediation_reconciliation = None
    render_remediation_text_section = None

try:
    from chief_strategist_governance.csg_builder import build_chief_strategist_governance_pack
    from chief_strategist_governance.report_renderers import governance_is_active, render_csg_text_section
except Exception:
    build_chief_strategist_governance_pack = None
    governance_is_active = None
    render_csg_text_section = None

try:
    from cio_context_capsule.master_prompt import build_chief_strategist_master_prompt
    from cio_context_capsule.builder import build_cio_context_capsule
    from cio_context_capsule.renderers import (
        capsule_is_active,
        master_prompt_is_active,
        render_cio_context_text_section,
        render_master_prompt_text_section,
    )
except Exception:
    build_chief_strategist_master_prompt = None
    build_cio_context_capsule = None
    capsule_is_active = None
    master_prompt_is_active = None
    render_cio_context_text_section = None
    render_master_prompt_text_section = None

try:
    from canonical.canonical_data_contract import build_v3_1_to_v3_4_payload
except Exception:
    build_v3_1_to_v3_4_payload = None

try:
    from db_efficiency.public_dataset import build_public_dataset
except Exception:
    build_public_dataset = None

try:
    from mid.nite_pei_report_builder import append_nite_pei_report
except Exception:
    append_nite_pei_report = None

try:
    import requests
except ImportError as exc:
    raise SystemExit("Missing dependency: requests. Install with: pip install requests") from exc

try:
    from dotenv import load_dotenv
    # Load V3 env first (non-override so process env takes precedence)
    _v3_env = Path(r"C:\bluelotus3\.env")
    if _v3_env.exists():
        load_dotenv(dotenv_path=_v3_env, override=False)
    else:
        load_dotenv(override=False)
    # If GITHUB_TOKEN is still blank (V3 .env has empty value), fall back to V2 .env
    # which holds the active token for the shared bluelotus GitHub Pages repo.
    import os as _os
    if not _os.environ.get("GITHUB_TOKEN"):
        _v2_env = Path(r"C:\bluelotus2\.env")
        if _v2_env.exists():
            for _line in _v2_env.read_text(encoding="utf-8").splitlines():
                if _line.startswith("GITHUB_TOKEN="):
                    _tok = _line.split("=", 1)[1].strip()
                    if _tok:
                        _os.environ["GITHUB_TOKEN"] = _tok
                    break
    # Force GITHUB_PAGES_REPO to the public Pages repo (V3 .env wrongly has bluelotus3)
    _os.environ["GITHUB_PAGES_REPO"] = "bluelotus"
except Exception:
    pass

# ── Configuration ──────────────────────────────────────────────────────────────
WINDOWS_DATASET_PATH      = r"C:\bluelotus3\data\frontend\dataset_raw.json"
WINDOWS_PUBLIC_DATASET_PATH = r"C:\bluelotus3\data\frontend\dataset_public.json"
WINDOWS_REPORT_PATH       = r"C:\bluelotus3\reports\chief_strategist_v17.txt"
WINDOWS_INTEL_PATH        = r"C:\bluelotus3\data\manual_intelligence.json"
LOCAL_FALLBACK_DATASET    = "/mnt/data/dataset_raw.json"
NEWS_PROBE_SOURCES_PATH   = Path(r"C:\bluelotus3\mid\news_probe_sources.json")
PORTFOLIO_THESIS_LABELS_PATH = Path(r"C:\bluelotus3\mid\portfolio_thesis_labels.json")

DATASET_RAW_PATH   = os.getenv("DATASET_RAW_PATH",    WINDOWS_DATASET_PATH)
PUBLIC_DATASET_PATH = os.getenv("PUBLIC_DATASET_PATH", WINDOWS_PUBLIC_DATASET_PATH)
REPORT_OUTPUT_PATH = os.getenv("CS_REPORT_OUTPUT_PATH", WINDOWS_REPORT_PATH)
# Publisher is single-shot when called from the V2 pipeline
RUN_EVERY_MINUTES  = int(os.getenv("RUN_EVERY_MINUTES", "60"))
RUN_LOOP           = False  # Integrated mode: pipeline controls the schedule
ACMS_COP_REPORT_PATH = Path(r"C:\bluelotus3\reports\acms_cop_latest.txt")

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "sohweekian")
# Use GITHUB_PAGES_REPO to avoid collision with bluelotus2 code repo
GITHUB_REPO     = os.getenv("GITHUB_PAGES_REPO", "bluelotus")
GITHUB_BRANCH   = os.getenv("GITHUB_BRANCH", "main")
BASE_URL        = f"https://{GITHUB_USERNAME}.github.io/{GITHUB_REPO}"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# Governance labels — display only
EXCLUDED_CRYPTO        = {"COIN"}
OBSERVATION_ONLY_DEFENSE = {"RTX", "NOC", "LMT", "HII", "LDOS", "BA", "AXON"}

# Thesis mapping — used instead of governance label on dashboard
TICKER_THESIS: Dict[str, str] = {
    "AU": "GOLD", "NEM": "GOLD", "GDX": "GOLD", "GDXJ": "GOLD",
    "GLD": "GOLD", "IAU": "GOLD", "SLV": "SILVER",
    "NVDA": "AI", "AMD": "AI", "MSFT": "AI", "GOOGL": "AI",
    "QBTS": "QUANTUM", "QUBT": "QUANTUM", "IONQ": "QUANTUM", "RGTI": "QUANTUM",
    "BAC": "BANKS", "WFC": "BANKS", "JPM": "BANKS", "GS": "BANKS",
    "C": "BANKS", "MS": "BANKS",
}


def load_portfolio_thesis_labels() -> Dict[str, str]:
    try:
        raw = json.loads(PORTFOLIO_THESIS_LABELS_PATH.read_text(encoding="utf-8"))
        labels = raw.get("labels", {}) if isinstance(raw, dict) else {}
        if isinstance(labels, dict):
            return {str(k).upper(): str(v).upper() for k, v in labels.items()}
    except Exception:
        pass
    return {}


TICKER_THESIS.update(load_portfolio_thesis_labels())


# ── Utilities ──────────────────────────────────────────────────────────────────
def now_sgt() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M SGT")


def display_sgt_time(value: Any) -> str:
    """Normalize common BlueLotus timestamp strings for display."""
    text = str(value or "").strip()
    if not text:
        return ""
    if text.endswith("SGT") and "T" not in text:
        return text
    try:
        if text.startswith("v3_cycle_"):
            stamp = text.replace("v3_cycle_", "", 1)
            dt = datetime.strptime(stamp, "%Y%m%d_%H%M%S")
            return dt.strftime("%Y-%m-%d %H:%M SGT")
        iso = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%Y-%m-%d %H:%M SGT")
    except Exception:
        if "T" in text:
            return text.replace("T", " ")[:16] + " SGT"
        return text


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def money(value: Any) -> str:
    return f"${safe_float(value):,.2f}"


def pct(value: Any) -> str:
    return f"{safe_float(value):+.2f}%"


def pct_short(value: Any) -> str:
    """Shorter percent string without leading space."""
    v = safe_float(value)
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.1f}%"


def clean_text(value: Any, limit: Optional[int] = None) -> str:
    text = re.sub(r"<[^>]+>", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        return text[: limit - 1].rstrip() + "…"
    return text


def html_escape(value: Any) -> str:
    s = str(value if value is not None else "")
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
    )


def append_acms_cop_report(report: str) -> str:
    if not ACMS_COP_REPORT_PATH.exists():
        return report
    try:
        acms = ACMS_COP_REPORT_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return report
    if not acms or "ACMS-COP Strategic Thinking" in report:
        return report
    return report.rstrip() + "\n\n" + acms + "\n"


def append_str_report(report: str, ds: Dict[str, Any]) -> str:
    if "STR - SIGNAL, ENTROPY, AND EDGE" in report:
        return report
    str_data = ds.get("shannon_thorp_refinement") if isinstance(ds.get("shannon_thorp_refinement"), dict) else {}
    if not str_data and build_shannon_thorp_refinement:
        try:
            str_data = build_shannon_thorp_refinement(ds)
        except Exception:
            str_data = {}
    if not str_data or not render_str_text_section:
        return report
    return report.rstrip() + "\n\n" + render_str_text_section(str_data).strip() + "\n"


def append_remediation_report(report: str, ds: Dict[str, Any]) -> str:
    rem_data = ds.get("v3_str_bug_clearance_reconciliation") if isinstance(ds.get("v3_str_bug_clearance_reconciliation"), dict) else {}
    str_data = ds.get("shannon_thorp_refinement") if isinstance(ds.get("shannon_thorp_refinement"), dict) else {}
    if not rem_data and build_remediation_reconciliation:
        try:
            rem_data = build_remediation_reconciliation(ds, str_data)
            ds["v3_str_bug_clearance_reconciliation"] = rem_data
        except Exception:
            rem_data = {}
    if not rem_data or not render_remediation_text_section:
        return report
    return report.rstrip() + "\n\n" + render_remediation_text_section(rem_data).strip() + "\n"


def append_csg_report(report: str, ds: Dict[str, Any]) -> str:
    if "CHIEF STRATEGIST GOVERNANCE LAYER" in report:
        return report
    if governance_is_active and render_csg_text_section and governance_is_active(ds):
        return report.rstrip() + "\n\n" + render_csg_text_section(ds).strip() + "\n"
    return report


def append_benchmark_report(report: str, ds: Dict[str, Any]) -> str:
    if "V3.4 BENCHMARK DASHBOARD" in report:
        return report
    benchmark = ds.get("benchmark_dashboard_v3_4") if isinstance(ds.get("benchmark_dashboard_v3_4"), dict) else {}
    replay = ds.get("deterministic_replay_v3_3") if isinstance(ds.get("deterministic_replay_v3_3"), dict) else {}
    canonical = ds.get("canonical") if isinstance(ds.get("canonical"), dict) else {}
    lock = ds.get("v3_4_observation_lock") if isinstance(ds.get("v3_4_observation_lock"), dict) else {}
    if not benchmark and not replay and not canonical:
        return report
    lines = [
        "V3.4 BENCHMARK DASHBOARD",
        "=" * 28,
        f"Canonical: {canonical.get('version', 'UNKNOWN')} validation={((canonical.get('validation') or {}).get('status', 'UNKNOWN'))}",
        f"Replay: strategies={replay.get('strategy_count', 0)} scenarios={replay.get('scenario_count', 0)} point_in_time={replay.get('point_in_time_guard_status', 'UNKNOWN')}",
        f"Benchmark: {benchmark.get('benchmark_id', 'UNKNOWN')} status={benchmark.get('benchmark_dashboard_status', 'UNKNOWN')}",
        f"Observation lock: {lock.get('lock_status', 'UNKNOWN')} upgrade_allowed={lock.get('upgrade_allowed', False)}",
        "Execution safety: CIO_ONLY_MANUAL | order_routing_enabled=False | orders_generated=0",
    ]
    for row in (benchmark.get("benchmark_rankings") or [])[:5]:
        if isinstance(row, dict):
            lines.append(f"- #{row.get('rank')} {row.get('strategy_id')} sharpe={row.get('avg_sharpe_proxy')} drawdown={row.get('avg_drawdown_proxy')}")
    return report.rstrip() + "\n\n" + "\n".join(lines).strip() + "\n"


def append_cio_context_report(report: str, ds: Dict[str, Any]) -> str:
    if "CIO CONTEXT CAPSULE" in report:
        return report
    if capsule_is_active and render_cio_context_text_section and capsule_is_active(ds):
        return render_cio_context_text_section(ds).strip() + "\n\n" + report.lstrip()
    return report


def append_master_prompt_report(report: str, ds: Dict[str, Any]) -> str:
    if "CHIEF STRATEGIST MASTER PROMPT" in report:
        return report
    if master_prompt_is_active and render_master_prompt_text_section and master_prompt_is_active(ds):
        return render_master_prompt_text_section(ds).strip() + "\n\n" + report.lstrip()
    return report


def pct_color(value: Any) -> str:
    return "#4ade80" if safe_float(value) >= 0 else "#ff5566"


def day_change_display(chg_pct: Any) -> str:
    """Show '--' when day change is absent or zero (stale/closed market)."""
    v = safe_float(chg_pct)
    if v == 0.0:
        return "--"
    return pct(v)


def thesis_label(ticker: str) -> str:
    return TICKER_THESIS.get(str(ticker).upper(), "WATCH")


def regime_color(regime_short: str) -> str:
    s = regime_short.upper()
    if "RISK OFF" in s or "OFF" in s:
        return "#ff5566"
    if "RISK ON" in s or "ON" in s:
        return "#4ade80"
    return "#fbbf24"


def regime_emoji(regime_short: str) -> str:
    s = regime_short.upper()
    if "RISK OFF" in s or "OFF" in s:
        return "🔴"
    if "RISK ON" in s or "ON" in s:
        return "🟢"
    return "🟡"


def hex_to_rgb_css(hex_color: str) -> str:
    """Convert '#ff5566' → '255,85,102' for use inside CSS rgba()."""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"


# ── Data helpers ───────────────────────────────────────────────────────────────
def load_dataset(path: str = DATASET_RAW_PATH) -> Dict[str, Any]:
    chosen = Path(path)
    if not chosen.exists() and Path(LOCAL_FALLBACK_DATASET).exists():
        chosen = Path(LOCAL_FALLBACK_DATASET)
    if not chosen.exists():
        raise FileNotFoundError(f"dataset_raw.json not found: {path}")
    with chosen.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("dataset_raw.json must contain a JSON object")
    data["_loaded_from"] = str(chosen)
    return data


def load_manual_intelligence(path: str = WINDOWS_INTEL_PATH) -> List[Dict[str, Any]]:
    """Load CIO manual intelligence notes from the persistent overlay file.
    Returns list of active/monitoring notes, sorted HIGH priority first.
    Silently returns empty list if file is missing (non-blocking)."""
    try:
        p = Path(path)
        if not p.exists():
            return []
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        notes = data.get("intelligence_notes", [])
        if not isinstance(notes, list):
            return []
        # Filter to active/monitoring only, sort HIGH first
        visible = [n for n in notes if isinstance(n, dict)
                   and str(n.get("status", "ACTIVE")).upper() in ("ACTIVE", "MONITORING")]
        # Drop notes older than 48 hours (stale intelligence)
        cutoff = datetime.now().timestamp() - 48 * 3600
        fresh = []
        for n in visible:
            raw_date = n.get("date") or n.get("created_at") or n.get("timestamp") or ""
            try:
                # Accept full datetime strings or date-only strings
                raw_str = str(raw_date).strip()
                if "T" in raw_str or " " in raw_str:
                    note_dt = datetime.fromisoformat(raw_str.replace("Z", ""))
                else:
                    note_dt = datetime.strptime(raw_str, "%Y-%m-%d")
                if note_dt.timestamp() >= cutoff:
                    fresh.append(n)
            except Exception:
                fresh.append(n)  # unparseable date — keep to avoid hiding valid notes
        fresh.sort(key=lambda n: 0 if str(n.get("priority", "")).upper() == "HIGH" else 1)
        return fresh
    except Exception as exc:
        print(f"  [intel] manual_intelligence.json load failed: {exc}")
        return []


def get_prices(ds: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    live = ds.get("live_prices", {})
    if isinstance(live, dict):
        prices = live.get("prices")
        if isinstance(prices, dict):
            return prices
    return {}


def get_top_movers(ds: Dict[str, Any], n: int = 12) -> List[Dict[str, Any]]:
    live = ds.get("live_prices", {})
    if isinstance(live, dict) and isinstance(live.get("top_movers"), list):
        return live.get("top_movers", [])[:n]
    prices = get_prices(ds)
    rows = [
        {"ticker": t, "price": v.get("price", 0), "chg_pct": v.get("chg_pct", 0)}
        for t, v in prices.items()
        if isinstance(v, dict)
    ]
    rows.sort(key=lambda x: abs(safe_float(x.get("chg_pct"))), reverse=True)
    return rows[:n]


def source_health_summary(ds: Dict[str, Any]) -> Tuple[int, int, List[str]]:
    meta = ds.get("meta", {}) if isinstance(ds.get("meta"), dict) else {}
    active   = int(safe_float(meta.get("sources_active") or meta.get("external_sources_active"), 0))
    expected = int(safe_float(meta.get("sources_expected"), 0))
    health   = ds.get("source_health", [])
    bad: List[str] = []
    if isinstance(health, list):
        for item in health:
            if not isinstance(item, dict):
                continue
            status = str(item.get("status") or item.get("grade") or "").upper()
            name   = item.get("source") or item.get("name") or item.get("feed")
            if name and any(x in status for x in ["FAIL", "ERROR", "STALE", "DOWN"]):
                bad.append(str(name))
    return active, expected, bad[:8]


def cio_action_from_regime(regime: Dict[str, Any], portfolio: Dict[str, Any]) -> str:
    short     = str(regime.get("regime_short") or regime.get("regime") or "").upper()
    integrity = bool(portfolio.get("integrity_flag")) or bool(portfolio.get("stale"))
    if integrity:
        return "WAIT"
    if "RISK OFF" in short:
        return "WAIT / HOLD"
    if "RISK ON" in short:
        return "SELECTIVE_BUY_RESEARCH_ONLY"
    return "HOLD / WAIT"


def source_coverage_label(active: Any, expected: Any) -> str:
    return f"Sources active: {int(safe_float(active, 0))} / baseline {int(safe_float(expected, 0))}"


def normalize_cash_fortress_text(text: Any, cash_fortress: bool = False) -> str:
    value = clean_text(text)
    if not cash_fortress:
        return value
    replacements = {
        "High cash concentration": "CASH_FORTRESS_ACTIVE - high cash is intentional defensive posture",
        "high cash concentration": "CASH_FORTRESS_ACTIVE - high cash is intentional defensive posture",
        "high cash is a concentration risk": "CASH_FORTRESS_ACTIVE - high cash is intentional defensive posture",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def filter_moomoo_for_portfolio(
    moomoo: List[Any], positions: Dict[str, Any]
) -> List[Any]:
    """Re-order moomoo intel so portfolio tickers appear first."""
    tickers = {str(t).upper() for t in positions.keys()}
    priority, other = [], []
    for item in moomoo:
        text = ""
        if isinstance(item, dict):
            text = str(item.get("summary") or item.get("raw_text") or item.get("title") or "")
        else:
            text = str(item)
        if any(t in text.upper() for t in tickers):
            priority.append(item)
        else:
            other.append(item)
    return priority + other


def extract_geo_alert(event_corr: List[Dict[str, Any]]) -> str:
    """Return short geopolitical alert text if present, else empty string."""
    for ev in event_corr:
        theme = str(ev.get("theme", "")).upper()
        why   = str(ev.get("why", ""))
        if "GEO" in theme or "DEFENSE" in theme or "IRAN" in why.upper() or "WAR" in theme:
            return clean_text(why, 110)
    return ""


def get_reference_prices(ds: Dict[str, Any]) -> Dict[str, float]:
    """Return SPY/QQQ/IWM prices if available in the dataset."""
    prices = get_prices(ds)
    ref: Dict[str, float] = {}
    for t in ("SPY", "QQQ", "IWM"):
        row = prices.get(t, {})
        if isinstance(row, dict) and row.get("chg_pct") is not None:
            ref[t] = safe_float(row.get("chg_pct"))
    return ref


# ── 8-Lens Chief Strategist Report ────────────────────────────────────────────
def build_chief_strategist_report(ds: Dict[str, Any],
                                   intel_notes: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    8-Lens Chief Strategist Brief v1.7 — deterministic, data-driven.
    Each lens: State · Readings/Flags/Breaches · Implication (3 lines max)
    CIO Intelligence Notes block (manual overlays) between Lens 8 and Strategist Brief.
    Followed by 5-line STRATEGIST BRIEF + CIO ACTION.
    """
    if intel_notes is None:
        intel_notes = []
    meta        = ds.get("meta", {}) if isinstance(ds.get("meta"), dict) else {}
    regime      = ds.get("regime", {}) if isinstance(ds.get("regime"), dict) else {}
    portfolio   = ds.get("portfolio", {}) if isinstance(ds.get("portfolio"), dict) else {}
    fear        = ds.get("fear_greed", {}) if isinstance(ds.get("fear_greed"), dict) else {}
    cm_conf     = ds.get("cross_market_confirmation", {}) if isinstance(ds.get("cross_market_confirmation"), dict) else {}
    risk_model  = ds.get("risk_model", {}) if isinstance(ds.get("risk_model"), dict) else {}
    thesis_lc   = ds.get("thesis_lifecycle", {}) if isinstance(ds.get("thesis_lifecycle"), dict) else {}
    event_corr  = ds.get("event_correlations", []) if isinstance(ds.get("event_correlations"), list) else []
    forecasting = ds.get("research_forecasting", {}) if isinstance(ds.get("research_forecasting"), dict) else {}
    iq          = ds.get("institutional_quant", {}) if isinstance(ds.get("institutional_quant"), dict) else {}
    monitoring  = ds.get("monitoring", {}) if isinstance(ds.get("monitoring"), dict) else {}
    cio_dec     = ds.get("cio_decisions", {}) if isinstance(ds.get("cio_decisions"), dict) else {}
    positions   = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
    active, expected, bad_sources = source_health_summary(ds)

    # ─── LENS 1 — REGIME ─────────────────────────────────────────────────────────
    regime_short = str(regime.get("regime_short") or regime.get("regime") or "UNKNOWN")
    regime_score = regime.get("score", "N/A")
    cio_action   = cio_action_from_regime(regime, portfolio)
    vix          = regime.get("vix_level", "N/A")
    fg_score     = fear.get("score", regime.get("fg_score", "N/A"))
    fg_label     = str(fear.get("label", fear.get("rating", "UNKNOWN"))).upper()
    warnings     = regime.get("warnings", []) if isinstance(regime.get("warnings"), list) else []
    factors      = regime.get("factors", {}) if isinstance(regime.get("factors"), dict) else {}
    factors_str  = "  ".join(
        f"{k}:{int(v):+d}" for k, v in factors.items() if isinstance(v, (int, float))
    ) if factors else "N/A"
    primary_warn = clean_text(warnings[0], 100) if warnings else "No primary warning flagged"
    L1_state = f"{regime_short}  (score {regime_score})  |  CIO: {cio_action}"
    L1_read  = f"VIX {vix}  ·  F&G {fg_score}/100 {fg_label}  ·  Factors [{factors_str}]"
    L1_impl  = primary_warn

    # ─── LENS 2 — CROSS-MARKET CONFIRMATION ──────────────────────────────────────
    cm_filled    = cm_conf.get("filled_count", 0)
    cm_total     = cm_conf.get("total_count", cm_conf.get("universe_count", 57))
    cm_scores    = cm_conf.get("derived_scores", {}) if isinstance(cm_conf.get("derived_scores"), dict) else {}
    cm_flags     = cm_conf.get("interpretation_flags", {}) if isinstance(cm_conf.get("interpretation_flags"), dict) else {}
    active_flags = [k for k, v in cm_flags.items() if v is True]
    total_flags  = len(cm_flags)
    flag_count   = len(active_flags)
    risk_app     = cm_scores.get("risk_appetite", cm_scores.get("risk_appetite_score", "N/A"))
    risk_app_str = f"{risk_app:.2f}" if isinstance(risk_app, float) else str(risk_app)
    flags_str    = ", ".join(active_flags[:6]) + ("…" if flag_count > 6 else "") if active_flags else "None"
    if flag_count >= 10:
        L2_impl = f"Strong cross-market divergence — {flag_count}/{total_flags} flags signal broad stress"
    elif flag_count >= 6:
        L2_impl = f"Moderate stress confirmation — {flag_count}/{total_flags} flags active"
    else:
        L2_impl = f"Low cross-market stress — {flag_count}/{total_flags} flags active"
    L2_state = f"{flag_count}/{total_flags} flags ACTIVE  ·  Risk appetite {risk_app_str}  ·  Coverage {cm_filled}/{cm_total}"
    L2_flags = flags_str

    # ─── LENS 3 — RISK MODEL ──────────────────────────────────────────────────────
    rm_hvar     = risk_model.get("historical_var", {})
    rm_var95    = rm_hvar.get("confidence_95", {}) if isinstance(rm_hvar, dict) else {}
    var_dollars = safe_float(rm_var95.get("daily_dollars") if isinstance(rm_var95, dict) else 0)
    var_pct     = safe_float(rm_var95.get("daily_pct") if isinstance(rm_var95, dict) else 0)
    beta_spy    = safe_float(risk_model.get("beta_to_spy"))
    vol_ann     = safe_float(risk_model.get("volatility_annualized"))
    return_obs  = risk_model.get("return_observations", "N/A")
    breaches    = risk_model.get("constraint_breaches", []) if isinstance(risk_model.get("constraint_breaches"), list) else []
    breach_count = len(breaches)
    breach_descs: List[str] = []
    for br in breaches[:3]:
        if isinstance(br, dict):
            desc = br.get("constraint") or br.get("description") or br.get("type") or br.get("breach") or str(br)
            breach_descs.append(clean_text(desc, 60))
    breach_str  = "  |  ".join(breach_descs) if breach_descs else ("No constraint breaches" if breach_count == 0 else f"{breach_count} breaches")
    var_pct_str = f"{var_pct*100:.2f}%" if var_pct > 0 else "N/A"
    L3_state  = f"VaR95 ${var_dollars:,.0f} ({var_pct_str})  ·  Beta SPY {beta_spy:.2f}  ·  {breach_count} constraint breach{'es' if breach_count != 1 else ''}"
    L3_breach = breach_str
    L3_impl   = f"Portfolio carries {beta_spy:.1f}x SPY sensitivity · annualised vol {vol_ann*100:.1f}% · {return_obs} observations"

    # ─── LENS 4 — PORTFOLIO ───────────────────────────────────────────────────────
    market_val    = safe_float(portfolio.get("market_val") or portfolio.get("total_value"))
    cash          = safe_float(portfolio.get("cash"))
    total_assets  = safe_float(portfolio.get("total_assets"))
    total_pnl     = safe_float(portfolio.get("total_pnl"))
    total_pnl_pct = safe_float(portfolio.get("total_pnl_pct"))
    cash_pct      = (cash / total_assets * 100.0) if total_assets else 0.0
    pos_parts: List[str] = []
    worst_t, worst_p = "", 0.0
    for t, p in positions.items():
        if not isinstance(p, dict):
            continue
        pp = safe_float(p.get("unrealized_p"))
        mv = safe_float(p.get("mkt_val") or p.get("market_value") or p.get("market_val") or 0.0)
        wt = (mv / market_val * 100.0) if market_val else 0.0
        sign = "+" if pp >= 0 else ""
        pos_parts.append(f"{t} {sign}{pp:.1f}% ({wt:.0f}%wt)")
        if pp < worst_p:
            worst_p, worst_t = pp, t
    pos_str  = "  |  ".join(pos_parts) if pos_parts else "No active positions"
    L4_state = f"{money(market_val)} equity  ·  {money(cash)} cash ({cash_pct:.0f}%)  ·  P/L {money(total_pnl)} ({pct_short(total_pnl_pct)})"
    L4_pos   = (pos_str[:200] + "…") if len(pos_str) > 200 else pos_str
    if worst_t:
        th      = TICKER_THESIS.get(worst_t, "WATCH")
        L4_impl = f"{worst_t} leading losses ({pct_short(worst_p)}) — {th} sleeve under pressure"
    else:
        L4_impl = "No dominant loss position — review concentration vs. cash buffer"

    # ─── LENS 5 — THESIS LIFECYCLE ───────────────────────────────────────────────
    theses     = thesis_lc.get("theses", []) if isinstance(thesis_lc.get("theses"), list) else []
    confirmed  = [t for t in theses if str(t.get("status", "")).upper() == "CONFIRMED"]
    active_th  = [t for t in theses if str(t.get("status", "")).upper() == "ACTIVE"]
    thesis_lines: List[str] = []
    for th in theses[:4]:
        status = str(th.get("status", "?")).upper()
        conf   = safe_float(th.get("confidence", th.get("confidence_pct", 0)))
        evid   = th.get("evidence", [])
        et = ""
        if isinstance(evid, list) and evid:
            fe = evid[0]
            et = clean_text(fe.get("evidence", "") if isinstance(fe, dict) else str(fe), 55)
        thesis_lines.append(f"[{status}] {et} ({conf*100:.0f}%)")
    top_th_str = "  |  ".join(thesis_lines) if thesis_lines else "No thesis data"
    if len(confirmed) >= 4:
        L5_impl = f"{len(confirmed)} theses CONFIRMED — structural positions aligned with regime"
    elif len(confirmed) >= 2:
        L5_impl = f"{len(confirmed)} confirmed, {len(active_th)} ACTIVE — partial validation; maintain sizing"
    else:
        L5_impl = "Thesis validation incomplete — high-conviction positions unconfirmed"
    L5_state = f"{len(theses)} theses  ·  {len(confirmed)} CONFIRMED  ·  {len(active_th)} ACTIVE"
    L5_key   = (top_th_str[:200] + "…") if len(top_th_str) > 200 else top_th_str

    # ─── LENS 6 — INTELLIGENCE TAPE ──────────────────────────────────────────────
    geo      = extract_geo_alert(event_corr)
    ro_count = sum(1 for ev in event_corr if "RISK-OFF" in str(ev.get("direction", "")).upper())
    total_ev = len(event_corr)
    top_evs: List[str] = []
    for ev in event_corr[:3]:
        theme = ev.get("theme", "EVENT")
        dirn  = str(ev.get("direction", "WATCH")).upper()
        conf  = safe_float(ev.get("confidence", 0))
        move  = safe_float(ev.get("basket_move", 0))
        top_evs.append(f"{theme}: {dirn} Conf {conf:.0f}% Basket {pct_short(move)}")
    ev_str    = "  |  ".join(top_evs) if top_evs else "No event data"
    geo_pfx   = (clean_text(geo, 80) + "  · ") if geo else ""
    L6_state  = f"{geo_pfx}{ro_count}/{total_ev} baskets RISK-OFF"
    L6_key    = ev_str
    if total_ev > 0 and ro_count >= int(total_ev * 0.6):
        L6_impl = f"Broad risk-off confirmation — {ro_count}/{total_ev} event baskets aligned bearish"
    elif ro_count > 0:
        L6_impl = f"Mixed signals — {ro_count}/{total_ev} baskets risk-off; selective caution warranted"
    else:
        L6_impl = "No event-driven risk-off signal — monitor for regime shift triggers"

    # ─── LENS 7 — SUPERFORECAST / BRIER ──────────────────────────────────────────
    snap_id      = str(forecasting.get("snapshot_id", "N/A"))
    brier_status = str(forecasting.get("brier_status", "N/A")).upper()
    fc_count     = forecasting.get("forecast_count", "N/A")
    fc_tickers   = forecasting.get("ticker_count", "N/A")
    maturity     = str(forecasting.get("first_maturity_date", forecasting.get("maturity_date", "2026-06-09")))
    L7_state = f"{fc_tickers} tickers  ·  {fc_count} forecasts  ·  Status: {brier_status}"
    L7_key   = f"Snapshot {snap_id}  ·  First resolutions: {maturity}  ·  Doctrine: no skill claimed until resolved"
    L7_impl  = f"Accountability layer {brier_status}. Forecast accuracy unscored until resolution window opens."

    # ─── LENS 8 — OPERATIONS ─────────────────────────────────────────────────────
    iq_score    = safe_float(iq.get("readiness_score", iq.get("iq_readiness_score", 0)))
    alert_count = int(safe_float(monitoring.get("alert_count", 0)))
    severity    = monitoring.get("severity_counts", {}) if isinstance(monitoring.get("severity_counts"), dict) else {}
    warn_alerts = int(safe_float(severity.get("WARNING", 0)))
    info_alerts = int(safe_float(severity.get("INFO", 0)))
    pending_rev = int(safe_float(cio_dec.get("pending_review_count", 0)))
    decisions   = cio_dec.get("decisions", []) if isinstance(cio_dec.get("decisions"), list) else []
    hi_priority = [d for d in decisions if str(d.get("priority", "")).upper() in ("HIGH", "CRITICAL", "URGENT")]
    if bad_sources:
        L8_impl = f"Source degradation: {', '.join(bad_sources[:3])} — verify data integrity"
    elif alert_count > 15:
        L8_impl = f"{alert_count} alerts ({warn_alerts} WARNING) — review monitoring queue"
    elif iq_score >= 90:
        L8_impl = f"IQ {iq_score:.1f}/100 — institutional-grade readiness · all systems nominal"
    else:
        L8_impl = f"IQ {iq_score:.1f}/100 — below target threshold · review process gaps"
    L8_state   = f"IQ Score {iq_score:.1f}/100  ·  {source_coverage_label(active, expected)}  ·  Alerts {alert_count} ({warn_alerts}W/{info_alerts}I)"
    L8_pending = f"{pending_rev} CIO reviews pending  ·  Execution: CIO_ONLY_MANUAL  ·  High-priority: {len(hi_priority)}"

    # ─── STRATEGIST BRIEF ────────────────────────────────────────────────────────
    brief_1 = f"Market is in {regime_short} (score {regime_score}) — VIX {vix}, F&G {fg_score}/100 {fg_label}."
    if flag_count >= 8:
        brief_2 = f"Cross-market confirms stress: {flag_count}/{total_flags} flags active, risk appetite {risk_app_str}."
    else:
        brief_2 = f"Cross-market neutral-to-cautious: {flag_count}/{total_flags} flags active, risk appetite {risk_app_str}."
    brief_3 = f"Portfolio {money(market_val)} / {cash_pct:.0f}% cash — VaR95 ${var_dollars:,.0f} at {beta_spy:.1f}x beta."
    if len(confirmed) >= 3:
        brief_4 = f"{len(confirmed)}/{len(theses)} theses CONFIRMED — structural conviction intact, aligned with regime."
    else:
        brief_4 = f"{len(confirmed)}/{len(theses)} theses confirmed — validation ongoing, maintain sizing discipline."
    brief_5 = f"IQ {iq_score:.1f}/100, {alert_count} alerts, {pending_rev} decisions pending — system {'nominal' if not bad_sources else 'degraded'}."

    SEP  = "═" * 62
    SEP2 = "─" * 62
    SEP3 = "·" * 62
    generated = meta.get("cycle_ts", meta.get("generated_at", now_sgt()))

    # ── CIO Intelligence Notes block ──────────────────────────────────────────────
    intel_block = ""
    if intel_notes:
        intel_block = f"\n{SEP3}\n  CIO INTELLIGENCE NOTES  ({len(intel_notes)} active)\n{SEP3}\n"
        for note in intel_notes:
            nid      = note.get("id", "INT-?")
            ndate    = note.get("date", "")
            priority = str(note.get("priority", "")).upper()
            cat      = str(note.get("category", "")).upper()
            title    = note.get("title", "")
            body     = note.get("body", "")
            affects  = ", ".join(note.get("affects", []))
            status   = str(note.get("status", "")).upper()
            intel_block += (
                f"\n[{nid}] {ndate}  [{priority}]  {cat}  [{status}]\n"
                f"  {title}\n"
                f"  {clean_text(body, 300)}\n"
                f"  Affects: {affects}\n"
            )

    return (
        f"{SEP}\n"
        f"  BLUELOTUS CHIEF STRATEGIST BRIEF v1.7\n"
        f"  {now_sgt()}  |  Cycle: {generated}\n"
        f"{SEP}\n"
        f"\n"
        f"LENS 1 — REGIME\n"
        f"  State      : {L1_state}\n"
        f"  Readings   : {L1_read}\n"
        f"  Implication: {L1_impl}\n"
        f"\n"
        f"LENS 2 — CROSS-MARKET CONFIRMATION\n"
        f"  State      : {L2_state}\n"
        f"  Flags      : {L2_flags}\n"
        f"  Implication: {L2_impl}\n"
        f"\n"
        f"LENS 3 — RISK MODEL\n"
        f"  State      : {L3_state}\n"
        f"  Breaches   : {L3_breach}\n"
        f"  Implication: {L3_impl}\n"
        f"\n"
        f"LENS 4 — PORTFOLIO\n"
        f"  State      : {L4_state}\n"
        f"  Positions  : {L4_pos}\n"
        f"  Implication: {L4_impl}\n"
        f"\n"
        f"LENS 5 — THESIS LIFECYCLE\n"
        f"  State      : {L5_state}\n"
        f"  Key        : {L5_key}\n"
        f"  Implication: {L5_impl}\n"
        f"\n"
        f"LENS 6 — INTELLIGENCE TAPE\n"
        f"  State      : {L6_state}\n"
        f"  Key        : {L6_key}\n"
        f"  Implication: {L6_impl}\n"
        f"\n"
        f"LENS 7 — SUPERFORECAST / BRIER\n"
        f"  State      : {L7_state}\n"
        f"  Key        : {L7_key}\n"
        f"  Implication: {L7_impl}\n"
        f"\n"
        f"LENS 8 — OPERATIONS\n"
        f"  State      : {L8_state}\n"
        f"  Pending    : {L8_pending}\n"
        f"  Implication: {L8_impl}\n"
        f"\n"
        f"{intel_block}"
        f"{SEP}\n"
        f"  STRATEGIST BRIEF\n"
        f"{SEP2}\n"
        f"  {brief_1}\n"
        f"  {brief_2}\n"
        f"  {brief_3}\n"
        f"  {brief_4}\n"
        f"  {brief_5}\n"
        f"\n"
        f"  CIO ACTION: {cio_action}\n"
        f"  Preserve cash buffer — no new entries without live price confirmation.\n"
        f"  Review {pending_rev} pending CIO decisions before next cycle.\n"
        f"{SEP}\n"
    )


# ── Telegram concise summary ───────────────────────────────────────────────────
def build_telegram_summary(ds: Dict[str, Any],
                            intel_notes: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Concise situational awareness message for Telegram.
    Target: fits one screen (~400-500 chars). One message, no chunks.
    """
    meta      = ds.get("meta", {}) if isinstance(ds.get("meta"), dict) else {}
    regime    = ds.get("regime", {}) if isinstance(ds.get("regime"), dict) else {}
    portfolio = ds.get("portfolio", {}) if isinstance(ds.get("portfolio"), dict) else {}
    fear      = ds.get("fear_greed", {}) if isinstance(ds.get("fear_greed"), dict) else {}
    positions = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
    event_corr = ds.get("event_correlations", []) if isinstance(ds.get("event_correlations"), list) else []

    cash        = safe_float(portfolio.get("cash"))
    total_assets = safe_float(portfolio.get("total_assets"))
    market_val  = safe_float(portfolio.get("market_val") or portfolio.get("total_value"))
    cash_pct    = (cash / total_assets * 100.0) if total_assets else 0.0
    total_pnl   = safe_float(portfolio.get("total_pnl"))
    total_pnl_pct = safe_float(portfolio.get("total_pnl_pct"))

    regime_short = str(regime.get("regime_short") or regime.get("regime") or "UNKNOWN")
    regime_score = regime.get("score", "N/A")
    vix          = regime.get("vix_level") or "N/A"
    fg_score     = fear.get("score", regime.get("fg_score", "N/A"))
    fg_label     = str(fear.get("label", fear.get("rating", ""))).upper()
    cio_action   = cio_action_from_regime(regime, portfolio)

    r_emoji = regime_emoji(regime_short)

    # Warnings — top 3, very short
    warnings = regime.get("warnings", []) if isinstance(regime.get("warnings"), list) else []
    warn_short = []
    for w in warnings[:3]:
        w_text = clean_text(w, 35)
        warn_short.append(w_text)

    # Geopolitical alert (one line if present)
    geo = extract_geo_alert(event_corr)
    geo_line = f"⚡ {clean_text(geo, 80)}" if geo else ""

    # Positions — compact: TICKER +/-X.X%
    pos_parts = []
    for t, p in positions.items():
        pp = safe_float(p.get("unrealized_p"))
        sign = "+" if pp >= 0 else ""
        pos_parts.append(f"{t} {sign}{pp:.1f}%")

    # Top 5 movers
    movers = get_top_movers(ds, 5)
    mover_parts = []
    for m in movers[:5]:
        chg = safe_float(m.get("chg_pct"))
        sign = "+" if chg >= 0 else ""
        mover_parts.append(f"{m.get('ticker','?')} {sign}{chg:.0f}%")

    # Risk-off basket count
    ro_count = sum(1 for ev in event_corr if "RISK-OFF" in str(ev.get("direction","")).upper())
    basket_line = f"Baskets: {ro_count}/{len(event_corr)} RISK-OFF" if event_corr else ""

    lines = [
        f"🪷 BLUELOTUS  {r_emoji} {regime_short} ({regime_score})  {now_sgt()}",
        f"CIO: {cio_action}",
        "",
        f"💼 {money(market_val)}  P/L {money(total_pnl)} ({pct_short(total_pnl_pct)})  Cash {cash_pct:.0f}%",
        f"📊 VIX {vix}  ·  F&G {fg_score}/100 {fg_label}",
    ]

    if warn_short:
        lines.append("⚠️  " + "  |  ".join(warn_short))
    if geo_line:
        lines.append(geo_line)
    if basket_line:
        lines.append(basket_line)

    if pos_parts:
        lines.append("")
        lines.append("POSITIONS  " + "  |  ".join(pos_parts))

    if mover_parts:
        lines.append("MOVERS  " + "  ·  ".join(mover_parts))

    # ── CIO Intelligence Brief ────────────────────────────────────────────────
    if intel_notes:
        high_notes = [n for n in intel_notes
                      if str(n.get("priority", "")).upper() == "HIGH"
                      and str(n.get("status", "")).upper() in ("ACTIVE", "MONITORING")]
        if high_notes:
            lines.append("")
            lines.append("📡 INTELLIGENCE BRIEF")
            for n in high_notes[:4]:          # cap at 4 to keep message compact
                nid    = n.get("id", "")
                title  = clean_text(str(n.get("title", "")), 60)
                status = str(n.get("status", "ACTIVE")).upper()
                status_tag = "●" if status == "ACTIVE" else "○"
                lines.append(f"  {status_tag} [{nid}] {title}")
        med_notes = [n for n in intel_notes
                     if str(n.get("priority", "")).upper() == "MEDIUM"
                     and str(n.get("status", "")).upper() in ("ACTIVE", "MONITORING")]
        if med_notes:
            for n in med_notes[:2]:           # up to 2 MEDIUM notes
                nid    = n.get("id", "")
                title  = clean_text(str(n.get("title", "")), 55)
                lines.append(f"  ○ [{nid}] {title}")

    lines.append("")
    lines.append(f"🔗 {BASE_URL}/")
    lines.append("")
    lines.append("— Dr. Codex & Dr. Claude Windows Platform Team")

    return "\n".join(lines)


# ── Telegram sender ────────────────────────────────────────────────────────────
def split_telegram_message(message: str, limit: int = 3900) -> List[str]:
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0
    for line in message.splitlines():
        add_len = len(line) + 1
        if current and current_len + add_len > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = add_len
        else:
            current.append(line)
            current_len += add_len
    if current:
        chunks.append("\n".join(current))
    return chunks or [message[:limit]]


def send_telegram(message: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  Telegram: skipped — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    ok = True
    for idx, chunk in enumerate(split_telegram_message(message), start=1):
        try:
            r = requests.post(
                url,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": chunk, "disable_web_page_preview": True},
                timeout=20,
            )
            if r.status_code != 200:
                ok = False
                print(f"  Telegram error chunk {idx}: HTTP {r.status_code} — {r.text[:300]}")
            time.sleep(0.4)
        except Exception as exc:
            ok = False
            print(f"  Telegram exception chunk {idx}: {exc}")
    print(f"  Telegram: {'PASS' if ok else 'FAIL'}")
    return ok


# ── GitHub publisher ───────────────────────────────────────────────────────────
def github_headers() -> Dict[str, str]:
    return {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}


def github_push(filepath: str, content: str, msg: str) -> bool:
    if not GITHUB_TOKEN:
        print(f"  GitHub {filepath}: skipped — GITHUB_TOKEN missing")
        return False
    url = f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}/contents/{filepath}"
    sha = None
    try:
        r = requests.get(url, headers=github_headers(), timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass
    payload: Dict[str, Any] = {
        "message": msg,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(url, headers=github_headers(), json=payload, timeout=30)
        ok = r.status_code in {200, 201}
        print(f"  GitHub {filepath}: {'PASS' if ok else 'FAIL'} ({r.status_code})")
        if not ok:
            print(f"    {r.text[:300]}")
        return ok
    except Exception as exc:
        print(f"  GitHub {filepath}: FAIL — {exc}")
        return False


# ── Navigation (unchanged from v1.6) ─────────────────────────────────────────
NAV_CSS = """<style id="bl-nav-css">
.bl-nav{position:fixed;top:0;left:0;right:0;z-index:9999;background:rgba(8,8,14,0.97);border-bottom:1px solid rgba(192,132,252,0.18);backdrop-filter:blur(16px);font-family:'JetBrains Mono','Courier New',monospace;}
.bl-nav-inner{max-width:1500px;margin:0 auto;padding:0 28px;display:flex;align-items:center;justify-content:space-between;height:52px;}
.bl-nav-logo{display:flex;align-items:center;gap:10px;text-decoration:none;}
.bl-nav-petal{width:18px;height:18px;background:linear-gradient(135deg,#c084fc,#a855f7);border-radius:50% 50% 50% 0;transform:rotate(-45deg);flex-shrink:0;}
.bl-nav-brand{font-size:10px;font-weight:500;letter-spacing:0.22em;color:#c084fc;text-transform:uppercase;}
.bl-nav-links{display:flex;align-items:center;gap:0;list-style:none;margin:0;padding:0;}
.bl-nav-links > li{position:relative;}
.bl-nav-links > li > a{display:block;font-size:9px;letter-spacing:0.13em;color:rgba(221,216,240,0.4);text-decoration:none;text-transform:uppercase;padding:6px 11px;border-radius:3px;transition:color 0.18s,background 0.18s;white-space:nowrap;}
.bl-nav-links > li > a:hover,.bl-nav-links > li > a.active{color:#c084fc;background:rgba(192,132,252,0.07);}
.bl-nav-links .sep{width:1px;height:14px;background:rgba(255,255,255,0.07);margin:0 1px;flex-shrink:0;}
.bl-dropdown{position:relative;}
.bl-dropdown-btn{display:flex;align-items:center;gap:4px;font-size:9px;letter-spacing:0.13em;color:rgba(221,216,240,0.4);text-decoration:none;text-transform:uppercase;padding:6px 11px;border-radius:3px;cursor:pointer;transition:color 0.18s,background 0.18s;white-space:nowrap;background:none;border:none;font-family:inherit;}
.bl-dropdown-btn:hover,.bl-dropdown:hover .bl-dropdown-btn{color:#c084fc;background:rgba(192,132,252,0.07);}
.bl-dropdown-arrow{font-size:7px;opacity:0.5;transition:transform 0.2s;}
.bl-dropdown:hover .bl-dropdown-arrow,.bl-dropdown.open .bl-dropdown-arrow{transform:rotate(180deg);}
.bl-dropdown-menu{display:none;position:absolute;top:calc(100% + 8px);left:50%;transform:translateX(-50%);background:rgba(10,10,20,0.98);border:1px solid rgba(192,132,252,0.2);border-radius:6px;padding:6px;min-width:190px;backdrop-filter:blur(20px);box-shadow:0 16px 40px rgba(0,0,0,0.6);}
.bl-dropdown:hover .bl-dropdown-menu,.bl-dropdown.open .bl-dropdown-menu{display:block;}
.bl-dropdown-menu a{display:flex;align-items:center;gap:10px;padding:8px 12px;font-size:9px;letter-spacing:0.12em;color:rgba(221,216,240,0.5);text-decoration:none;text-transform:uppercase;border-radius:4px;transition:all 0.15s;white-space:nowrap;}
.bl-dropdown-menu a:hover{color:#c084fc;background:rgba(192,132,252,0.08);}
.bl-dropdown-menu .tribute-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
.bl-dropdown-divider{height:1px;background:rgba(255,255,255,0.06);margin:4px 0;}
.bl-nav-right{display:flex;align-items:center;gap:10px;}
.bl-nav-live{font-size:9px;letter-spacing:0.12em;color:#4ade80;text-transform:uppercase;display:flex;align-items:center;gap:5px;}
.bl-nav-dot{width:5px;height:5px;background:#4ade80;border-radius:50%;animation:blPulse 1.8s ease infinite;}
@keyframes blPulse{0%,100%{opacity:1;}50%{opacity:0.3;}}
.bl-dropdown-menu.wide{min-width:250px;text-align:left;}
.bl-dropdown-menu .subline{display:block;font-size:7px;letter-spacing:.06em;color:rgba(221,216,240,.28);text-transform:none;margin-top:2px;line-height:1.25;}
.bl-nav-action{border:1px solid rgba(192,132,252,.22)!important;background:rgba(192,132,252,.06)!important;color:rgba(232,222,255,.72)!important;}
.bl-nav-action:hover{background:rgba(192,132,252,.12)!important;color:#fff!important;}
body{padding-top:52px !important;}
@media(max-width:1100px){.bl-nav-links > li > a,.bl-dropdown-btn{font-size:8px;padding:5px 8px;}.bl-nav-brand{display:none;}}
@media(max-width:720px){.bl-nav-links .sep{display:none;}.bl-nav-links > li > a,.bl-dropdown-btn{padding:5px 6px;letter-spacing:0.07em;}}
</style>"""

NAV_JS = """<script id="bl-nav-js">
(function(){
  document.querySelectorAll('.bl-dropdown-btn').forEach(function(btn){
    btn.addEventListener('click', function(e){
      e.preventDefault();
      var parent = btn.closest('.bl-dropdown');
      document.querySelectorAll('.bl-dropdown.open').forEach(function(el){ if(el!==parent) el.classList.remove('open'); });
      if(parent) parent.classList.toggle('open');
    });
  });
  document.addEventListener('click', function(e){
    if(!e.target.closest('.bl-dropdown')){
      document.querySelectorAll('.bl-dropdown.open').forEach(function(el){ el.classList.remove('open'); });
    }
  });
})();
</script>"""


def build_nav(active_page: str = "") -> str:
    b = BASE_URL
    def a(key: str, href: str, label: str) -> str:
        cls = ' class="active"' if active_page == key else ""
        return f'<li><a href="{href}"{cls}>{label}</a></li>'
    return f"""{NAV_CSS}
<nav class="bl-nav" role="navigation" aria-label="BlueLotus Navigation">
  <div class="bl-nav-inner">
    <a class="bl-nav-logo" href="{b}/">
      <div class="bl-nav-petal"></div>
      <span class="bl-nav-brand">BlueLotus&nbsp;Fund</span>
    </a>
    <ul class="bl-nav-links">
      {a('dashboard',  f'{b}/',                                'Dashboard')}
      <li class="sep"></li>
      {a('watchlist',  f'{b}/bluelotus-watchlist.html',        'Portfolio')}
      <li class="sep"></li>
      <li class="bl-dropdown">
        <button class="bl-dropdown-btn bl-nav-action">Forecast <span class="bl-dropdown-arrow">&#9660;</span></button>
        <div class="bl-dropdown-menu wide">
          <a href="{b}/bluelotus-watchlist-superforecast.html"><span class="tribute-dot" style="background:#4ade80;"></span><span>Superforecast Report<span class="subline">78-ticker valuation + Brier tracker</span></span></a>
          <div class="bl-dropdown-divider"></div>
          <a href="{b}/superforecasting-thesis.html"><span class="tribute-dot" style="background:#fbbf24;"></span><span>Research Thesis I<span class="subline">May 2026 — protocol, calibration, Kelly</span></span></a>
          <a href="{b}/superforecasting-eipe-thesis-v3.html"><span class="tribute-dot" style="background:#a78bfa;"></span><span>Research Thesis II<span class="subline">Jun 2026 — Brier ledger, EIPE, CIO learning</span></span></a>
          <a href="{b}/slicdo-probabilistic-intelligence-thesis-v3.html"><span class="tribute-dot" style="background:#2dd4bf;"></span><span>Research Thesis III<span class="subline">Jun 2026 — PEI, ACMS–COP, dual Brier</span></span></a>
          <a href="{b}/bgtm-thesis.html"><span class="tribute-dot" style="background:#38bdf8;"></span><span>BGTM-V1<span class="subline">Jun 2026 — Nash equilibrium, game theory</span></span></a>
          <a href="{b}/agentic-turn-thesis.html"><span class="tribute-dot" style="background:#c084fc;"></span><span>The Agentic Turn<span class="subline">Jun 2026 — Claude Code &amp; SE labour</span></span></a>
        </div>
      </li>
      <li class="sep"></li>
      {a('framework',  f'{b}/bluelotus-framework.html',        'Framework')}
      <li class="sep"></li>
      {a('aladdin',    f'{b}/aladdin-story.html',              'Aladdin')}
      <li class="sep"></li>
      {a('cs-report',  f'{b}/chief-strategist.html',           'Strategist')}
      <li class="sep"></li>
      {a('cio-letter', f'{b}/cio-letter.html',                 'CIO Letter')}
      <li class="sep"></li>
      <li class="bl-dropdown">
        <button class="bl-dropdown-btn">Tributes <span class="bl-dropdown-arrow">&#9660;</span></button>
        <div class="bl-dropdown-menu">
          <a href="{b}/einstein-tribute.html"><span class="tribute-dot" style="background:#ff5566;"></span>Einstein &mdash; Prime Mover</a>
          <a href="{b}/shannon-tribute.html"><span class="tribute-dot" style="background:#4a9eff;"></span>Shannon &mdash; Information</a>
          <a href="{b}/turing-tribute.html"><span class="tribute-dot" style="background:#00e5a0;"></span>Turing &mdash; Machine Mind</a>
          <a href="{b}/thorp-tribute.html"><span class="tribute-dot" style="background:#c9a84c;"></span>Thorp &mdash; The Edge</a>
          <div class="bl-dropdown-divider"></div>
          <a href="{b}/gametheory-tribute.html"><span class="tribute-dot" style="background:#9b7fff;"></span>Von Neumann &amp; Nash</a>
        </div>
      </li>
    </ul>
    <div class="bl-nav-right">
      <div class="bl-nav-live"><div class="bl-nav-dot"></div>Live&nbsp;v1.7</div>
    </div>
  </div>
</nav>
{NAV_JS}
"""


def _hex_to_rgb(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"{r},{g},{b}"
    except Exception:
        return "192,132,252"


def build_events_from_dataset(ds: Dict[str, Any]) -> str:
    CATEGORY_COLORS = {
        "fed": "#c084fc", "fomc": "#c084fc", "macro": "#fbbf24",
        "earnings": "#4ade80", "high_impact": "#ff5566", "risk": "#ff5566",
        "info": "#4a9eff", "default": "#8b93a7",
    }
    raw_events: List[Dict[str, Any]] = []
    for key in ("upcoming_events", "economic_calendar", "catalyst_calendar"):
        candidate = ds.get(key)
        if isinstance(candidate, list) and candidate:
            raw_events = candidate
            break
        if isinstance(candidate, dict):
            inner = candidate.get("events") or candidate.get("items") or []
            if isinstance(inner, list) and inner:
                raw_events = inner
                break

    if not raw_events:
        return ""   # v1.7: return empty string — dashboard omits empty calendar

    from datetime import datetime as _dt
    today = _dt.now().date()
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for ev in raw_events:
        raw_date = str(ev.get("date") or ev.get("event_date") or "")
        try:
            if "/" in raw_date:
                d = _dt.strptime(raw_date, "%m/%d/%Y").date()
            else:
                d = _dt.strptime(raw_date[:10], "%Y-%m-%d").date()
        except Exception:
            continue
        grouped.setdefault(d.strftime("%Y-%m-%d"), []).append({**ev, "_date_obj": d})

    if not grouped:
        return ""

    cols = ""
    for iso in sorted(grouped.keys())[:7]:
        evs   = grouped[iso]
        d_obj = evs[0]["_date_obj"]
        day_str  = d_obj.strftime("%a").upper()
        date_str = d_obj.strftime("%b %d")
        is_today = (d_obj == today)
        tborder  = "border-top:2px solid #c084fc;" if is_today else ""
        ttag     = (' <span style="color:#c084fc;font-size:9px;font-family:monospace">TODAY</span>' if is_today else "")
        items = ""
        for ev in evs:
            cat   = str(ev.get("category") or ev.get("type") or "default").lower()
            color = ev.get("color") or CATEGORY_COLORS.get(cat, CATEGORY_COLORS["default"])
            rgb   = _hex_to_rgb(color)
            label = ev.get("label") or ev.get("title") or ev.get("name") or ev.get("event") or "Event"
            if cat in ("earnings",):
                ticker = ev.get("ticker", "")
                note   = ev.get("note") or ev.get("time") or ""
                label  = f"💰 {ticker+' ' if ticker else ''}{label}" + (f" — {note}" if note else "")
            elif cat in ("fed", "fomc"):
                label = f"🏦 {label}"
            items += (
                f'<div style="background:rgba({rgb},0.08);border-left:2px solid {color};'
                f'padding:4px 7px;border-radius:3px;margin-bottom:4px;'
                f'font-size:11px;color:{color};line-height:1.5">{html_escape(label)}</div>'
            )
        cols += (
            f'<div style="flex:1;min-width:140px;background:#111;border:1px solid #222;'
            f'border-radius:6px;padding:12px;{tborder}">'
            f'<div style="font-family:monospace;font-size:10px;color:#888;letter-spacing:1px;margin-bottom:2px">{day_str}</div>'
            f'<div style="font-size:13px;font-weight:600;color:#e6edf3;margin-bottom:10px">{date_str}{ttag}</div>'
            f'{items}</div>'
        )

    legend = (
        '<div style="margin-top:10px;font-size:10px;color:#666;display:flex;gap:16px;flex-wrap:wrap">'
        '<span style="color:#c084fc">&#9632; Fed / FOMC</span>'
        '<span style="color:#fbbf24">&#9632; Macro</span>'
        '<span style="color:#4ade80">&#9632; Earnings</span>'
        '<span style="color:#ff5566">&#9632; High Impact</span>'
        '<span style="color:#4a9eff">&#9632; Info</span>'
        '</div>'
    )
    sorted_dates = sorted(grouped.keys())
    try:
        from datetime import datetime as _dt2
        first = _dt2.strptime(sorted_dates[0], "%Y-%m-%d")
        last  = _dt2.strptime(sorted_dates[-1], "%Y-%m-%d")
        week_label = first.strftime("%b %d") + " — " + last.strftime("%b %d, %Y")
    except Exception:
        week_label = "Upcoming Events"

    return (
        f'<div class="cal-block">'
        f'<div class="ct" style="color:#c084fc;letter-spacing:2px;margin-bottom:10px;font-size:10px">'
        f'&#128197; WEEKLY CATALYST CALENDAR &#8212; {week_label}</div>'
        f'<div style="display:flex;gap:8px;flex-wrap:wrap">{cols}</div>'
        f'{legend}</div>'
    )


def build_thesis_evidence_html(ds: Dict[str, Any]) -> str:
    """Build S3 · Thesis Evidence table from event_correlations_all dataset key."""
    rows = ds.get("event_correlations_all") or []
    if not rows:
        return ""

    DIR_COLOR = {
        "RISK ON":  "#4ade80",
        "RISK OFF": "#ff5566",
        "WATCH":    "#fbbf24",
        "NEUTRAL":  "#94a3b8",
    }

    header = (
        '<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);'
        'border-radius:12px;padding:18px 22px;margin-bottom:16px">'
        '<div style="font-family:JetBrains Mono,monospace;font-size:11px;letter-spacing:.18em;'
        'text-transform:uppercase;color:#c084fc;margin-bottom:12px;display:flex;'
        'align-items:center;gap:10px">S3 · THESIS EVIDENCE'
        '<span style="height:1px;background:rgba(192,132,252,.18);flex:1;display:block"></span>'
        '</div>'
        '<table style="width:100%;border-collapse:collapse;font-size:12px">'
        '<thead><tr style="color:#94a3b8;border-bottom:1px solid rgba(255,255,255,.08)">'
        '<th style="text-align:left;padding:4px 8px;font-weight:500">THEME</th>'
        '<th style="text-align:center;padding:4px 8px;font-weight:500">DIRECTION</th>'
        '<th style="text-align:center;padding:4px 8px;font-weight:500">BASKET MOVE</th>'
        '<th style="text-align:left;padding:4px 8px;font-weight:500">EVIDENCE</th>'
        '<th style="text-align:center;padding:4px 8px;font-weight:500">CONFIDENCE</th>'
        '</tr></thead><tbody>'
    )

    body_rows = []
    for r in rows[:12]:
        theme       = html_escape(str(r.get("theme", "")))
        direction   = str(r.get("direction", "WATCH")).upper()
        basket_move = html_escape(str(r.get("basket_move", "")))
        why         = html_escape(str(r.get("why", r.get("evidence", "")))[:80])
        confidence  = html_escape(str(r.get("confidence", r.get("evidence_tier_label", ""))))
        dir_color   = DIR_COLOR.get(direction, "#94a3b8")
        body_rows.append(
            f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);color:#e2e8f0">'
            f'<td style="padding:5px 8px">{theme}</td>'
            f'<td style="padding:5px 8px;text-align:center">'
            f'<span style="background:{dir_color}22;color:{dir_color};border-radius:4px;'
            f'padding:2px 7px;font-size:11px;font-weight:600">{direction}</span></td>'
            f'<td style="padding:5px 8px;text-align:center;color:#cbd5e1">{basket_move}</td>'
            f'<td style="padding:5px 8px;color:#94a3b8;font-size:11px">{why}</td>'
            f'<td style="padding:5px 8px;text-align:center;color:#cbd5e1;font-size:11px">{confidence}</td>'
            f'</tr>'
        )

    footer = '</tbody></table></div>'
    return header + "".join(body_rows) + footer


def _load_news_probe_sources() -> dict:
    """Load news_probe_sources.json — single source of truth for source config."""
    try:
        return json.loads(NEWS_PROBE_SOURCES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def build_logo_html(logo: dict) -> str:
    """
    Render an HTML badge string from a logo config dict (from news_probe_sources.json).
    Supports types: badge, circle, split, badge_sub.
    All style values come from config — zero hardcoding.
    """
    ltype = logo.get("type", "badge")
    base_flex = "display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;"

    if ltype == "badge":
        style = (
            f"{base_flex}"
            f"background:{logo.get('bg','#444')};"
            f"color:{logo.get('color','#fff')};"
            f"font-family:{logo.get('font','Arial,sans-serif')};"
            f"font-size:{logo.get('font_size','11px')};"
            f"font-weight:{logo.get('font_weight','700')};"
            + (f"letter-spacing:{logo['letter_spacing']};" if logo.get('letter_spacing') else "")
            + (f"width:{logo['width']};" if logo.get('width') else "")
            + (f"height:{logo.get('height','22px')};")
            + (f"padding:{logo['padding']};" if logo.get('padding') else "")
            + f"border-radius:{logo.get('border_radius','3px')};"
        )
        return f'<span style="{style}">{logo.get("text","")}</span>'

    elif ltype == "circle":
        sz = logo.get("size", "22px")
        style = (
            f"{base_flex}"
            f"background:{logo.get('bg','#444')};"
            f"color:{logo.get('color','#fff')};"
            f"font-family:{logo.get('font','Arial,sans-serif')};"
            f"font-size:{logo.get('font_size','14px')};"
            f"font-weight:{logo.get('font_weight','700')};"
            f"width:{sz};height:{sz};border-radius:50%;"
        )
        return f'<span style="{style}">{logo.get("text","")}</span>'

    elif ltype == "badge_sub":
        outer_style = (
            f"{base_flex}"
            f"background:{logo.get('bg','#444')};"
            f"height:{logo.get('height','22px')};"
            f"border-radius:{logo.get('border_radius','3px')};"
            + (f"padding:{logo['padding']};" if logo.get('padding') else "")
            + "gap:4px;"
        )
        main_style = (
            f"font-family:{logo.get('font','Arial,sans-serif')};"
            f"font-weight:{logo.get('font_weight','700')};"
            f"color:{logo.get('color','#fff')};"
            f"font-size:{logo.get('font_size','9px')};"
            + (f"letter-spacing:{logo['letter_spacing']};" if logo.get('letter_spacing') else "")
        )
        sub_style = (
            f"font-family:{logo.get('font','Arial,sans-serif')};"
            f"font-weight:{logo.get('sub_font_weight','400')};"
            f"color:{logo.get('sub_color','#fff')};"
            f"font-size:{logo.get('font_size','9px')};"
        )
        return (
            f'<span style="{outer_style}">'
            f'<span style="{main_style}">{logo.get("text","")}</span>'
            f'<span style="{sub_style}">{logo.get("sub_text","")}</span>'
            f'</span>'
        )

    elif ltype == "split":
        sz = logo.get("size", "22px")
        br = logo.get("border_radius", "2px")
        font = logo.get("font", "Arial,sans-serif")
        fsz = logo.get("font_size", "9px")
        fw = logo.get("font_weight", "700")
        left = logo.get("left", {})
        right = logo.get("right", {})
        left_style = (
            f"display:inline-flex;align-items:center;justify-content:center;"
            f"background:{left.get('bg','#888')};color:{left.get('color','#fff')};"
            f"width:{sz};height:{sz};"
            f"border-radius:{br} 0 0 {br};"
            f"font-family:{font};font-weight:{fw};font-size:{fsz};flex-shrink:0;"
        )
        right_style = (
            f"display:inline-flex;align-items:center;justify-content:center;"
            f"background:{right.get('bg','#444')};color:{right.get('color','#fff')};"
            f"width:{sz};height:{sz};"
            f"border-radius:0 {br} {br} 0;"
            f"font-family:{font};font-weight:{fw};font-size:{fsz};flex-shrink:0;"
        )
        return (
            f'<span style="display:inline-flex;align-items:center;gap:1px;flex-shrink:0;">'
            f'<span style="{left_style}">{left.get("text","")}</span>'
            f'<span style="{right_style}">{right.get("text","")}</span>'
            f'</span>'
        )

    # Unknown type — empty
    return ""


def build_logos_js(sources_cfg: dict) -> str:
    """
    Build a JS-safe `var LOGOS = {...};` string from news_probe_sources.json config.
    All brand data comes from config — no hardcoding in Python.
    Returns a string suitable for direct injection into a <script> block.
    """
    sources = sources_cfg.get("sources", {})
    pairs = []
    for src_id, src_cfg in sources.items():
        logo_cfg = src_cfg.get("logo")
        if not logo_cfg:
            continue
        html = build_logo_html(logo_cfg)
        # Escape for JS string: backslash, then single quote
        html_escaped = html.replace("\\", "\\\\").replace("'", "\\'")
        pairs.append(f"  '{src_id}': '{html_escaped}'")
    inner = ",\n".join(pairs)
    return f"var LOGOS={{\n{inner}\n}};"


def build_dashboard_html(ds: Dict[str, Any]) -> str:
    # ── Load news source config (logo badges, labels) from JSON — never hardcoded ──
    _news_sources_cfg = _load_news_probe_sources()
    _logos_js_var = build_logos_js(_news_sources_cfg)

    meta       = ds.get("meta", {}) if isinstance(ds.get("meta"), dict) else {}
    regime     = ds.get("regime", {}) if isinstance(ds.get("regime"), dict) else {}
    portfolio  = ds.get("portfolio", {}) if isinstance(ds.get("portfolio"), dict) else {}
    fear       = ds.get("fear_greed", {}) if isinstance(ds.get("fear_greed"), dict) else {}
    event_corr = ds.get("event_correlations", []) if isinstance(ds.get("event_correlations"), list) else []
    positions  = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
    movers     = get_top_movers(ds, 10)

    cash        = safe_float(portfolio.get("cash"))
    total_assets = safe_float(portfolio.get("total_assets"))
    market_val  = safe_float(portfolio.get("market_val") or portfolio.get("total_value"))
    cash_pct    = (cash / total_assets * 100.0) if total_assets else 0.0
    total_pnl   = safe_float(portfolio.get("total_pnl"))
    total_pnl_pct = safe_float(portfolio.get("total_pnl_pct"))
    cio_action  = cio_action_from_regime(regime, portfolio)

    regime_short = str(regime.get("regime_short") or regime.get("regime") or "UNKNOWN")
    rc           = regime_color(regime_short)
    r_emoji_str  = regime_emoji(regime_short)
    fg_score     = fear.get("score", regime.get("fg_score", "N/A"))
    fg_label     = str(fear.get("label", fear.get("rating", "UNKNOWN"))).upper()
    vix          = html_escape(str(regime.get("vix_level", ds.get("live_prices", {}).get("vix", {}).get("price", "N/A"))))
    score        = html_escape(str(regime.get("score", "N/A")))

    generated    = html_escape(meta.get("generated_at") or now_sgt())
    integrity_ok = not (portfolio.get("integrity_flag") or portfolio.get("stale"))
    integrity_str = "PASS" if integrity_ok else "⚠ DATA WARNING"
    integrity_col = "#4ade80" if integrity_ok else "#ff5566"

    active, expected, bad_sources = source_health_summary(ds)

    # ── Fund Status — live JS fetch from portfolio_live.json ──────────────────
    # cmd_bar + pulse_strip are now fully JS-driven so they update every pipeline
    # cycle without requiring a new index.html push.  The static Python values
    # (rc, generated, etc.) are still computed above for use elsewhere (sit_board,
    # sys_health) but are NOT baked into the dashboard HTML here.
    fund_live_js = f"""<div id="fund-live" style="margin-bottom:4px">
  <div style="background:rgba(13,16,32,.60);border-left:4px solid #444;border-radius:10px;
    padding:14px 20px;margin-bottom:14px;font-family:JetBrains Mono,monospace;
    color:#444;font-size:11px">Loading Fund Status…</div>
  <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px;opacity:.3">
    {''.join(['<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.10);border-radius:14px;padding:14px 16px;height:72px"></div>' for _ in range(5)])}
  </div>
</div>
<script>
(function(){{
  var BASE="{BASE_URL}";
  function esc(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}}
  function rgb(h){{
    h=h.replace('#','');
    return parseInt(h.slice(0,2),16)+','+parseInt(h.slice(2,4),16)+','+parseInt(h.slice(4,6),16);
  }}
  function kpi(label,value,sub,vc){{
    return '<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);'
      +'border-radius:14px;padding:14px 16px">'
      +'<div style="font-family:JetBrains Mono,monospace;color:#8b93a7;font-size:10px;'
      +'letter-spacing:.16em;text-transform:uppercase">'+esc(label)+'</div>'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:22px;font-weight:700;'
      +'margin-top:6px;color:'+vc+'">'+esc(value)+'</div>'
      +'<div style="color:#8b93a7;font-size:11px;margin-top:3px">'+esc(sub)+'</div>'
      +'</div>';
  }}
  var TH_COLORS={{"GOLD":"#c9a84c","AI":"#4a9eff","QUANTUM":"#c084fc","BANKS":"#4ade80","SILVER":"#aab4be","WATCH":"#8b93a7"}};
  function pcolor(v){{return v>=0?"#4ade80":"#ff5566";}}
  function render_portfolio(d){{
    var el=document.getElementById("portfolio-table-live");
    if(!el)return;
    var rawPositions=d.positions||[];
    var positions=Array.isArray(rawPositions)
      ? rawPositions
      : Object.keys(rawPositions).map(function(t){{
          var p=rawPositions[t]||{{}};
          p.ticker=p.ticker||t;
          return p;
        }});
    if(!positions.length){{el.innerHTML='<div style="color:#8b93a7;font-size:12px;padding:8px 0">No positions.</div>';return;}}
    var ts=(d.portfolio_updated_at||"").slice(11,16);
    var rows="";
    for(var i=0;i<positions.length;i++){{
      var p=positions[i];
      var th=p.thesis||"WATCH";
      var thc=TH_COLORS[th]||"#8b93a7";
      var avg=(p.avg_price!==null&&p.avg_price!==undefined)?p.avg_price:p.avg_cost;
      if((avg===null||avg===undefined)&&p.cost_basis&&p.qty)avg=p.cost_basis/p.qty;
      var avgStr=(avg===null||avg===undefined||isNaN(parseFloat(avg)))?"--":"$"+parseFloat(avg).toFixed(3);
      var unrl=p.unrealized||0;var unrlp=p.unrealized_p||0;var unrlC=pcolor(unrl);
      rows+='<tr>'
        +'<td style="color:#c084fc;font-weight:700;padding:5px 6px">'+esc(p.ticker)+'</td>'
        +'<td style="color:#8b93a7;padding:5px 6px">'+(p.qty||0).toFixed(0)+'</td>'
        +'<td style="padding:5px 6px">$'+(p.price||0).toFixed(2)+'</td>'
        +'<td style="color:#8b93a7;font-family:JetBrains Mono,monospace;padding:5px 6px">'+avgStr+'</td>'
        +'<td style="color:'+unrlC+';font-family:JetBrains Mono,monospace;padding:5px 6px">'
        +(unrl>=0?"+$":"-$")+Math.abs(unrl).toFixed(2)+'</td>'
        +'<td style="padding:5px 6px"><span style="background:rgba('+rgb(thc)+',.15);color:'+thc
        +';font-size:9px;padding:2px 6px;border-radius:4px;font-family:JetBrains Mono,monospace;letter-spacing:.08em">'+esc(th)+'</span></td>'
        +'</tr>';
    }}
    var cpc=d.cash_color||"#e6edf3";var plc=d.pnl_color||"#e6edf3";
    var footer='<div style="margin-top:12px;padding-top:10px;border-top:1px solid rgba(255,255,255,.06);'
      +'display:flex;gap:20px;font-family:JetBrains Mono,monospace;font-size:11px;flex-wrap:wrap">'
      +'<span style="color:#8b93a7">MKT <span style="color:#e6edf3">'+esc(d.market_val_fmt||"")+'</span></span>'
      +'<span style="color:#8b93a7">CASH <span style="color:'+cpc+'">'+esc(d.cash_fmt||"")+' ('+((d.cash_pct||0).toFixed(0))+'%)</span></span>'
      +'<span style="color:#8b93a7">P/L <span style="color:'+plc+'">'+esc(d.pnl_fmt||"")+'</span></span>'
      +(ts?'<span style="color:#555;margin-left:auto;font-size:9px;letter-spacing:.1em">LIVE · '+esc(ts)+' SGT</span>':"")
      +'</div>';
    el.innerHTML='<table style="width:100%;border-collapse:collapse;font-family:JetBrains Mono,monospace;font-size:12px">'
      +'<tr style="border-bottom:1px solid rgba(192,132,252,.2)">'
      +'<th style="color:#c084fc;font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 6px 8px;text-align:left">Ticker</th>'
      +'<th style="color:#c084fc;font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 6px 8px;text-align:left">Qty</th>'
      +'<th style="color:#c084fc;font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 6px 8px;text-align:left">Price</th>'
      +'<th style="color:#c084fc;font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 6px 8px;text-align:left">Ave Price</th>'
      +'<th style="color:#c084fc;font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 6px 8px;text-align:left">P/L</th>'
      +'<th style="color:#c084fc;font-size:9px;letter-spacing:.12em;text-transform:uppercase;padding:4px 6px 8px;text-align:left">Thesis</th>'
      +'</tr>'+rows+'</table>'+footer;
  }}
  function fmt_chg(v){{
    if(v===null||v===undefined||v===0||v==="0")return{{s:"--",c:"#8b93a7"}};
    var f=parseFloat(v);
    if(isNaN(f)||f===0)return{{s:"--",c:"#8b93a7"}};
    return{{s:(f>=0?"+":"")+f.toFixed(1)+"%",c:f>=0?"#4ade80":"#ff5566"}};
  }}
  function render_threat_signals(d){{
    var el=document.getElementById("threat-signals-live");
    if(!el)return;
    var ms=d.market_signals||{{}};
    var fg=d.fg_score;var fgl=d.fg_label||"";var fgc=d.fg_color||"#fbbf24";
    var sc=ms.sentiment_color||"#94a3b8";var sg=ms.sentiment||"";
    var da=ms.defensive_avg;var ga=ms.growth_avg;
    var html="";
    /* F&G row */
    if(fg!==null&&fg!==undefined){{
      html+='<div style="display:flex;align-items:center;gap:8px;padding:7px 0;'
        +'border-bottom:1px solid rgba(255,255,255,.05);">'
        +'<span style="font-size:13px;flex-shrink:0">📊</span>'
        +'<span style="font-size:12px;color:#ccd5e3;line-height:1.5">'
        +'Fear &amp; Greed <span style="color:'+fgc+';font-weight:700">'+esc(fg)+'/100 '+esc(fgl)+'</span></span>'
        +'</div>';
    }}
    /* Sector sentiment row */
    if(sg&&sg!=="INSUFFICIENT_DATA"){{
      var sgLabel=sg.replace(/_/g," ");
      var dStr=(da!==null&&da!==undefined)?"DEF "+(da>=0?"+":"")+parseFloat(da).toFixed(1)+"%":"";
      var gStr=(ga!==null&&ga!==undefined)?"GRW "+(ga>=0?"+":"")+parseFloat(ga).toFixed(1)+"%":"";
      html+='<div style="display:flex;align-items:flex-start;gap:8px;padding:7px 0;'
        +'border-bottom:1px solid rgba(255,255,255,.05);">'
        +'<span style="font-size:13px;flex-shrink:0">📈</span>'
        +'<span style="font-size:12px;color:#ccd5e3;line-height:1.5">'
        +'Inst Sentiment <span style="color:'+sc+';font-weight:700">'+esc(sgLabel)+'</span>'
        +(dStr||gStr?'<br><span style="font-size:10px;font-family:JetBrains Mono,monospace;color:#8b93a7">'
          +(dStr?'<span style="color:#fbbf24">'+esc(dStr)+'</span> ':"")+' '
          +(gStr?'<span style="color:#4ade80">'+esc(gStr)+'</span>':"")+'</span>':"")
        +'</span></div>';
    }}
    el.innerHTML=html;
  }}
  function render(d){{
    var rc=d.regime_color||"#fbbf24";
    var ic=d.integrity_color||"#4ade80";
    /* Live regime label: show (LIVE) indicator when overridden by thesis probe */
    var regimeSrc=d._live_regime_active?"LIVE · ":"";
    var bar='<div style="background:rgba('+rgb(rc)+',0.10);border-left:4px solid '+rc+';'
      +'border-radius:10px;padding:14px 20px;margin-bottom:14px;'
      +'display:flex;align-items:center;gap:24px;flex-wrap:wrap;font-family:JetBrains Mono,monospace">'
      +'<span style="font-size:22px;font-weight:700;color:'+rc+';letter-spacing:.05em">'
      +esc(d.regime_emoji||"")+'&nbsp;'+esc(d.regime_short||"")+'</span>'
      +'<span style="font-size:13px;color:#e6edf3;font-weight:600">CIO:&nbsp;'
      +'<span style="color:'+rc+'">'+esc(d.cio_action||"")+'</span></span>'
      +(d._live_regime_basis?'<span style="font-size:10px;color:#555;font-family:JetBrains Mono,monospace">'+esc(d._live_regime_basis)+'</span>':"")
      +'<span style="font-size:11px;color:#8b93a7;margin-left:auto">'
      +regimeSrc+'Portfolio&nbsp;·&nbsp;'+esc(d.generated_at||"")+'&nbsp;&nbsp;·&nbsp;&nbsp;'
      +'Integrity&nbsp;<span style="color:'+ic+';font-weight:700">'+esc(d.integrity||"")+'</span>'
      +'</span></div>';
    var vixVal=d.vix||"N/A";
    var vixColor=(parseFloat(vixVal)>25)?"#ff5566":((parseFloat(vixVal)>20)?"#fbbf24":"#4ade80");
    var strip='<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:16px">'
      +kpi("VIX",esc(vixVal),"Volatility Index",vixColor)
      +kpi("Fear & Greed",(d.fg_score||"N/A")+"/100",esc(d.fg_label||""),d.fg_color||"#fbbf24")
      +kpi("Regime Score",esc(String(d.regime_score||"N/A")),esc(d.regime_short||""),rc)
      +kpi("Portfolio",esc(d.market_val_fmt||""),"P/L "+esc(d.pnl_fmt||""),d.pnl_color||"#e6edf3")
      +kpi("Cash Reserve",esc(d.cash_pct_fmt||""),esc(d.cash_fmt||""),d.cash_color||"#e6edf3")
      +'</div>';
    document.getElementById("fund-live").innerHTML=bar+strip;
    render_portfolio(d);
    render_threat_signals(d);
  }}
  function load(){{
    /* Parallel fetch: portfolio data (Moomoo, hourly) + thesis probe (10-min live regime) */
    Promise.all([
      fetch(BASE+"/data/portfolio_live.json?t="+Date.now()).then(function(r){{return r.json();}}).catch(function(){{return {{}}}}),
      fetch(BASE+"/data/thesis_evidence_live.json?t="+Date.now()).then(function(r){{return r.json();}}).catch(function(){{return {{}}}})
    ]).then(function(results){{
      var d=results[0]||{{}};
      var td=results[1]||{{}};
      var lr=td.live_regime;
      /* Override stale pipeline regime with live 10-min probe data when available */
      if(lr&&lr.regime&&lr.regime!=="UNKNOWN"&&lr.regime_score!==undefined){{
        d.regime_short  = lr.regime_short  || d.regime_short;
        d.regime_score  = lr.regime_score;
        d.regime_color  = lr.regime_color  || d.regime_color;
        d.regime_emoji  = lr.regime_emoji  || d.regime_emoji;
        /* CIO action follows live regime */
        if(lr.regime.indexOf("OFF")>=0){{d.cio_action="WAIT / HOLD";}}
        else if(lr.regime==="NEUTRAL"){{d.cio_action="WATCH";}}
        else{{d.cio_action="HOLD / REVIEW";}}
        /* VIX from live probe (actual index level) */
        if(lr.vix_level&&lr.vix_level>0){{d.vix=lr.vix_level.toFixed(1);d.vix_alert=lr.vix_level>20;}}
        d._live_regime_active=true;
        d._live_regime_basis=lr.basis||"";
      }}
      render(d);
    }}).catch(function(){{}});
  }}
  load();
  setInterval(load,60000);
}})();
</script>"""

    # ── Threat Board (left column) ─────────────────────────────────────────────
    # Static warn_items (regime.warnings strings from dataset_raw.json) removed —
    # they duplicated F/G and sentiment signals now shown live in threat-signals-live.
    # Only geo_banner is retained: geopolitical alerts are pipeline-derived intel,
    # not replaceable by market data signals.
    geo = extract_geo_alert(event_corr)

    geo_banner = ""
    if geo:
        geo_banner = (
            f'<div style="background:rgba(255,85,102,.12);border:1px solid #ff5566;'
            f'border-radius:8px;padding:10px 12px;margin-bottom:10px;'
            f'font-family:JetBrains Mono,monospace;font-size:11px;color:#ff5566;line-height:1.5">'
            f'<span style="font-weight:700">⚡ GEO ALERT</span><br>'
            f'{html_escape(clean_text(geo, 120))}'
            f'</div>'
        )

    threat_col = f"""
<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);
  border-radius:18px;padding:18px;">
  <div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;
    text-transform:uppercase;color:#ff5566;margin-bottom:12px;display:flex;
    align-items:center;gap:8px">Threat Board
    <span style="height:1px;background:rgba(255,85,102,.25);flex:1;display:block"></span>
  </div>
  {geo_banner}
  <div id="threat-signals-live"></div>
</div>"""

    # ── Portfolio (centre column) — JS-driven from portfolio_live.json ───────
    # Positions are now rendered by render_portfolio() in the fund-live JS block.
    # The static Python build is skipped so the table always reflects the latest
    # portfolio_live.json push (hourly from portfolio_live_updater.py or each
    # pipeline cycle from build_portfolio_live()).
    portfolio_col = """
<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);
  border-radius:18px;padding:18px;">
  <div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;
    text-transform:uppercase;color:#c084fc;margin-bottom:12px;display:flex;
    align-items:center;gap:8px">Portfolio
    <span style="height:1px;background:rgba(192,132,252,.18);flex:1;display:block"></span>
  </div>
  <div id="portfolio-table-live" style="color:#555;font-size:11px;font-family:JetBrains Mono,monospace;padding:4px 0">
    Loading positions&hellip;
  </div>
</div>"""

    # ── Top Movers (right column) ──────────────────────────────────────────────
    ref_prices = get_reference_prices(ds)
    ref_line = ""
    if ref_prices:
        parts = []
        for t, chg in ref_prices.items():
            col = "#4ade80" if chg >= 0 else "#ff5566"
            parts.append(f'<span style="color:{col}">{t} {pct_short(chg)}</span>')
        ref_line = (
            f'<div style="font-size:10px;font-family:JetBrains Mono,monospace;'
            f'margin-bottom:10px;padding:6px 8px;background:rgba(255,255,255,.04);'
            f'border-radius:6px;display:flex;gap:12px;flex-wrap:wrap">'
            f'{"  ·  ".join(parts)}</div>'
        )

    # ── Situation Board (2 columns) ───────────────────────────────────────────
    sit_board = f"""
<div style="display:grid;grid-template-columns:1fr 1.5fr;gap:14px;margin-bottom:16px">
  {threat_col}
  {portfolio_col}
</div>"""

    # ── Event Correlation (top 4 + breadth summary) ───────────────────────────
    ro_count     = sum(1 for ev in event_corr if "RISK-OFF" in str(ev.get("direction","")).upper())
    breadth_col  = "#ff5566" if ro_count >= len(event_corr) / 2 else "#4ade80"
    breadth_line = (
        f'<div style="font-family:JetBrains Mono,monospace;font-size:11px;'
        f'color:{breadth_col};margin-bottom:10px;letter-spacing:.08em">'
        f'{ro_count}/{len(event_corr)} baskets RISK-OFF'
        f'</div>'
    ) if event_corr else ""

    event_cards = ""
    for ev in event_corr[:4]:
        move  = safe_float(ev.get("basket_move"))
        conf  = safe_float(ev.get("confidence"))
        dirn  = str(ev.get("direction","WATCH")).upper()
        dirn_col = "#ff5566" if "OFF" in dirn else ("#4ade80" if "ON" in dirn else "#fbbf24")
        event_cards += (
            f'<div style="background:rgba(13,16,32,.86);border:1px solid rgba(255,255,255,.06);'
            f'border-radius:14px;padding:14px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
            f'<b style="color:#fff;font-size:13px">{html_escape(ev.get("theme","EVENT"))}</b>'
            f'<span style="color:{dirn_col};font-family:JetBrains Mono,monospace;font-size:9px;'
            f'letter-spacing:.08em">{html_escape(dirn)}</span>'
            f'</div>'
            f'<p style="color:#bfc8d7;font-size:12px;margin:0 0 6px;line-height:1.5">'
            f'{html_escape(clean_text(ev.get("why"), 130))}</p>'
            f'<div style="color:#8b93a7;font-size:11px;font-family:JetBrains Mono,monospace">'
            f'Conf {conf:.0f}% &nbsp;·&nbsp; Basket '
            f'<strong style="color:{pct_color(move)}">{pct_short(move)}</strong>'
            f'</div></div>'
        )
    if not event_cards:
        event_cards = '<p style="color:#8b93a7">No event correlations available.</p>'

    event_section = f"""
<div style="margin-bottom:16px">
  <div style="font-family:JetBrains Mono,monospace;font-size:11px;letter-spacing:.18em;
    text-transform:uppercase;color:#c084fc;margin-bottom:8px;display:flex;
    align-items:center;gap:10px">Event Correlation Engine
    <span style="height:1px;background:rgba(192,132,252,.18);flex:1;display:block"></span>
  </div>
  {breadth_line}
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px">{event_cards}</div>
</div>"""

    # ── S3 · Thesis Evidence — live JS fetch from thesis_evidence_live.json ──
    thesis_section = f"""<div id="thesis-live" style="margin-bottom:16px">
  <div style="background:rgba(13,16,32,.60);border:1px solid rgba(192,132,252,.14);
    border-radius:12px;padding:14px 24px;color:#444;font-family:JetBrains Mono,monospace;
    font-size:10px;letter-spacing:.12em">S3 · THESIS EVIDENCE — loading…</div>
</div>
<script>
(function(){{
  var BASE="{BASE_URL}";
  var STATUS_COLOR={{
    "CONFIRMING":"#4ade80","WATCH":"#fbbf24",
    "WARNING":"#ff5566","FAILING":"#ef4444"
  }};
  var DIR_COLOR={{
    "RISK ON":"#4ade80","RISK-ON":"#4ade80","RISK_ON":"#4ade80",
    "RISK OFF":"#ff5566","RISK-OFF":"#ff5566","RISK_OFF":"#ff5566",
    "SELECTIVE RISK ON":"#86efac","SELECTIVE_RISK_ON":"#86efac",
    "SELECTIVE RISK OFF":"#fca5a5","SELECTIVE_RISK_OFF":"#fca5a5",
    "WATCH":"#fbbf24","NEUTRAL":"#94a3b8"
  }};
  var CHECK_NAMES={{
    "gold_stabilizes_and_rises":"Gold Spot",
    "silver_confirms_or_gsr_compresses":"Silver / GSR",
    "miners_vs_gold":"Miners vs GLD",
    "au_nem_vs_gdx":"AU/NEM vs GDX",
    "real_yields_do_not_spike":"Real Yields",
    "dxy_does_not_surge":"USD / DXY",
    "oil_risk_premium_elevated":"Oil-Risk Premium",
    "miners_not_liquidated_as_equity_beta":"Miner Liq Risk"
  }};
  var CHECK_COLOR={{"PASS":"#4ade80","WATCH":"#fbbf24","FAIL":"#ff5566","MISSING":"#444"}};
  function esc(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}}
  function badge(txt,col){{
    return '<span style="background:'+col+'22;color:'+col+';border-radius:4px;'
      +'padding:2px 7px;font-size:11px;font-weight:600">'+esc(txt)+'</span>';
  }}
  function render(d){{
    var gt=d.gold_thesis||{{}}, checks=gt.checks||{{}};
    var st=gt.status||"UNKNOWN", score=gt.score||0, conf=gt.confidence||"";
    var sc=STATUS_COLOR[st]||"#94a3b8";
    var n_p=gt.n_pass||0, n_w=gt.n_watch||0, n_f=gt.n_fail||0;
    var n_m=gt.n_missing||0, action=gt.core_action||"";

    // ── Gold Thesis status card ───────────────────────────────────────────
    var km=gt.key_metrics||{{}};
    var metrics="";
    [["GLD",km.gld_chg_pct],["GDX",km.gdx_chg_pct],["SLV",km.slv_chg_pct],
     ["UUP",km.uup_chg_pct],["TLT",km.tlt_chg_pct],["XLE",km.xle_chg_pct],
     ["SPY",km.spy_chg_pct]].forEach(function(pair){{
      if(pair[1]===null||pair[1]===undefined) return;
      var v=parseFloat(pair[1]), col=v>=0?"#4ade80":"#ff5566";
      metrics+='<span style="margin-right:12px;white-space:nowrap">'
        +'<span style="color:#555">'+pair[0]+'</span>&nbsp;'
        +'<span style="color:'+col+'">'+(v>=0?"+":"")+v.toFixed(2)+'%</span></span>';
    }});

    var checksHtml="";
    Object.keys(CHECK_NAMES).forEach(function(k){{
      var c=checks[k]||{{}}, cst=c.status||"MISSING";
      var col=CHECK_COLOR[cst]||"#444";
      checksHtml+='<div style="display:flex;align-items:baseline;gap:8px;'
        +'padding:3px 0;border-bottom:1px solid rgba(255,255,255,.03)">'
        +'<span style="color:'+col+';font-size:10px;font-weight:700;width:14px;flex-shrink:0">'
        +(cst==="PASS"?"✓":cst==="FAIL"?"✗":cst==="WATCH"?"~":"·")+'</span>'
        +'<span style="color:#94a3b8;font-size:11px;flex:1">'+esc(CHECK_NAMES[k])+'</span>'
        +'<span style="color:#555;font-size:10px;text-align:right;max-width:220px;'
        +'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'+esc(c.evidence||"")+'</span>'
        +'</div>';
    }});

    var statusCard=
      '<div style="background:rgba(13,16,32,.97);border:1px solid '+sc+'44;'
      +'border-radius:12px;padding:18px 22px;margin-bottom:10px">'
      +'<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px;flex-wrap:wrap">'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:11px;letter-spacing:.18em;'
      +'text-transform:uppercase;color:#c084fc;font-weight:700">S3 · GOLD THESIS</div>'
      +'<span style="height:1px;background:rgba(192,132,252,.18);flex:1;display:block;min-width:20px"></span>'
      +'<span style="font-size:9px;color:#555;font-family:JetBrains Mono,monospace">Live · '+esc(d.generated_at||"")+'</span>'
      +'</div>'
      +'<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">'
      +'<div>'
      +'<div style="margin-bottom:10px">'+badge(st,sc)
      +'&nbsp;<span style="color:#94a3b8;font-size:12px">Score '+score.toFixed(2)+'/1.00'
      +' · Confidence <span style="color:'+sc+'">'+esc(conf)+'</span></span></div>'
      +'<div style="font-size:11px;color:#555;margin-bottom:6px">'
      +'<span style="color:#4ade80">'+n_p+' PASS</span>'
      +' · <span style="color:#fbbf24">'+n_w+' WATCH</span>'
      +' · <span style="color:#ff5566">'+n_f+' FAIL</span>'
      +(n_m?' · <span style="color:#444">'+n_m+' MISSING</span>':"")+'</div>'
      +'<div style="font-size:11px;color:#94a3b8;margin-bottom:10px">'
      +'CIO Action: <span style="color:#e2e8f0;font-weight:600">'+esc(action)+'</span>'
      +'&nbsp;·&nbsp;Thesis Add Signal: <span style="color:#e2e8f0">'
      +esc(gt.thesis_add_signal||gt.gold_thesis_add_signal||(gt.add_allowed?"THESIS_SUPPORTS_ADD":"THESIS_HOLD_ONLY"))+'</span>'
      +'&nbsp;·&nbsp;Execution Permission: <span style="color:'+((String(gt.execution_permission||gt.gold_execution_permission||"").indexOf("BLOCKED")>=0)?"#ff5566":"#fbbf24")+'">'
      +esc(gt.execution_permission||gt.gold_execution_permission||(gt.add_allowed?"EXECUTION_REQUIRES_CIO_REVIEW":"EXECUTION_BLOCKED_REQUIRES_CIO_REVIEW"))+'</span></div>'
      +'<div style="font-size:11px;color:#555;font-family:JetBrains Mono,monospace;'
      +'overflow-x:auto;white-space:nowrap">'+metrics+'</div>'
      +'</div>'
      +'<div>'+checksHtml+'</div>'
      +'</div>'
      +'</div>';

    // ── Event Correlations table ─────────────────────────────────────────
    var rows=d.event_correlations||[], corr_ts=d.generated_at||d.correlations_as_of||"";
    var corrHtml="";
    if(rows.length){{
      var thead='<table style="width:100%;border-collapse:collapse;font-size:12px">'
        +'<thead><tr style="color:#94a3b8;border-bottom:1px solid rgba(255,255,255,.08)">'
        +'<th style="text-align:left;padding:4px 8px;font-weight:500;white-space:nowrap">THEME</th>'
        +'<th style="text-align:center;padding:4px 8px;font-weight:500;white-space:nowrap">DIRECTION</th>'
        +'<th style="text-align:center;padding:4px 8px;font-weight:500;white-space:nowrap">AVG MOVE</th>'
        +'<th style="text-align:left;padding:4px 8px;font-weight:500">BASKET TICKERS &amp; LOGIC</th>'
        +'<th style="text-align:center;padding:4px 8px;font-weight:500;white-space:nowrap">TIER</th>'
        +'</tr></thead><tbody>';
      var tbody="";
      rows.slice(0,12).forEach(function(r){{
        // Normalise direction — handle RISK_ON, RISK-ON, SELECTIVE_RISK_OFF etc.
        var dirRaw=(r.direction||"WATCH").toUpperCase();
        var dc=DIR_COLOR[dirRaw]||"#94a3b8";
        var dirLabel=dirRaw.replace(/_/g," ");
        var bm=r.basket_move!=null?((r.basket_move>=0?"+":"")+parseFloat(r.basket_move).toFixed(2)+"%"):"—";
        var bmCol=parseFloat(r.basket_move||0)>=0?"#4ade80":"#ff5566";
        var tier=String(r.tier||r.evidence_tier_label||r.confidence||"");

        // Build ticker chip evidence
        var evHtml="";
        if(r.tickers&&r.tickers.length){{
          var chips="";
          r.tickers.slice(0,6).forEach(function(tk){{
            var chg=parseFloat(tk.chg||0);
            var col=chg>0.05?"#4ade80":chg<-0.05?"#ff5566":"#8b93a7";
            var sign=chg>=0?"+":"";
            chips+='<span style="display:inline-block;margin:1px 5px 1px 0;'
              +'white-space:nowrap;font-size:10px;font-family:JetBrains Mono,monospace;'
              +'color:'+col+'">'
              +esc(tk.t)+'&nbsp;<b>'+sign+chg.toFixed(2)+'%</b></span>';
          }});
          var qual=r.qualifying_rule?
            '<div style="font-size:9px;color:#555;margin-top:3px;letter-spacing:.05em">'+esc(r.qualifying_rule)+'</div>':"";
          evHtml=chips+qual;
        }} else {{
          // Fallback: show old why/evidence text for pipeline-sourced rows
          evHtml='<span style="font-size:11px;color:#555">'+esc(String(r.why||r.evidence||"").substring(0,70))+'</span>';
        }}

        tbody+='<tr style="border-bottom:1px solid rgba(255,255,255,.04);color:#e2e8f0">'
          +'<td style="padding:5px 8px;white-space:nowrap;font-weight:500">'+esc(r.theme||"")+'</td>'
          +'<td style="padding:5px 8px;text-align:center">'+badge(dirLabel,dc)+'</td>'
          +'<td style="padding:5px 8px;text-align:center;color:'+bmCol+';font-weight:600;'
          +'font-family:JetBrains Mono,monospace">'+esc(bm)+'</td>'
          +'<td style="padding:5px 8px">'+evHtml+'</td>'
          +'<td style="padding:5px 8px;text-align:center;color:#555;font-size:10px;'
          +'font-family:JetBrains Mono,monospace;white-space:nowrap">'+esc(tier)+'</td>'
          +'</tr>';
      }});
      corrHtml='<div style="margin-top:10px">'
        +'<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#555;'
        +'letter-spacing:.10em;margin-bottom:6px">S3 · THESIS EVIDENCE'
        +(corr_ts?' <span style="color:#444;font-size:9px">· '+esc(corr_ts)+'</span>':"")+'</div>'
        +thead+tbody+'</tbody></table></div>';
    }}

    // ── Methodology footnote ─────────────────────────────────────────────
    var meth=
      '<details style="margin-top:12px">'
      +'<summary style="font-family:JetBrains Mono,monospace;font-size:9px;'
      +'letter-spacing:.12em;color:#444;cursor:pointer;user-select:none;'
      +'text-transform:uppercase">▸ Methodology</summary>'
      +'<div style="margin-top:8px;font-size:11px;color:#555;line-height:1.7;'
      +'border-top:1px solid rgba(255,255,255,.05);padding-top:10px">'
      +'<div style="margin-bottom:8px">'
      +'<span style="color:#94a3b8;font-weight:600">Gold Thesis Score</span>&nbsp;'
      +'8 checks evaluated against live market prices (10-min yfinance refresh).<br>'
      +'Each check: <span style="color:#4ade80">PASS=1.0</span>'
      +' · <span style="color:#fbbf24">WATCH=0.5</span>'
      +' · <span style="color:#ff5566">FAIL=0.0</span>'
      +' · <span style="color:#444">MISSING=excluded</span><br>'
      +'Score = average of available (non-MISSING) checks.<br>'
      +'<span style="color:#4ade80">CONFIRMING ≥0.75</span>'
      +' · <span style="color:#fbbf24">WATCH 0.50–0.74</span>'
      +' · <span style="color:#ff5566">WARNING 0.30–0.49</span>'
      +' · <span style="color:#ef4444">FAILING &lt;0.30</span>'
      +'</div>'
      +'<div style="margin-bottom:8px">'
      +'<span style="color:#94a3b8;font-weight:600">5 Critical Checks</span>&nbsp;'
      +'Gold spot · Miners vs GLD · AU/NEM vs GDX · Real yields · Miner liquidation risk.<br>'
      +'Confidence degrades when critical checks fail: '
      +'<span style="color:#4ade80">HIGH</span> (0 critical fails)'
      +' → <span style="color:#fbbf24">MEDIUM</span>'
      +' → <span style="color:#ff5566">MEDIUM_LOW</span>'
      +' → <span style="color:#ef4444">LOW</span>'
      +'</div>'
      +'<div>'
      +'<span style="color:#94a3b8;font-weight:600">ECE Basket Tickers</span>&nbsp;'
      +'12 themes, each with a fixed ticker basket (4–7 names). '
      +'Basket move = average % change across available tickers vs prior close (yfinance, 10-min refresh).<br>'
      +'Direction rule: avg ≥+0.5% &amp; ≥60% pos → <span style="color:#4ade80">RISK ON</span> · '
      +'avg ≥+0.1% → <span style="color:#86efac">SELECTIVE RISK ON</span> · '
      +'avg &lt;-0.5% &amp; ≤40% pos → <span style="color:#ff5566">RISK OFF</span> · '
      +'avg &lt;-0.1% → <span style="color:#fca5a5">SELECTIVE RISK OFF</span> · else NEUTRAL.<br>'
      +'Qualifying logic (N/M pos · avg X%) shown below each ticker row. '
      +'Tickers sorted by absolute move (largest first). Fully independent of V2 pipeline.'
      +'</div>'
      +'</div>'
      +'</details>';

    document.getElementById("thesis-live").innerHTML=
      '<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);'
      +'border-radius:12px;padding:18px 22px;margin-bottom:16px">'
      +statusCard+corrHtml+meth
      +'</div>';
  }}
  function load(){{
    fetch(BASE+"/data/thesis_evidence_live.json?t="+Date.now())
      .then(function(r){{return r.json();}})
      .then(render)
      .catch(function(e){{
        document.getElementById("thesis-live").innerHTML=
          '<div style="background:rgba(13,16,32,.60);border:1px solid rgba(192,132,252,.14);'
          +'border-radius:12px;padding:14px 24px;color:#444;font-family:JetBrains Mono,monospace;'
          +'font-size:10px">S3 · THESIS EVIDENCE — data pending (thesis_probe_daemon not running?)</div>';
      }});
  }}
  load();
  setInterval(load, 600000);
}})();
</script>"""

    # ── S4 · Hawkish Warsh Thesis — live JS fetch from warsh_thesis_live.json ──
    warsh_section = f"""<div id="warsh-live" style="margin-bottom:16px">
  <div style="background:rgba(13,16,32,.60);border:1px solid rgba(251,191,36,.12);
    border-radius:12px;padding:14px 24px;color:#444;font-family:JetBrains Mono,monospace;
    font-size:10px;letter-spacing:.12em">S4 · HAWKISH WARSH THESIS — loading…</div>
</div>
<script>
(function(){{
  var BASE="{BASE_URL}";
  function esc(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}}
  var STATUS_COLOR={{
    "CONFIRMING":"#4ade80","PARTIAL_CONFIRMATION":"#fbbf24","MIXED":"#fbbf24",
    "WARNING":"#f97316","FAILING":"#ff5566","INSUFFICIENT_DATA":"#94a3b8"
  }};
  var GATE_COLOR={{
    "PASS":"#4ade80","WATCH":"#fbbf24","FAIL":"#ff5566",
    "HAWKISH":"#4ade80","MIXED":"#fbbf24","DOVISH":"#ff5566",
    "LOW":"#4ade80","ACTIVE":"#f97316","SEVERE":"#ff5566",
    "CALM":"#4ade80","STRESS":"#ff5566","UNKNOWN":"#94a3b8"
  }};

  /* format a % value with sign */
  function fp(v){{
    if(v===null||v===undefined)return"–";
    var f=parseFloat(v);if(isNaN(f))return"–";
    return(f>=0?"+":"")+f.toFixed(2)+"%";
  }}
  /* color: green=up, red=down; inv=true flips (e.g. VXX down is good) */
  function pc(v,inv){{
    if(v===null||v===undefined)return"#8b93a7";
    var f=parseFloat(v);if(isNaN(f)||f===0)return"#8b93a7";
    var good=f>0;if(inv)good=!good;
    return good?"#4ade80":"#ff5566";
  }}
  /* one metric row: label on left, value on right */
  function mr(label,val,color){{
    return'<div style="display:flex;justify-content:space-between;align-items:baseline;'
      +'padding:1.5px 0;border-bottom:1px solid rgba(255,255,255,.03)">'
      +'<span style="color:#555;font-size:9px;font-family:JetBrains Mono,monospace;'
      +'white-space:nowrap">'+esc(label)+'</span>'
      +'<span style="color:'+(color||"#cbd5e1")+';font-size:10px;font-weight:600;'
      +'font-family:JetBrains Mono,monospace;margin-left:8px">'+esc(String(val!==undefined&&val!==null?val:"–"))+'</span>'
      +'</div>';
  }}
  /* gate panel: title, status badge, score, metric rows */
  function gp(title,status,weight,score,metricsHtml){{
    var sc=GATE_COLOR[String(status).toUpperCase()]||"#94a3b8";
    var sc2=GATE_COLOR[String(status)]||"#94a3b8";
    var finalSc=sc!="#94a3b8"?sc:sc2;
    return'<div style="background:rgba(8,10,24,.92);border:1px solid rgba(255,255,255,.09);'
      +'border-top:2px solid '+finalSc+';border-radius:8px;padding:10px 12px;'
      +'flex:1;min-width:160px;box-sizing:border-box">'
      +'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:7px">'
      +'<div>'
      +'<div style="font-size:8px;color:#555;letter-spacing:.14em;text-transform:uppercase;'
      +'font-family:JetBrains Mono,monospace;margin-bottom:3px">'+esc(title)+'</div>'
      +'<div style="font-size:13px;font-weight:700;color:'+finalSc+'">'+esc(String(status))+'</div>'
      +'</div>'
      +'<div style="text-align:right;flex-shrink:0;margin-left:6px">'
      +'<div style="font-size:7px;color:#444;font-family:JetBrains Mono,monospace;letter-spacing:.10em">SCORE</div>'
      +'<div style="font-size:14px;font-weight:700;color:'+finalSc+';line-height:1.1">'
      +score+'<span style="color:#444;font-size:8px">/'+weight+'</span></div>'
      +'</div></div>'
      +'<div style="border-top:1px solid rgba(255,255,255,.06);padding-top:5px">'+metricsHtml+'</div>'
      +'</div>';
  }}

  function render(d){{
    var status=d.status||"INSUFFICIENT_DATA";
    var score=(d.score!=null)?d.score:"–";
    var sc=STATUS_COLOR[status]||"#94a3b8";
    var gen=d.generated_at||"";
    var cio=d.cio_action||"–";
    var statusLabel=status.replace(/_/g," ");

    var ft=d.fed_tone||{{}};
    var rc=d.rates_confirmation||{{}};
    var dc=d.dollar_confirmation||{{}};
    var bc=d.bank_confirmation||{{}};
    var gm=d.gold_miner_confirmation||{{}};
    var hb=d.high_beta_risk||{{}};
    var cs=d.credit_stress||{{}};
    var yc=d.yen_carry_risk||{{}};

    /* ── 8 gate panels with live metric values ── */

    var pFed=gp("FED TONE · 20pt",ft.status||"UNKNOWN",20,(ft.score||0).toFixed(1),
      mr("Hawkish signals",(ft.hawkish_count!==undefined?ft.hawkish_count:"–"),"#e2e8f0")
      +mr("Dovish signals",(ft.dovish_count!==undefined?ft.dovish_count:"–"),"#e2e8f0")
      +(ft.evidence&&ft.evidence[0]
        ?'<div style="color:#555;font-size:9px;font-family:JetBrains Mono,monospace;'
          +'margin-top:5px;line-height:1.45;border-top:1px solid rgba(255,255,255,.04);padding-top:4px">'
          +esc((ft.evidence[0]||"").substring(0,72))+'</div>'
        :"")
    );

    /* RATES color logic:
       TLT/IEF/SHY are bond PRICES — falling = yields rising = hawkish confirm = GREEN → inv=true
       10Y/30Y yield Δ — positive = yield rising = hawkish confirm = GREEN → no inv */
    var pRates=gp("RATES · 15pt",rc.status||"–",15,(rc.score||0).toFixed(1),
      mr("TLT (bond price)",fp(rc.tlt_change_pct),pc(rc.tlt_change_pct,true))
      +mr("IEF (bond price)",fp(rc.ief_change_pct),pc(rc.ief_change_pct,true))
      +mr("SHY (bond price)",fp(rc.shy_change_pct),pc(rc.shy_change_pct,true))
      +mr("10Y yield Δ",fp(rc.us_10y_proxy),pc(rc.us_10y_proxy))
      +mr("30Y yield Δ",fp(rc.us_30y_proxy),pc(rc.us_30y_proxy))
    );

    var pDollar=gp("DOLLAR · 10pt",dc.status||"–",10,(dc.score||0).toFixed(1),
      mr("UUP",fp(dc.uup_change_pct),pc(dc.uup_change_pct))
      +(dc.evidence&&dc.evidence[0]
        ?'<div style="color:#555;font-size:9px;font-family:JetBrains Mono,monospace;'
          +'margin-top:5px;border-top:1px solid rgba(255,255,255,.04);padding-top:4px">'
          +esc((dc.evidence[0]||"").substring(0,55))+'</div>'
        :"")
    );

    var pBanks=gp("BANKS · 15pt",bc.status||"–",15,(bc.score||0).toFixed(1),
      mr("XLF",fp(bc.xlf_change_pct),pc(bc.xlf_change_pct))
      +mr("JPM",fp(bc.jpm_change_pct),pc(bc.jpm_change_pct))
      +mr("BAC",fp(bc.bac_change_pct),pc(bc.bac_change_pct))
      +mr("GS",fp(bc.gs_change_pct),pc(bc.gs_change_pct))
      +mr("MS",fp(bc.ms_change_pct),pc(bc.ms_change_pct))
      +mr("HYG (credit)",fp(bc.hyg_change_pct),pc(bc.hyg_change_pct))
    );

    var pGold=gp("GOLD MINERS · 15pt",gm.status||"–",15,(gm.score||0).toFixed(1),
      mr("GLD",fp(gm.gld_change_pct),pc(gm.gld_change_pct))
      +mr("GDX",fp(gm.gdx_change_pct),pc(gm.gdx_change_pct))
      +mr("GDXJ",fp(gm.gdxj_change_pct),pc(gm.gdxj_change_pct))
      +mr("AU",fp(gm.au_change_pct),pc(gm.au_change_pct))
      +mr("NEM",fp(gm.nem_change_pct),pc(gm.nem_change_pct))
      +mr("GDX−GLD spread",fp(gm.gdx_vs_gld_spread),pc(gm.gdx_vs_gld_spread))
    );

    var pHiBeta=gp("HIGH BETA · 10pt",hb.status||"–",10,(hb.score||0).toFixed(1),
      mr("QQQ",fp(hb.qqq_change_pct),pc(hb.qqq_change_pct))
      +mr("IWM",fp(hb.iwm_change_pct),pc(hb.iwm_change_pct))
      +mr("VXX",fp(hb.vxx_change_pct),pc(hb.vxx_change_pct,true))
      +mr("UVXY",fp(hb.uvxy_change_pct),pc(hb.uvxy_change_pct,true))
      +mr("NVDA",fp(hb.nvda_change_pct),pc(hb.nvda_change_pct))
      +(hb.red_flag?'<div style="color:#f97316;font-size:9px;margin-top:4px;'
        +'font-family:JetBrains Mono,monospace">⚠ RED FLAG ACTIVE</div>':"")
    );

    var pCredit=gp("CREDIT · 10pt",cs.status||"–",10,(cs.score||0).toFixed(1),
      mr("HYG",fp(cs.hyg_change_pct),pc(cs.hyg_change_pct))
      +mr("JNK",fp(cs.jnk_change_pct),pc(cs.jnk_change_pct))
      +mr("LQD",fp(cs.lqd_change_pct),pc(cs.lqd_change_pct))
    );

    var pYen=gp("YEN CARRY · 5pt",yc.status||"–",5,(yc.score||0).toFixed(1),
      mr("EWJ",fp(yc.ewj_change_pct),pc(yc.ewj_change_pct))
      +mr("VXX",fp(yc.vxx_change_pct),pc(yc.vxx_change_pct,true))
    );

    /* ── blocked / notes ── */
    var blockedHtml="";
    if((d.blocked_actions||[]).length){{
      blockedHtml='<div style="margin-top:10px;padding:7px 12px;'
        +'background:rgba(255,85,102,.08);border-left:3px solid #ff5566;'
        +'font-size:10px;color:#ff5566;font-family:JetBrains Mono,monospace;letter-spacing:.06em">'
        +'⚠ BLOCKED: '+esc(d.blocked_actions.join(" · "))+'</div>';
    }}
    var notesHtml="";
    if((d.notes||[]).length){{
      notesHtml='<div style="margin-top:8px;font-size:10px;color:#555;'
        +'font-family:JetBrains Mono,monospace;line-height:1.7">'
        +(d.notes.slice(0,4).map(function(n){{return"· "+esc(n);}}).join("<br>"))+'</div>';
    }}

    var html=
      '<div style="background:rgba(13,16,32,.94);border:1px solid rgba(251,191,36,.22);'
      +'border-radius:12px;padding:18px 22px;margin-bottom:16px">'
      /* header bar */
      +'<div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">'
      +'<span style="font-family:JetBrains Mono,monospace;font-size:11px;letter-spacing:.18em;'
      +'text-transform:uppercase;color:#fbbf24;font-weight:700">S4 · HAWKISH WARSH THESIS</span>'
      +'<span style="height:1px;background:rgba(251,191,36,.18);flex:1;display:block"></span>'
      +'<span style="font-size:9px;color:#444;font-family:JetBrains Mono,monospace">'+esc(gen)+'</span>'
      +'</div>'
      /* status + score + CIO action */
      +'<div style="display:flex;align-items:center;gap:20px;margin-bottom:16px;flex-wrap:wrap">'
      +'<div>'
      +'<div style="font-size:22px;font-weight:700;color:'+sc+';line-height:1.1">'+esc(statusLabel)+'</div>'
      +'<div style="font-size:11px;color:#8b93a7;font-family:JetBrains Mono,monospace;margin-top:3px">'
      +'Score&nbsp;<b style="color:'+sc+'">'+score+'</b>&nbsp;/&nbsp;100</div>'
      +'</div>'
      +'<div style="margin-left:auto;text-align:right">'
      +'<div style="font-size:9px;color:#555;font-family:JetBrains Mono,monospace;letter-spacing:.10em">CIO ACTION</div>'
      +'<div style="font-size:15px;font-weight:700;color:#e2e8f0;letter-spacing:.04em;margin-top:2px">'+esc(cio)+'</div>'
      +'</div>'
      +'</div>'
      /* row 1: FED TONE | RATES | DOLLAR | BANKS */
      +'<div style="display:flex;gap:8px;margin-bottom:8px;flex-wrap:wrap">'
      +pFed+pRates+pDollar+pBanks
      +'</div>'
      /* row 2: GOLD MINERS | HIGH BETA | CREDIT | YEN CARRY */
      +'<div style="display:flex;gap:8px;flex-wrap:wrap">'
      +pGold+pHiBeta+pCredit+pYen
      +'</div>'
      +blockedHtml+notesHtml
      +'</div>';

    document.getElementById("warsh-live").innerHTML=html;
  }}

  function load(){{
    var nonce=Date.now();
    var urls=[
      "https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO}/{GITHUB_BRANCH}/data/warsh_thesis_live.json?t="+nonce,
      BASE+"/data/warsh_thesis_live.json?t="+nonce
    ];
    function tryFetch(i){{
      return fetch(urls[i],{{cache:"no-store"}})
        .then(function(r){{if(!r.ok)throw new Error("HTTP "+r.status);return r.json();}})
        .catch(function(e){{if(i+1<urls.length)return tryFetch(i+1);throw e;}});
    }}
    tryFetch(0).then(render)
      .catch(function(e){{
        document.getElementById("warsh-live").innerHTML=
          '<div style="background:rgba(13,16,32,.60);border:1px solid rgba(251,191,36,.12);'
          +'border-radius:12px;padding:14px 24px;color:#444;font-family:JetBrains Mono,monospace;'
          +'font-size:10px">S4 · HAWKISH WARSH THESIS — data pending (warsh_thesis_probe_daemon not running?)</div>';
      }});
  }}
  load();
  setInterval(load, 600000);
}})();
</script>"""

    # ── S5 · BOJ / Yen Carry Event Watcher — live JS, 60s poll, narrative ──────
    boj_section = f"""<style>
@keyframes boj-pulse{{0%,100%{{box-shadow:0 0 0 0 rgba(249,115,22,.5)}}50%{{box-shadow:0 0 0 8px rgba(249,115,22,0)}}}}
@keyframes boj-pulse-severe{{0%,100%{{box-shadow:0 0 0 0 rgba(255,85,102,.6)}}50%{{box-shadow:0 0 0 14px rgba(255,85,102,0)}}}}
@keyframes dot-blink{{0%,100%{{opacity:1}}50%{{opacity:.15}}}}
</style>
<div id="boj-live" style="margin-bottom:16px">
  <div style="background:rgba(13,16,32,.60);border:1px solid rgba(34,211,238,.12);border-radius:12px;
    padding:14px 24px;color:#444;font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.12em">
    S5 · BOJ / YEN CARRY — loading…</div>
</div>
<script>
(function(){{
  var BASE="{BASE_URL}";
  var PROBE_SEC=600;
  var _lastData=null,_prevStatus=null;

  function esc(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}}

  /* ── colour maps ── */
  var SC={{"LOW":"#4ade80","WATCH":"#fbbf24","ACTIVE":"#f97316","SEVERE":"#ff5566"}};
  var GC={{"CALM":"#4ade80","WATCH":"#fbbf24","ACTIVE":"#f97316","SPIKE":"#ff5566",
    "SHOCK":"#ff5566","SELL_OFF":"#ff5566","STRESS":"#ff5566","LIQUIDATING":"#ff5566",
    "BREAKDOWN":"#ff5566","DETECTED":"#fbbf24","NONE":"#4ade80",
    "HAWKISH":"#ff5566","DOVISH":"#4ade80","NEUTRAL":"#94a3b8","UNKNOWN":"#94a3b8"}};
  function gc(v){{return GC[String(v||"").toUpperCase()]||"#94a3b8";}}
  function fp(v,dec){{
    if(v===null||v===undefined||v==="")return"–";
    var f=parseFloat(v);if(isNaN(f))return"–";
    return(f>=0?"+":"")+f.toFixed(dec||3)+"%";
  }}
  function badge(label,col){{
    return'<span style="background:'+col+'22;color:'+col+';border-radius:4px;padding:2px 7px;font-size:10px;font-weight:700">'+esc(label)+'</span>';
  }}

  /* ── countdown ── */
  function parseGenAt(s){{
    if(!s)return null;
    var m=s.match(/(\d{{4}})-(\d{{2}})-(\d{{2}}) (\d{{2}}):(\d{{2}})/);
    if(!m)return null;
    return new Date(Date.UTC(+m[1],+m[2]-1,+m[3],+m[4]-8,+m[5]));
  }}
  function tickCountdown(){{
    if(!_lastData)return;
    var el=document.getElementById("boj-countdown");if(!el)return;
    var genAt=parseGenAt(_lastData.generated_at);
    if(!genAt){{el.innerHTML="";return;}}
    var next=new Date(genAt.getTime()+PROBE_SEC*1000);
    var diff=Math.round((next-Date.now())/1000);
    if(diff<=0){{el.innerHTML='<span style="color:#fbbf24">⟳ probe due now…</span>';}}
    else{{
      var mm=Math.floor(diff/60),ss=diff%60;
      el.innerHTML='<span style="color:'+(diff<60?"#f97316":"#555")+'">⟳ next probe '
        +(mm>0?mm+"m ":"")+ss+"s</span>";
    }}
  }}
  setInterval(tickCountdown,1000);

  /* ── status narrative ── */
  var SITUATION={{
    "LOW":   {{"bg":"rgba(74,222,128,.07)","border":"rgba(74,222,128,.2)","icon":"✅",
               "headline":"Yen carry trade is STABLE — no unwind risk detected.",
               "what":"USD/JPY is not moving significantly. No BOJ hawkish signals. All market gates calm. You can monitor without urgent action.",
               "watch":"Watch for: BOJ governor speaking · USD/JPY drops below 158 · VXX/UVXY spike +5% · Nikkei drops >2%"}},
    "WATCH": {{"bg":"rgba(251,191,36,.08)","border":"rgba(251,191,36,.3)","icon":"⚠️",
               "headline":"CAUTION — Early carry unwind signals appearing.",
               "what":"One or more gates are showing stress. The yen may be starting to strengthen. Second tranche adds are now BLOCKED. Stay alert.",
               "watch":"Escalation triggers: USD/JPY breakdown flag · VXX +8% · Japan equity (EWJ) -2% · BOJ hawkish statement"}},
    "ACTIVE":{{"bg":"rgba(249,115,22,.10)","border":"rgba(249,115,22,.4)","icon":"🚨",
               "headline":"CARRY UNWIND ACTIVE — Multiple stress signals confirmed.",
               "what":"Yen is strengthening and markets are under pressure. High-beta positions (ASTS, RKLB, QBTS, LUNR) at risk of liquidation selling. Do NOT add. Review exposure now.",
               "watch":"Escalation to SEVERE: USD/JPY BREAKDOWN + VXX +15% + US equity selloff simultaneously"}},
    "SEVERE":{{"bg":"rgba(255,85,102,.12)","border":"rgba(255,85,102,.5)","icon":"🔴",
               "headline":"SEVERE CARRY UNWIND — Extreme stress across all gates.",
               "what":"This is a crisis-level yen carry event. All adds blocked. High-beta liquidation likely in progress. CIO manual review REQUIRED before any portfolio action.",
               "watch":"De-risk priority: ASTS → RKLB → QBTS → LUNR. Do not panic-sell without CIO review."}}
  }};

  /* ── gate explanations ── */
  var GATE_EXPLAIN={{
    "BOJ Statement": "BOJ governor/MPC issued a statement or press conference. DETECTED = risk elevated.",
    "BOJ Tone":      "Language of BOJ communications. HAWKISH = rate hike signals = yen strengthens = carry trades close.",
    "USD/JPY":       "Yen strength gauge. Falling USD/JPY = yen getting MORE expensive = carry traders forced to buy yen back.",
    "Japan Equity":  "EWJ/DXJ (Japanese stock ETFs). Carry unwind hits Japan equities first — watch for -2% drops.",
    "Volatility":    "VXX/UVXY (fear index). Spike = liquidity drain = leveraged carry trades forced to close suddenly.",
    "US Equity":     "SPY/QQQ/IWM. If US stocks fall WHILE yen strengthens, carry unwind is confirmed cross-market.",
    "Credit":        "HYG/JNK credit spreads widening. Credit stress = deleveraging = carry positions closed to raise cash.",
    "High Beta":     "NVDA/ASTS/QBTS/RKLB/LUNR/IONQ — OUR positions. Selling here = carry unwind hitting your book directly."
  }};

  function render(d){{
    if(!d||!d.status)return;
    _lastData=d;
    var st=d.status||"LOW",sc=parseFloat(d.score||0);
    var sc_col=SC[st]||"#94a3b8";
    var gen=d.generated_at||"";
    var act=d.cio_action||"WAIT";
    var tone=(d.boj_tone_gate||{{}}).tone||"UNKNOWN";
    var summ=SITUATION[st]||SITUATION["LOW"];

    /* border / animation */
    var borderCol=st==="LOW"?"rgba(34,211,238,.2)":summ.border;
    var anim=st==="SEVERE"?"boj-pulse-severe 1.2s infinite":st==="ACTIVE"?"boj-pulse 1.6s infinite":
             st==="WATCH"?"boj-pulse 2s infinite":"none";

    /* ── score bar with threshold markers at 25/50/75 ── */
    var scoreBarHtml=
      '<div style="position:relative;flex:1;margin:0 4px">'
      +'<div style="background:rgba(255,255,255,.06);border-radius:4px;height:10px;overflow:visible;position:relative">'
      +'<div style="height:100%;width:'+Math.min(sc,100)+'%;background:'+sc_col+';border-radius:4px;transition:width .8s ease"></div>'
      /* threshold ticks */
      +'<div style="position:absolute;top:-3px;bottom:-3px;left:25%;width:1px;background:rgba(251,191,36,.4)"></div>'
      +'<div style="position:absolute;top:-3px;bottom:-3px;left:50%;width:1px;background:rgba(249,115,22,.4)"></div>'
      +'<div style="position:absolute;top:-3px;bottom:-3px;left:75%;width:1px;background:rgba(255,85,102,.4)"></div>'
      +'</div>'
      /* threshold labels */
      +'<div style="display:flex;position:relative;font-size:8px;color:#555;margin-top:2px">'
      +'<span style="position:absolute;left:25%;transform:translateX(-50%)">WATCH</span>'
      +'<span style="position:absolute;left:50%;transform:translateX(-50%)">ACTIVE</span>'
      +'<span style="position:absolute;left:75%;transform:translateX(-50%)">SEVERE</span>'
      +'</div></div>';

    /* ── USD/JPY strip ── */
    var usd=d.usd_jpy||{{}};
    var price=usd.price?parseFloat(usd.price).toFixed(3):"–";
    var chg5m=fp(usd.change_5m_pct,3),chg15m=fp(usd.change_15m_pct,3),chg1h=fp(usd.change_1h_pct,3);
    var usdNote=usd.note||"",breakdown=usd.breakdown_flag;
    function cc(v){{
      if(v==="–")return"#555";
      var f=parseFloat(v);
      return f<-0.3?"#f97316":f<-0.1?"#fbbf24":f>0.1?"#4ade80":"#94a3b8";
    }}
    var bdBadge=breakdown
      ?'<div style="margin-left:auto;background:#ff556622;color:#ff5566;border:1px solid #ff556644;'
       +'border-radius:4px;padding:3px 8px;font-size:10px;font-weight:700;animation:boj-pulse-severe 1s infinite">⚠ YEN BREAKDOWN</div>':"";

    var usdStrip=
      '<div style="display:flex;gap:0;padding:10px 14px;background:rgba(34,211,238,.05);'
      +'border:1px solid rgba(34,211,238,.14);border-radius:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap;gap:0">'
      +'<div style="flex:0 0 auto;padding-right:16px;border-right:1px solid rgba(255,255,255,.07);margin-right:16px">'
      +'<div style="font-size:9px;color:#555;letter-spacing:.12em">USD/JPY</div>'
      +'<div style="font-size:20px;font-weight:700;color:#e2e8f0;font-family:JetBrains Mono,monospace;line-height:1.2">'+esc(price)+'</div>'
      +(usdNote?'<div style="font-size:8px;color:#555">~approx</div>':'')
      +'</div>'
      +'<div style="padding-right:16px;border-right:1px solid rgba(255,255,255,.07);margin-right:16px">'
      +'<div style="font-size:9px;color:#555">5 min</div>'
      +'<div style="font-size:14px;font-weight:600;color:'+cc(chg5m)+'">'+esc(chg5m)+'</div>'
      +'<div style="font-size:8px;color:#555">yen direction</div></div>'
      +'<div style="padding-right:16px;border-right:1px solid rgba(255,255,255,.07);margin-right:16px">'
      +'<div style="font-size:9px;color:#555">15 min</div>'
      +'<div style="font-size:14px;font-weight:600;color:'+cc(chg15m)+'">'+esc(chg15m)+'</div>'
      +'<div style="font-size:8px;color:#555">momentum</div></div>'
      +'<div style="padding-right:16px;border-right:1px solid rgba(255,255,255,.07);margin-right:16px">'
      +'<div style="font-size:9px;color:#555">1 hour</div>'
      +'<div style="font-size:14px;font-weight:600;color:'+cc(chg1h)+'">'+esc(chg1h)+'</div>'
      +'<div style="font-size:8px;color:#555">trend</div></div>'
      +'<div>'
      +'<div style="font-size:9px;color:#555">BOJ TONE</div>'
      +'<div style="margin-top:2px">'+badge(tone,gc(tone))+'</div>'
      +'<div style="font-size:8px;color:#555;margin-top:2px">'+
        (tone==="HAWKISH"?"rate hike signal":tone==="DOVISH"?"easing stance":tone==="NEUTRAL"?"neutral":"no BOJ data")
      +'</div></div>'
      +bdBadge
      +'</div>';

    /* ── 8 gate rows with explanations ── */
    var gates=[
      ["BOJ Statement",(d.boj_statement||{{}}).status,  (d.boj_statement||{{}}).score,  15],
      ["BOJ Tone",     tone,                             (d.boj_tone_gate||{{}}).score,  15],
      ["USD/JPY",      (d.usd_jpy_gate||{{}}).status,   (d.usd_jpy_gate||{{}}).score,   20],
      ["Japan Equity", (d.japan_equity_gate||{{}}).status,(d.japan_equity_gate||{{}}).score,10],
      ["Volatility",   (d.volatility_gate||{{}}).status, (d.volatility_gate||{{}}).score, 15],
      ["US Equity",    (d.us_equity_gate||{{}}).status,  (d.us_equity_gate||{{}}).score,  10],
      ["Credit",       (d.credit_gate||{{}}).status,     (d.credit_gate||{{}}).score,     10],
      ["High Beta",    (d.high_beta_gate||{{}}).status,  (d.high_beta_gate||{{}}).score,   5],
    ];
    var gateRows=gates.map(function(g){{
      var nm=g[0],gst=String(g[1]||""),gsc=parseFloat(g[2])||0,wt=g[3];
      var col=gc(gst);var pct=Math.min(gsc,wt)/wt*100;
      var explain=GATE_EXPLAIN[nm]||"";
      var isAlert=gst!=="CALM"&&gst!=="NONE"&&gst!=="UNKNOWN"&&gst!=="DOVISH";
      return'<div style="padding:5px 0;border-bottom:1px solid rgba(255,255,255,.04)">'
        +'<div style="display:flex;align-items:center;gap:8px">'
        +'<div style="width:100px;color:'+(isAlert?col:"#94a3b8")+';font-size:10px;font-weight:'+(isAlert?"700":"400")+';flex-shrink:0">'+esc(nm)+'</div>'
        +'<div style="flex:1;background:rgba(255,255,255,.05);border-radius:3px;height:6px;overflow:hidden">'
        +'<div style="height:100%;width:'+pct+'%;background:'+col+';border-radius:3px;transition:width .8s ease"></div></div>'
        +'<div style="width:24px;text-align:right;color:'+col+';font-size:10px;font-weight:700">'+gsc.toFixed(0)+'<span style="font-size:8px;color:#444">/'+wt+'</span></div>'
        +'<div style="width:82px;text-align:right">'+badge(gst,col)+'</div>'
        +'</div>'
        +'<div style="font-size:9px;color:#444;margin-top:1px;margin-left:108px;line-height:1.3">'+esc(explain)+'</div>'
        +'</div>';
    }}).join("");

    /* ── situation summary box ── */
    var summBox=
      '<div style="background:'+summ.bg+';border:1px solid '+summ.border+';border-radius:8px;'
      +'padding:10px 14px;margin-bottom:10px">'
      +'<div style="font-size:13px;font-weight:700;color:'+sc_col+';margin-bottom:4px">'
      +summ.icon+' '+esc(summ.headline)+'</div>'
      +'<div style="font-size:11px;color:#cbd5e1;line-height:1.5;margin-bottom:6px">'+esc(summ.what)+'</div>'
      +'<div style="font-size:10px;color:#555;border-top:1px solid rgba(255,255,255,.06);padding-top:6px">'
      +'<span style="color:#94a3b8;font-weight:600">WATCH FOR: </span>'+esc(summ.watch)+'</div>'
      +'</div>';

    /* ── alerts ── */
    var alerts=d.alerts||[],alertHtml="";
    if(alerts.length){{
      alertHtml='<div style="margin-top:8px;padding:8px 12px;background:rgba(249,115,22,.10);'
        +'border:1px solid rgba(249,115,22,.3);border-radius:6px">'
        +'<div style="font-size:9px;font-weight:700;color:#f97316;letter-spacing:.1em;margin-bottom:4px">ACTIVE ALERTS</div>'
        +alerts.map(function(a){{return'<div style="font-size:11px;color:#fcd34d;padding:2px 0">⚠ '+esc(a)+'</div>';
        }}).join("")+'</div>';
    }}

    /* ── notes (human summary from engine) ── */
    var notes=d.notes||[],notesHtml="";
    var hs=d.human_summary||"";
    if(hs){{
      notesHtml='<div style="margin-top:6px;padding:4px 2px;font-size:10px;color:#555;font-style:italic">'+esc(hs)+'</div>';
    }}

    /* ── pulse dot ── */
    var dot='<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:'+sc_col+
      ';margin-right:7px;animation:dot-blink 1.4s infinite;vertical-align:middle"></span>';

    var html='<div style="background:rgba(13,16,32,.97);border:1px solid '+borderCol+';'
      +'border-radius:12px;padding:20px 24px;animation:'+anim+'">'

      /* ── header ── */
      +'<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px">'
      +'<div>'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:11px;letter-spacing:.18em;'
      +'text-transform:uppercase;color:#22d3ee;margin-bottom:2px">'+dot+'S5 · BOJ / YEN CARRY EVENT WATCHER</div>'
      +'<div style="font-size:10px;color:#555">Probing every 10 min · JS refreshes every 60s</div>'
      +'</div>'
      +'<div style="text-align:right">'
      +'<div style="font-size:10px;color:#555">'+esc(gen)+'</div>'
      +'<div id="boj-countdown" style="font-size:9px;margin-top:2px"></div>'
      +'</div></div>'

      /* ── score row ── */
      +'<div style="display:flex;align-items:center;gap:14px;margin-bottom:14px">'
      +'<div>'
      +'<div style="font-size:36px;font-weight:800;font-family:JetBrains Mono,monospace;color:'+sc_col+';line-height:1">'
      +sc.toFixed(1)+'</div>'
      +'<div style="font-size:10px;color:#555">/ 100 pts</div>'
      +'</div>'
      +'<div>'+badge(st,sc_col)+'<div style="font-size:9px;color:#555;margin-top:3px;text-align:center">risk level</div></div>'
      +scoreBarHtml
      +'<div style="text-align:right;flex-shrink:0">'
      +'<div style="font-size:9px;color:#555;letter-spacing:.1em">CIO ACTION</div>'
      +'<div style="font-size:15px;font-weight:700;color:#e2e8f0">'+esc(act)+'</div>'
      +'<div style="font-size:9px;color:#555">'
      +(act==="WAIT"?"safe to monitor":act==="HOLD_HEDGE"?"hold, no adds":act==="TAKE_PARTIAL_HEDGE_PROFIT_REVIEW"?"review exposure":"all adds BLOCKED")
      +'</div></div></div>'

      /* ── situation summary ── */
      +summBox

      /* ── USD/JPY strip ── */
      +usdStrip

      /* ── 8 gates ── */
      +'<div style="margin-bottom:8px">'+gateRows+'</div>'

      /* ── alerts ── */
      +alertHtml

      /* ── engine narrative ── */
      +notesHtml

      /* ── governance ── */
      +'<div style="margin-top:12px;padding-top:8px;border-top:1px solid rgba(255,255,255,.04);'
      +'font-size:9px;color:#444;letter-spacing:.07em">'
      +'EXECUTION: CIO_ONLY_MANUAL &nbsp;·&nbsp; ORDER_ROUTING: DISABLED &nbsp;·&nbsp; GOVERNANCE: BOJ_YEN_CARRY v1.0'
      +'</div>'
      +'</div>';

    /* flash on escalation */
    if(_prevStatus&&_prevStatus!==st&&st!=="LOW"){{
      var el2=document.getElementById("boj-live");
      if(el2){{el2.style.transition="background .4s";el2.style.background="rgba(249,115,22,.15)";
        setTimeout(function(){{el2.style.background="";}},3000);}}
    }}
    _prevStatus=st;
    document.getElementById("boj-live").innerHTML=html;
    tickCountdown();
  }}

  function load(){{
    fetch(BASE+"/data/boj_yen_carry_live.json?t="+Date.now())
      .then(function(r){{return r.ok?r.json():Promise.reject(r.status);}})
      .then(render)
      .catch(function(){{
        if(!_lastData){{
          document.getElementById("boj-live").innerHTML=
            '<div style="background:rgba(13,16,32,.60);border:1px solid rgba(34,211,238,.10);'
            +'border-radius:12px;padding:14px 24px;color:#555;font-family:JetBrains Mono,monospace;'
            +'font-size:10px;letter-spacing:.1em">S5 · BOJ / YEN CARRY — daemon not yet running &nbsp;·&nbsp; '
            +'<a href="javascript:location.reload()" style="color:#22d3ee;text-decoration:none">retry</a></div>';
        }}
      }});
  }}
  load();
  setInterval(load, 60000);
}})();
</script>"""

    # ── Catalyst Calendar (only if data present) ───────────────────────────────
    events_html = build_events_from_dataset(ds)
    cal_section = ""
    if events_html:
        cal_section = f"""
<div style="margin-bottom:16px">
  <div style="font-family:JetBrains Mono,monospace;font-size:11px;letter-spacing:.18em;
    text-transform:uppercase;color:#c084fc;margin-bottom:8px;display:flex;
    align-items:center;gap:10px">Catalyst Calendar
    <span style="height:1px;background:rgba(192,132,252,.18);flex:1;display:block"></span>
  </div>
  {events_html}
</div>"""

    # ── System Health (single footer line) ────────────────────────────────────
    total_signals = meta.get("total_signals", "N/A")
    bad_str = f" · Issues: {', '.join(bad_sources)}" if bad_sources else ""
    sys_health = (
        f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#555;'
        f'padding:10px 0 4px;border-top:1px solid rgba(255,255,255,.05);letter-spacing:.06em">'
        f'System Health&nbsp;·&nbsp;{source_coverage_label(active, expected)}&nbsp;·&nbsp;'
        f'Signals {total_signals}&nbsp;·&nbsp;Integrity '
        f'<span style="color:{integrity_col}">{integrity_str}</span>'
        f'{html_escape(bad_str)}'
        f'&nbsp;·&nbsp;<a href="{BASE_URL}/chief-strategist.html" '
        f'style="color:#c084fc;text-decoration:none">Full Strategist Report &rarr;</a>'
        f'</div>'
    )

    nav_html = build_nav("dashboard")
    thesis_widgets_zone = render_widget_zone()

    # ── Live headlines — news_probe_daemon v2.0 pushes headlines_live.json ──────
    # JS reads source_order from the JSON — no hardcoded source list here.
    headlines_js = f"""<div id="hl-live" style="margin-bottom:16px">
  <div style="background:rgba(13,16,32,.60);border:1px solid rgba(192,132,252,.14);
    border-radius:12px;padding:14px 24px;color:#444;font-family:JetBrains Mono,monospace;
    font-size:10px;letter-spacing:.12em">🪷&nbsp;HEADLINES — loading…</div>
</div>
<script>
(function(){{
  var BASE="{BASE_URL}";
  function esc(s){{return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}}
  /* ── Source logo badges — generated from news_probe_sources.json (never hardcoded) ── */
  {_logos_js_var}
  function render(d){{
    var srcs=d.sources||{{}},gen=(d.generated_at||""),order=(d.source_order||Object.keys(srcs)),rows="";
    var freshMin=d.window_min||d.freshness_window_minutes||60;
    var freshLabel=freshMin>=60?(freshMin/60|0)+"h":freshMin+"min";
    order.forEach(function(sid){{
      var s=srcs[sid]||{{label:sid,items:[]}};
      var items=s.items||[],content="";
      if(!items.length){{
        var srcWin=s.window_min||freshMin;
        var srcLabel=srcWin>=60?(srcWin/60|0)+"h":srcWin+"min";
        content='<div style="color:#444;font-size:11px;padding:4px 0;font-style:italic">No fresh news in last '+srcLabel+'</div>';
      }}else{{
        items.forEach(function(it){{
          content+='<div style="display:flex;gap:14px;align-items:baseline;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.04)">'
            +'<span style="color:#555;font-size:10px;white-space:nowrap;font-family:JetBrains Mono,monospace;flex-shrink:0">'+esc(it.ts||"")+'</span>'
            +(it.url?'<a href="'+esc(it.url)+'" target="_blank" rel="noopener" style="color:#c9d1d9;font-size:13px;line-height:1.55;text-decoration:none"><span style="border-bottom:1px solid rgba(201,209,217,.25)">'+esc(it.text||"")+'</span></a>':'<span style="color:#c9d1d9;font-size:13px;line-height:1.55">'+esc(it.text||"")+'</span>')
            +'</div>';
        }});
      }}
      var logoBadge=LOGOS[sid]||'';
      var labelInner=logoBadge
        +'<span style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;'
        +'text-transform:uppercase;color:#c084fc;font-weight:600;margin-left:'+(logoBadge?'9px':'0')+'">'+esc(s.label||sid)+'</span>';
      rows+='<div style="margin-bottom:16px">'
        +'<div style="display:flex;align-items:center;margin-bottom:8px;padding-bottom:6px;'
        +'border-bottom:1px solid rgba(192,132,252,.30)">'
        +labelInner+'</div>'
        +content+'</div>';
    }});
    document.getElementById("hl-live").innerHTML=
      '<div style="background:rgba(13,16,32,.97);border:1px solid rgba(192,132,252,.22);'
      +'border-radius:12px;padding:18px 24px;margin-bottom:16px">'
      +'<div style="font-family:JetBrains Mono,monospace;font-size:11px;letter-spacing:.22em;'
      +'text-transform:uppercase;color:#c084fc;margin-bottom:16px;display:flex;'
      +'align-items:center;gap:12px;font-weight:700">🪷&nbsp;HEADLINES'
      +'<span style="height:1px;background:rgba(192,132,252,.22);flex:1;display:block"></span>'
      +'<span style="font-size:9px;color:#555;font-weight:400;letter-spacing:.08em">'+freshLabel+' window · '+esc(gen)+'</span>'
      +'</div>'+rows+'</div>';
  }}
  function load(){{
    fetch(BASE+"/data/headlines_live.json?t="+Date.now())
      .then(function(r){{return r.json();}})
      .then(render)
      .catch(function(){{}});
  }}
  load();
  setInterval(load,600000);
}})();
</script>"""

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="refresh" content="10800">
<title>BlueLotus Command Center v1.7</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600;700&family=Cormorant+Garamond:wght@500;700&family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
<style>
:root{{--bg:#060712;--line:rgba(192,132,252,.18);--text:#e6edf3;--muted:#8b93a7;--lotus:#c084fc}}
*{{box-sizing:border-box}}
body{{margin:0;background:radial-gradient(circle at top left,rgba(192,132,252,.12),transparent 28%),#060712;color:var(--text);font-family:Outfit,sans-serif;line-height:1.55}}
.shell{{max-width:1480px;margin:0 auto;padding:22px 28px}}
@media(max-width:1100px){{
  [style*="grid-template-columns:1fr 1.5fr 1fr"]{{grid-template-columns:1fr!important}}
  [style*="grid-template-columns:repeat(4,1fr)"]{{grid-template-columns:1fr 1fr!important}}
  [style*="grid-template-columns:repeat(5,1fr)"]{{grid-template-columns:repeat(3,1fr)!important}}
  [style*="grid-template-columns:repeat(4,1fr)"]{{grid-template-columns:1fr 1fr!important}}
}}
@media(max-width:700px){{
  [style*="grid-template-columns:repeat(5,1fr)"]{{grid-template-columns:1fr 1fr!important}}
  [style*="grid-template-columns:repeat(4,1fr)"]{{grid-template-columns:1fr!important}}
  .shell{{padding:14px}}
}}
</style>
{nav_html}
</head>
<body>
<main class="shell">
{headlines_js}
{fund_live_js}
{sit_board}
{thesis_section}
{warsh_section}
{boj_section}
{cal_section}
{thesis_widgets_zone}
{sys_health}
</main>
</body></html>"""


# ── Chief Strategist HTML — 8-Lens Cards ──────────────────────────────────────
def build_chief_strategist_html(report: str, ds: Dict[str, Any],
                                intel_notes: Optional[List[Dict[str, Any]]] = None,
                                v3_data: Optional[Dict[str, Any]] = None) -> str:
    regime      = ds.get("regime", {}) if isinstance(ds.get("regime"), dict) else {}
    portfolio   = ds.get("portfolio", {}) if isinstance(ds.get("portfolio"), dict) else {}
    fear        = ds.get("fear_greed", {}) if isinstance(ds.get("fear_greed"), dict) else {}
    cm_conf     = ds.get("cross_market_confirmation", {}) if isinstance(ds.get("cross_market_confirmation"), dict) else {}
    risk_model  = ds.get("risk_model", {}) if isinstance(ds.get("risk_model"), dict) else {}
    thesis_lc   = ds.get("thesis_lifecycle", {}) if isinstance(ds.get("thesis_lifecycle"), dict) else {}
    event_corr  = ds.get("event_correlations", []) if isinstance(ds.get("event_correlations"), list) else []
    forecasting = ds.get("research_forecasting", {}) if isinstance(ds.get("research_forecasting"), dict) else {}
    iq          = ds.get("institutional_quant", {}) if isinstance(ds.get("institutional_quant"), dict) else {}
    monitoring  = ds.get("monitoring", {}) if isinstance(ds.get("monitoring"), dict) else {}
    cio_dec     = ds.get("cio_decisions", {}) if isinstance(ds.get("cio_decisions"), dict) else {}
    positions   = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
    moomoo      = ds.get("moomoo_intel", []) if isinstance(ds.get("moomoo_intel"), list) else []
    moomoo_filt = filter_moomoo_for_portfolio(moomoo, positions)
    active_src, expected_src, bad_sources = source_health_summary(ds)
    if intel_notes is None:
        intel_notes = []

    # ── Regime
    regime_short = str(regime.get("regime_short") or regime.get("regime") or "UNKNOWN")
    regime_score = regime.get("score", "N/A")
    cio_action   = cio_action_from_regime(regime, portfolio)
    vix          = regime.get("vix_level", "N/A")
    fg_score     = fear.get("score", regime.get("fg_score", "N/A"))
    fg_label     = str(fear.get("label", fear.get("rating", "UNKNOWN"))).upper()
    warnings     = regime.get("warnings", []) if isinstance(regime.get("warnings"), list) else []
    factors      = regime.get("factors", {}) if isinstance(regime.get("factors"), dict) else {}
    factors_str  = "  ".join(
        f"{k}:{int(v):+d}" for k, v in factors.items() if isinstance(v, (int, float))
    ) if factors else "N/A"
    primary_warn = clean_text(warnings[0], 100) if warnings else "No primary warning flagged"
    rc = regime_color(regime_short)

    # ── Cross-market
    cm_filled    = cm_conf.get("filled_count", 0)
    cm_total     = cm_conf.get("total_count", cm_conf.get("universe_count", 57))
    cm_scores    = cm_conf.get("derived_scores", {}) if isinstance(cm_conf.get("derived_scores"), dict) else {}
    cm_flags     = cm_conf.get("interpretation_flags", {}) if isinstance(cm_conf.get("interpretation_flags"), dict) else {}
    active_flags = [k for k, v in cm_flags.items() if v is True]
    total_flags  = len(cm_flags)
    flag_count   = len(active_flags)
    risk_app     = cm_scores.get("risk_appetite", cm_scores.get("risk_appetite_score", "N/A"))
    risk_app_str = f"{risk_app:.2f}" if isinstance(risk_app, float) else str(risk_app)
    flags_str    = ", ".join(active_flags[:8]) + ("…" if flag_count > 8 else "") if active_flags else "None"

    # ── Risk model
    rm_hvar     = risk_model.get("historical_var", {})
    rm_var95    = rm_hvar.get("confidence_95", {}) if isinstance(rm_hvar, dict) else {}
    var_dollars = safe_float(rm_var95.get("daily_dollars") if isinstance(rm_var95, dict) else 0)
    var_pct     = safe_float(rm_var95.get("daily_pct") if isinstance(rm_var95, dict) else 0)
    beta_spy    = safe_float(risk_model.get("beta_to_spy"))
    vol_ann     = safe_float(risk_model.get("volatility_annualized"))
    return_obs  = risk_model.get("return_observations", "N/A")
    breaches    = risk_model.get("constraint_breaches", []) if isinstance(risk_model.get("constraint_breaches"), list) else []
    breach_count = len(breaches)
    breach_descs: List[str] = []
    for br in breaches[:3]:
        if isinstance(br, dict):
            desc = br.get("constraint") or br.get("description") or br.get("type") or br.get("breach") or str(br)
            breach_descs.append(clean_text(desc, 55))
    var_pct_str = f"{var_pct*100:.2f}%" if var_pct > 0 else "N/A"

    # ── Portfolio
    market_val    = safe_float(portfolio.get("market_val") or portfolio.get("total_value"))
    cash          = safe_float(portfolio.get("cash"))
    total_assets  = safe_float(portfolio.get("total_assets"))
    total_pnl     = safe_float(portfolio.get("total_pnl"))
    total_pnl_pct = safe_float(portfolio.get("total_pnl_pct"))
    cash_pct      = (cash / total_assets * 100.0) if total_assets else 0.0
    pos_parts: List[str] = []
    worst_t, worst_p = "", 0.0
    for t, p in positions.items():
        if not isinstance(p, dict):
            continue
        pp = safe_float(p.get("unrealized_p"))
        mv = safe_float(p.get("mkt_val") or p.get("market_value") or p.get("market_val") or 0.0)
        wt = (mv / market_val * 100.0) if market_val else 0.0
        sign = "+" if pp >= 0 else ""
        pos_parts.append(f"{t} {sign}{pp:.1f}% ({wt:.0f}%wt)")
        if pp < worst_p:
            worst_p, worst_t = pp, t
    pos_str = "  ·  ".join(pos_parts) if pos_parts else "No active positions"

    # ── Thesis
    theses    = thesis_lc.get("theses", []) if isinstance(thesis_lc.get("theses"), list) else []
    confirmed = [t for t in theses if str(t.get("status", "")).upper() == "CONFIRMED"]
    active_th = [t for t in theses if str(t.get("status", "")).upper() == "ACTIVE"]
    thesis_parts: List[str] = []
    for th in theses[:4]:
        status = str(th.get("status", "?")).upper()
        conf   = safe_float(th.get("confidence", th.get("confidence_pct", 0)))
        evid   = th.get("evidence", [])
        et = ""
        if isinstance(evid, list) and evid:
            fe = evid[0]
            et = clean_text(fe.get("evidence", "") if isinstance(fe, dict) else str(fe), 50)
        sc = "#4ade80" if status == "CONFIRMED" else ("#fbbf24" if status == "ACTIVE" else "#8b93a7")
        thesis_parts.append(
            f'<span style="color:{sc}">[{status}]</span> {html_escape(et)} '
            f'<span style="color:#8b93a7">({conf*100:.0f}%)</span>'
        )

    # ── Intelligence tape
    geo      = extract_geo_alert(event_corr)
    ro_count = sum(1 for ev in event_corr if "RISK-OFF" in str(ev.get("direction", "")).upper())
    total_ev = len(event_corr)

    # ── Forecast
    snap_id      = str(forecasting.get("snapshot_id", "N/A"))
    brier_status = str(forecasting.get("brier_status", "N/A")).upper()
    fc_count     = forecasting.get("forecast_count", "N/A")
    fc_tickers   = forecasting.get("ticker_count", "N/A")
    maturity     = str(forecasting.get("first_maturity_date", forecasting.get("maturity_date", "2026-06-09")))

    # ── Ops
    iq_score    = safe_float(iq.get("readiness_score", iq.get("iq_readiness_score", 0)))
    alert_count = int(safe_float(monitoring.get("alert_count", 0)))
    severity    = monitoring.get("severity_counts", {}) if isinstance(monitoring.get("severity_counts"), dict) else {}
    warn_alerts = int(safe_float(severity.get("WARNING", 0)))
    info_alerts = int(safe_float(severity.get("INFO", 0)))
    pending_rev = int(safe_float(cio_dec.get("pending_review_count", 0)))
    decisions   = cio_dec.get("decisions", []) if isinstance(cio_dec.get("decisions"), list) else []
    hi_priority = [d for d in decisions if str(d.get("priority", "")).upper() in ("HIGH", "CRITICAL", "URGENT")]

    nav_html = build_nav("cs-report")
    generated = str((ds.get("meta") or {}).get("generated_at") or now_sgt())
    publish_time = now_sgt()
    report_time = display_sgt_time(generated)
    council_time = ""
    latest_agent_time = ""
    if v3_data:
        briefing = v3_data.get("briefing", {}) if isinstance(v3_data.get("briefing"), dict) else {}
        council_time = display_sgt_time(briefing.get("created_at_sgt")) or display_sgt_time(v3_data.get("cycle_id"))
        latest_agent_time = display_sgt_time(v3_data.get("latest_cycle_id"))
    timing_bits = [f"Published {publish_time}"]
    if report_time:
        timing_bits.append(f"Report data {report_time}")
    if council_time:
        timing_bits.append(f"Council snapshot {council_time}")
    if v3_data and v3_data.get("fallback_from_cycle_id") and latest_agent_time:
        timing_bits.append(f"Latest agent attempt {latest_agent_time} unavailable")
    timing_line = " · ".join(timing_bits)

    # ── Helper: single lens card ──────────────────────────────────────────────────
    def lens_card(num: str, name: str, rgb: str,
                  state: str, mid_label: str, mid_val: str, impl: str) -> str:
        return (
            f'<div style="background:rgba(13,16,32,.94);border:1px solid rgba({rgb},.22);'
            f'border-radius:14px;padding:18px 20px;break-inside:avoid">'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.16em;'
            f'text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:8px">'
            f'<span style="color:rgba({rgb},.55)">LENS {num}</span>'
            f'<span style="color:rgba(255,255,255,.25)">—</span>'
            f'<span style="color:rgba({rgb},1)">{html_escape(name)}</span>'
            f'<span style="height:1px;background:rgba({rgb},.14);flex:1;display:block"></span>'
            f'</div>'
            f'<div style="font-size:12px;font-weight:600;color:#e6edf3;margin-bottom:6px;line-height:1.45">'
            f'{html_escape(state)}'
            f'</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#8b93a7;'
            f'margin-bottom:8px;line-height:1.55">'
            f'<span style="color:rgba({rgb},.65);text-transform:uppercase;font-size:9px;'
            f'letter-spacing:.1em">{html_escape(mid_label)}: </span>'
            f'{html_escape(mid_val)}'
            f'</div>'
            f'<div style="font-size:11px;color:rgba({rgb},0.85);font-style:italic;line-height:1.45;'
            f'border-top:1px solid rgba({rgb},.12);padding-top:7px">'
            f'&#9654; {html_escape(impl)}'
            f'</div>'
            f'</div>'
        )

    def lens_card_html(num: str, name: str, rgb: str,
                       state: str, mid_label: str, mid_html: str, impl: str) -> str:
        """Variant that accepts pre-escaped HTML for mid_val."""
        return (
            f'<div style="background:rgba(13,16,32,.94);border:1px solid rgba({rgb},.22);'
            f'border-radius:14px;padding:18px 20px;break-inside:avoid">'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.16em;'
            f'text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:8px">'
            f'<span style="color:rgba({rgb},.55)">LENS {num}</span>'
            f'<span style="color:rgba(255,255,255,.25)">—</span>'
            f'<span style="color:rgba({rgb},1)">{html_escape(name)}</span>'
            f'<span style="height:1px;background:rgba({rgb},.14);flex:1;display:block"></span>'
            f'</div>'
            f'<div style="font-size:12px;font-weight:600;color:#e6edf3;margin-bottom:6px;line-height:1.45">'
            f'{html_escape(state)}'
            f'</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:#8b93a7;'
            f'margin-bottom:8px;line-height:1.55">'
            f'<span style="color:rgba({rgb},.65);text-transform:uppercase;font-size:9px;'
            f'letter-spacing:.1em">{html_escape(mid_label)}: </span>'
            f'{mid_html}'
            f'</div>'
            f'<div style="font-size:11px;color:rgba({rgb},0.85);font-style:italic;line-height:1.45;'
            f'border-top:1px solid rgba({rgb},.12);padding-top:7px">'
            f'&#9654; {html_escape(impl)}'
            f'</div>'
            f'</div>'
        )

    # ── Build lens card data ──────────────────────────────────────────────────────
    # L1 Regime
    l1_state = f"{regime_short} (score {regime_score}) · CIO: {cio_action}"
    l1_read  = f"VIX {vix} · F&G {fg_score}/100 {fg_label} · Factors [{factors_str}]"
    l1_impl  = primary_warn
    l1 = lens_card("1", "REGIME", "251,191,36",    l1_state, "Readings", l1_read, l1_impl)

    # L2 Cross-market
    flag_impl = (f"Strong divergence — {flag_count}/{total_flags} flags" if flag_count >= 10
                 else f"Moderate stress — {flag_count}/{total_flags} flags" if flag_count >= 6
                 else f"Low stress — {flag_count}/{total_flags} flags")
    l2_state = f"{flag_count}/{total_flags} flags ACTIVE · Risk appetite {risk_app_str} · Coverage {cm_filled}/{cm_total}"
    l2 = lens_card("2", "CROSS-MARKET", "96,165,250",    l2_state, "Active flags", flags_str, flag_impl)

    # L3 Risk model
    breach_html = ("  |  ".join(html_escape(b) for b in breach_descs)
                   if breach_descs else '<span style="color:#4ade80">No constraint breaches</span>')
    l3_state = f"VaR95 ${var_dollars:,.0f} ({var_pct_str}) · Beta SPY {beta_spy:.2f} · {breach_count} breach{'es' if breach_count != 1 else ''}"
    l3_impl  = f"Portfolio carries {beta_spy:.1f}x SPY sensitivity · annualised vol {vol_ann*100:.1f}% · {return_obs} obs"
    l3 = lens_card_html("3", "RISK MODEL", "248,113,113",  l3_state, "Breaches", breach_html, l3_impl)

    # L4 Portfolio
    pnl_col = "#4ade80" if total_pnl >= 0 else "#ff5566"
    l4_state = f"{money(market_val)} equity · {money(cash)} cash ({cash_pct:.0f}%) · P/L {money(total_pnl)} ({pct_short(total_pnl_pct)})"
    if worst_t:
        th_sl    = TICKER_THESIS.get(worst_t, "WATCH")
        l4_impl  = f"{worst_t} leading losses ({pct_short(worst_p)}) — {th_sl} sleeve under pressure"
    else:
        l4_impl  = "No dominant loss position — review concentration vs. cash buffer"
    l4 = lens_card("4", "PORTFOLIO", "192,132,252",   l4_state, "Positions", pos_str[:160] + ("…" if len(pos_str) > 160 else ""), l4_impl)

    # L5 Thesis lifecycle
    th_inner = "  ".join(thesis_parts) if thesis_parts else "No thesis data"
    th_state = f"{len(theses)} theses · {len(confirmed)} CONFIRMED · {len(active_th)} ACTIVE"
    if len(confirmed) >= 4:
        th_impl = f"{len(confirmed)} theses CONFIRMED — structural positions aligned with regime"
    elif len(confirmed) >= 2:
        th_impl = f"{len(confirmed)} confirmed, {len(active_th)} ACTIVE — partial validation; maintain sizing"
    else:
        th_impl = "Thesis validation incomplete — high-conviction positions unconfirmed"
    l5 = lens_card_html("5", "THESIS LIFECYCLE", "74,222,128",  th_state, "Theses", th_inner, th_impl)

    # L6 Intelligence tape
    geo_pfx  = (clean_text(geo, 75) + " · ") if geo else ""
    l6_state = f"{geo_pfx}{ro_count}/{total_ev} baskets RISK-OFF"
    top3_ev  = []
    for ev in event_corr[:3]:
        dirn = str(ev.get("direction", "WATCH")).upper()
        dc   = "#ff5566" if "OFF" in dirn else ("#4ade80" if "ON" in dirn else "#fbbf24")
        move = safe_float(ev.get("basket_move", 0))
        conf = safe_float(ev.get("confidence", 0))
        top3_ev.append(
            f'<span style="color:{dc}">{html_escape(ev.get("theme","?"))}</span>'
            f'<span style="color:#8b93a7"> {dirn} {conf:.0f}% Basket {pct_short(move)}</span>'
        )
    ev_html = "  ·  ".join(top3_ev) if top3_ev else "No event data"
    if total_ev > 0 and ro_count >= int(total_ev * 0.6):
        l6_impl = f"Broad risk-off — {ro_count}/{total_ev} event baskets aligned bearish"
    elif ro_count > 0:
        l6_impl = f"Mixed — {ro_count}/{total_ev} baskets risk-off; selective caution"
    else:
        l6_impl = "No event-driven risk-off signal — monitor for regime shift"
    l6 = lens_card_html("6", "INTELLIGENCE TAPE", "251,146,60",  l6_state, "Top events", ev_html, l6_impl)

    # L7 Superforecast / Brier
    bs_col   = "#fbbf24" if brier_status == "COLLECTING" else ("#4ade80" if brier_status == "SCORING" else "#8b93a7")
    l7_state = f"{fc_tickers} tickers · {fc_count} forecasts · Status: {brier_status}"
    l7_key   = f"Snapshot {snap_id} · Maturity {maturity}"
    l7_impl  = "Accountability layer COLLECTING. No skill claimed until resolution window opens."
    l7_key_html = f'{html_escape(l7_key)} <span style="color:{bs_col}">·  Doctrine: no skill claimed until resolved</span>'
    l7 = lens_card_html("7", "SUPERFORECAST / BRIER", "96,165,250",  l7_state, "Forecast", l7_key_html, l7_impl)

    # L8 Operations
    iq_col = "#4ade80" if iq_score >= 90 else ("#fbbf24" if iq_score >= 75 else "#ff5566")
    l8_state = f"IQ Score {iq_score:.1f}/100 · {source_coverage_label(active_src, expected_src)} · Alerts {alert_count} ({warn_alerts}W/{info_alerts}I)"
    l8_pend  = f"{pending_rev} CIO reviews pending · Execution: CIO_ONLY_MANUAL · Hi-priority: {len(hi_priority)}"
    if bad_sources:
        l8_impl = f"Source degradation: {', '.join(bad_sources[:3])} — verify data integrity"
    elif alert_count > 15:
        l8_impl = f"{alert_count} alerts ({warn_alerts} WARNING) — review monitoring queue"
    elif iq_score >= 90:
        l8_impl = f"IQ {iq_score:.1f}/100 — institutional-grade readiness · all systems nominal"
    else:
        l8_impl = f"IQ {iq_score:.1f}/100 — below target threshold · review process gaps"
    l8 = lens_card("8", "OPERATIONS", "45,212,191",   l8_state, "Pending", l8_pend, l8_impl)

    # ── Strategist Brief card ─────────────────────────────────────────────────────
    brief_lines = []
    brief_lines.append(f"Market is in <b>{html_escape(regime_short)}</b> (score {regime_score}) — VIX {vix}, F&G {fg_score}/100 {fg_label}.")
    if flag_count >= 8:
        brief_lines.append(f"Cross-market confirms stress: {flag_count}/{total_flags} flags active, risk appetite {risk_app_str}.")
    else:
        brief_lines.append(f"Cross-market neutral-to-cautious: {flag_count}/{total_flags} flags active, risk appetite {risk_app_str}.")
    brief_lines.append(f"Portfolio {html_escape(money(market_val))} / {cash_pct:.0f}% cash — VaR95 ${var_dollars:,.0f} at {beta_spy:.1f}x beta.")
    if len(confirmed) >= 3:
        brief_lines.append(f"{len(confirmed)}/{len(theses)} theses CONFIRMED — structural conviction intact, aligned with regime.")
    else:
        brief_lines.append(f"{len(confirmed)}/{len(theses)} theses confirmed — validation ongoing, maintain sizing discipline.")
    brief_lines.append(f"IQ {iq_score:.1f}/100, {alert_count} alerts, {pending_rev} decisions pending — system {'nominal' if not bad_sources else 'degraded'}.")
    brief_html = "".join(
        f'<div style="padding:6px 0;border-bottom:1px solid rgba(192,132,252,.08);'
        f'font-size:13px;color:#e6edf3;line-height:1.5">{bl}</div>'
        for bl in brief_lines
    )
    brief_action_col = rc
    strategist_brief = (
        f'<div style="background:rgba(13,16,32,.96);border:1px solid rgba(192,132,252,.35);'
        f'border-radius:18px;padding:28px;margin-bottom:16px">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;'
        f'text-transform:uppercase;color:#c084fc;margin-bottom:16px;display:flex;align-items:center;gap:10px">'
        f'Strategist Brief'
        f'<span style="height:1px;background:rgba(192,132,252,.2);flex:1;display:block"></span>'
        f'</div>'
        f'{brief_html}'
        f'<div style="margin-top:14px;padding:12px 16px;background:rgba({hex_to_rgb_css(brief_action_col)},.08);'
        f'border-left:3px solid {brief_action_col};border-radius:0 8px 8px 0">'
        f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.14em;'
        f'text-transform:uppercase;color:{brief_action_col}">CIO ACTION: </span>'
        f'<span style="font-size:13px;font-weight:600;color:#e6edf3">{html_escape(cio_action)}</span>'
        f'<div style="font-size:11px;color:#8b93a7;margin-top:4px">Preserve cash buffer — no new entries without live price confirmation. '
        f'Review {pending_rev} pending CIO decisions before next cycle.</div>'
        f'</div>'
        f'</div>'
    )

    # ── Event correlation section (keep for intelligence context)
    ev_rows = ""
    for ev in event_corr[:6]:
        move  = safe_float(ev.get("basket_move"))
        conf  = safe_float(ev.get("confidence"))
        dirn  = str(ev.get("direction", "WATCH")).upper()
        dirn_col = "#ff5566" if "OFF" in dirn else ("#4ade80" if "ON" in dirn else "#fbbf24")
        ev_rows += (
            f'<div style="padding:10px 0;border-bottom:1px solid rgba(255,255,255,.04)">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<b style="color:#fff;font-size:13px">{html_escape(ev.get("theme","EVENT"))}</b>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:10px;color:{dirn_col}">'
            f'{html_escape(dirn)} · Conf {conf:.0f}% · Basket '
            f'<span style="color:{pct_color(move)}">{pct_short(move)}</span></span>'
            f'</div>'
            f'<p style="margin:4px 0 0;color:#bfc8d7;font-size:12px;line-height:1.5">'
            f'{html_escape(clean_text(ev.get("why"), 200))}</p>'
            f'</div>'
        )
    if not ev_rows:
        ev_rows = '<p style="color:#8b93a7">No event correlations available.</p>'

    # ── Moomoo intel
    mm_rows = ""
    for item in moomoo_filt[:8]:
        text = (item.get("summary") or item.get("raw_text") or item.get("title") or ""
                if isinstance(item, dict) else str(item))
        mm_rows += (
            f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04);'
            f'font-size:12px;color:#ccd5e3;line-height:1.5">'
            f'{html_escape(clean_text(text, 200))}</div>'
        )
    if not mm_rows:
        mm_rows = '<p style="color:#8b93a7">No Moomoo intelligence available.</p>'

    # ── Raw report
    report_html = html_escape(report).replace("\n", "<br>")

    # ── CIO Intelligence Notes card ───────────────────────────────────────────────
    PRIORITY_COLOR = {"HIGH": "248,113,113", "MEDIUM": "251,191,36", "LOW": "148,163,184"}
    CAT_ICON = {
        "CAUSAL_CHAIN_CORRECTION": "⚡",
        "THESIS_INTELLIGENCE":     "🧠",
        "SILVER_THESIS":           "🥈",
        "CATALYST_WATCH":          "📅",
        "MACRO_OVERRIDE_WATCH":    "🚨",
    }
    intel_rows_html = ""
    for note in (intel_notes or []):
        nid      = note.get("id", "")
        ndate    = note.get("date", "")
        priority = str(note.get("priority", "MEDIUM")).upper()
        cat      = str(note.get("category", "")).upper()
        title    = note.get("title", "")
        body     = note.get("body", "")
        affects  = ", ".join(note.get("affects", []))
        status   = str(note.get("status", "ACTIVE")).upper()
        pc       = PRIORITY_COLOR.get(priority, "148,163,184")
        icon     = CAT_ICON.get(cat, "📌")
        status_col = "#4ade80" if status == "MONITORING" else f"rgb({pc})"
        intel_rows_html += (
            f'<div style="padding:12px 0;border-bottom:1px solid rgba(255,255,255,.05)">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin-bottom:6px">'
            f'<div style="display:flex;align-items:center;gap:8px;flex:1">'
            f'<span style="font-size:14px">{icon}</span>'
            f'<b style="color:#e6edf3;font-size:13px;line-height:1.4">{html_escape(title)}</b>'
            f'</div>'
            f'<div style="display:flex;gap:6px;flex-shrink:0;align-items:center">'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;padding:2px 7px;'
            f'border-radius:4px;background:rgba({pc},.15);color:rgb({pc})">{priority}</span>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:#8b93a7">{nid} · {ndate}</span>'
            f'</div>'
            f'</div>'
            f'<p style="margin:0 0 6px 22px;color:#bfc8d7;font-size:12px;line-height:1.6">'
            f'{html_escape(clean_text(body, 400))}</p>'
            f'<div style="margin-left:22px;font-family:JetBrains Mono,monospace;font-size:10px;color:#8b93a7">'
            f'Affects: <span style="color:#c084fc">{html_escape(affects)}</span>'
            f'&nbsp;&nbsp;·&nbsp;&nbsp;Status: <span style="color:{status_col}">{status}</span>'
            f'</div>'
            f'</div>'
        )
    if not intel_rows_html:
        intel_rows_html = '<p style="color:#8b93a7;font-size:12px">No active intelligence notes.</p>'

    def sec(title: str, content: str, title_color: str = "#c084fc",
            raw_title: bool = False) -> str:
        title_html = title if raw_title else html_escape(title)
        return (
            f'<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);'
            f'border-radius:18px;padding:24px;margin-bottom:16px">'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;'
            f'text-transform:uppercase;color:{title_color};margin-bottom:14px;display:flex;'
            f'align-items:center;gap:10px">{title_html}'
            f'<span style="height:1px;background:rgba(192,132,252,.15);flex:1;display:block"></span>'
            f'</div>'
            f'{content}'
            f'</div>'
        )

    v3_council_section = build_v3_agent_council_section(v3_data or {})
    v3_synthesis       = build_v3_synthesis_section(v3_data or {})

    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chief Strategist · V3 Agent Council | BlueLotus</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;600&family=Cormorant+Garamond:wght@500;700&family=Outfit:wght@300;400;600&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#060712;color:#e6edf3;font-family:Outfit,sans-serif;line-height:1.55}}
.shell{{max-width:1100px;margin:0 auto;padding:36px 24px}}
.lens-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:12px;margin-bottom:16px}}
@media(max-width:900px){{.lens-grid{{grid-template-columns:1fr}}}}
@media(max-width:900px) .v3-grid{{grid-template-columns:repeat(2,1fr)!important}}
@media(max-width:600px) .v3-grid{{grid-template-columns:1fr!important}}
</style>
{nav_html}
</head>
<body>
<main class="shell">
  <div style="font-family:Cormorant Garamond,serif;font-size:52px;color:#c084fc;line-height:1;margin:0 0 6px">
    Chief Strategist
  </div>
  <div style="font-family:Cormorant Garamond,serif;font-size:52px;color:#e6edf3;line-height:1;margin:0 0 12px">
    Report · V3 Council
  </div>
  <div style="font-family:JetBrains Mono,monospace;color:#8b93a7;font-size:11px;letter-spacing:.14em;
    text-transform:uppercase;margin-bottom:28px">
    Qwen3:4B Agentic AI · 9 Agents · {html_escape(timing_line)}
  </div>

  <!-- V3 Agent Council (top) -->
  {v3_council_section}

  <!-- V3 Chief Strategist Synthesis -->
  {v3_synthesis}

</main>
</body></html>"""


# ── Local report save ──────────────────────────────────────────────────────────
def save_local_report(report: str) -> None:
    path = Path(REPORT_OUTPUT_PATH)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        print(f"  Report saved: {path}")
    except Exception as exc:
        fallback = Path("/mnt/data/chief_strategist_v17.txt")
        try:
            fallback.write_text(report, encoding="utf-8")
            print(f"  Report saved fallback: {fallback} ({exc})")
        except Exception:
            print(f"  Report save failed: {exc}")


# ── Portfolio live JSON (pushed every pipeline cycle) ─────────────────────────
def build_portfolio_live(ds: Dict[str, Any]) -> str:
    """Serialise the Fund Status data to JSON for the live dashboard JS fetch."""
    meta      = ds.get("meta", {}) if isinstance(ds.get("meta"), dict) else {}
    regime    = ds.get("regime", {}) if isinstance(ds.get("regime"), dict) else {}
    portfolio = ds.get("portfolio", {}) if isinstance(ds.get("portfolio"), dict) else {}
    fear      = ds.get("fear_greed", {}) if isinstance(ds.get("fear_greed"), dict) else {}

    cash        = safe_float(portfolio.get("cash"))
    total_assets = safe_float(portfolio.get("total_assets"))
    market_val  = safe_float(portfolio.get("market_val") or portfolio.get("total_value"))
    cash_pct    = (cash / total_assets * 100.0) if total_assets else 0.0
    total_pnl   = safe_float(portfolio.get("total_pnl"))
    total_pnl_pct = safe_float(portfolio.get("total_pnl_pct"))
    cio_action  = cio_action_from_regime(regime, portfolio)

    regime_short = str(regime.get("regime_short") or regime.get("regime") or "UNKNOWN")
    rc           = regime_color(regime_short)
    fg_score     = fear.get("score", regime.get("fg_score", "N/A"))
    fg_label     = str(fear.get("label", fear.get("rating", "UNKNOWN"))).upper()
    vix_raw      = regime.get("vix_level", ds.get("live_prices", {}).get("vix", {}).get("price"))
    vix_str      = str(vix_raw) if vix_raw is not None else "N/A"
    score_str    = str(regime.get("score", "N/A"))
    integrity_ok = not (portfolio.get("integrity_flag") or portfolio.get("stale"))

    pnl_color  = pct_color(total_pnl)
    cash_color = "#4ade80" if cash_pct >= 30 else ("#fbbf24" if cash_pct >= 15 else "#ff5566")
    fg_color   = "#4ade80" if safe_float(fg_score) >= 55 else ("#ff5566" if safe_float(fg_score) <= 30 else "#fbbf24")

    raw_positions = portfolio.get("positions") or {}
    if isinstance(raw_positions, dict):
        position_items = raw_positions.items()
    elif isinstance(raw_positions, list):
        position_items = [
            (str(p.get("ticker") or p.get("symbol") or "").upper(), p)
            for p in raw_positions
            if isinstance(p, dict)
        ]
    else:
        position_items = []

    positions: List[Dict[str, Any]] = []
    for ticker, pos in position_items:
        if not ticker or not isinstance(pos, dict):
            continue
        avg_raw = pos.get("avg_price")
        if avg_raw is None:
            avg_raw = pos.get("avg_cost")
        if avg_raw is None and safe_float(pos.get("qty")):
            avg_raw = safe_float(pos.get("cost_basis")) / safe_float(pos.get("qty"))
        chg_raw = pos.get("day_change_pct")
        if chg_raw is None:
            chg_raw = pos.get("chg_pct")
        unrl_raw = pos.get("unrealized_pnl")
        if unrl_raw is None:
            unrl_raw = pos.get("unrealized")
        unrl_pct_raw = pos.get("unrealized_pnl_pct")
        if unrl_pct_raw is None:
            unrl_pct_raw = pos.get("unrealized_p")
        positions.append({
            "ticker": ticker,
            "qty": round(safe_float(pos.get("qty")), 2),
            "price": round(safe_float(pos.get("price")), 2),
            "avg_price": round(safe_float(avg_raw), 3) if avg_raw is not None else None,
            "avg_cost": round(safe_float(avg_raw), 3) if avg_raw is not None else None,
            "chg_pct": round(safe_float(chg_raw), 2) if chg_raw is not None else None,
            "market_val": round(safe_float(pos.get("mkt_val") or pos.get("market_val")), 2),
            "cost_basis": round(safe_float(pos.get("cost_basis")), 2),
            "unrealized": round(safe_float(unrl_raw), 2),
            "unrealized_p": round(safe_float(unrl_pct_raw), 2),
            "pnl_integrity_status": pos.get("pnl_integrity_status"),
            "thesis": pos.get("thesis") or thesis_label(ticker),
        })

    payload = {
        "generated_at":  meta.get("generated_at") or now_sgt(),
        "portfolio_updated_at": meta.get("generated_at") or meta.get("cycle_ts") or now_sgt(),
        "source":        "dataset_raw",
        "regime_short":  regime_short,
        "regime_score":  score_str,
        "regime_color":  rc,
        "regime_emoji":  regime_emoji(regime_short),
        "cio_action":    cio_action,
        "vix":           vix_str,
        "vix_alert":     safe_float(vix_raw) > 20,
        "fg_score":      fg_score,
        "fg_label":      fg_label,
        "fg_color":      fg_color,
        "market_val":    round(market_val, 2),
        "market_val_fmt": money(market_val),
        "total_pnl":     round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 3),
        "pnl_fmt":       f"{money(total_pnl)} ({pct_short(total_pnl_pct)})",
        "pnl_color":     pnl_color,
        "cash":          round(cash, 2),
        "cash_fmt":      money(cash),
        "cash_pct":      round(cash_pct, 2),
        "cash_pct_fmt":  f"{cash_pct:.1f}%",
        "cash_color":    cash_color,
        "integrity":     "PASS" if integrity_ok else "⚠ DATA WARNING",
        "integrity_color": "#4ade80" if integrity_ok else "#ff5566",
        "positions":     positions,
    }
    return json.dumps(payload, ensure_ascii=False)


# ── V3 Agent Council loader & builder ─────────────────────────────────────────
V3_CYCLES_ROOT = Path(r"C:\bluelotus3\data\v3_cycles")
V3_AGENT_IDS   = [
    "data_integrity", "macro_strategist", "portfolio_structure",
    "catalyst_intelligence", "thesis_lifecycle", "risk_challenger",
    "forecasting_brier", "sector_specialist", "sentiment_narrative",
]
V3_AGENT_ICONS = {
    "data_integrity":      "🔍",
    "macro_strategist":    "🌐",
    "portfolio_structure": "📊",
    "catalyst_intelligence": "⚡",
    "thesis_lifecycle":    "🧠",
    "risk_challenger":     "⚔",
    "forecasting_brier":   "🎯",
    "sector_specialist":   "🏭",
    "sentiment_narrative": "📰",
}
V3_AGENT_NAMES = {
    "data_integrity": "Data Integrity Agent",
    "macro_strategist": "Macro Strategist Agent",
    "portfolio_structure": "Portfolio Structure Agent",
    "catalyst_intelligence": "Catalyst Intelligence Agent",
    "thesis_lifecycle": "Thesis Lifecycle Agent",
    "risk_challenger": "Risk Challenger Agent",
    "forecasting_brier": "Forecasting Brier Agent",
    "sector_specialist": "Sector Specialist Agent",
    "sentiment_narrative": "Sentiment Narrative Agent",
}
V3_REC_COLOR = {
    "HOLD": "#4ade80",
    "WAIT": "#4ade80",
    "REVIEW": "#fbbf24",
    "BUY":  "#4ade80",
    "CIO_VERIFICATION_REQUIRED": "#ff5566",
    "SELL": "#ff5566",
    "UNKNOWN": "#8b93a7",
}


def _load_v3_cycle_folder(cycle_dir: Path, latest_cycle_id: str = "") -> Dict[str, Any]:
    """Load briefing and agent reports from one V3 cycle folder."""
    result: Dict[str, Any] = {
        "cycle_id": cycle_dir.name,
        "cycle_path": str(cycle_dir),
        "latest_cycle_id": latest_cycle_id or cycle_dir.name,
    }

    # Load chief strategist briefing
    brief_path = cycle_dir / "chief_strategist_briefing.json"
    if brief_path.exists():
        try:
            result["briefing"] = json.loads(brief_path.read_text(encoding="utf-8"))
        except Exception:
            result["briefing"] = {}
    else:
        result["briefing"] = {}

    # Load chief strategist report text
    report_path = cycle_dir / "chief_strategist_report.txt"
    if report_path.exists():
        try:
            result["report_text"] = report_path.read_text(encoding="utf-8")
        except Exception:
            result["report_text"] = ""
    else:
        result["report_text"] = ""

    # Load all agent reports
    agent_reports: List[Dict[str, Any]] = []
    reports_dir = cycle_dir / "agent_reports"
    for agent_id in V3_AGENT_IDS:
        rpath = reports_dir / f"{agent_id}.json"
        if rpath.exists():
            try:
                data = json.loads(rpath.read_text(encoding="utf-8"))
                agent_reports.append(data)
            except Exception:
                pass
    result["agent_reports"] = agent_reports
    agent_errors: List[Dict[str, Any]] = []
    errors_dir = cycle_dir / "agent_errors"
    for agent_id in V3_AGENT_IDS:
        epath = errors_dir / f"{agent_id}.json"
        if epath.exists():
            try:
                data = json.loads(epath.read_text(encoding="utf-8"))
            except Exception:
                data = {"agent_id": agent_id, "error": "unreadable_agent_error"}
            if isinstance(data, dict):
                data.setdefault("agent_id", agent_id)
                agent_errors.append(data)
    result["agent_errors"] = agent_errors
    learning_path = cycle_dir / "learning_loop_snapshot.json"
    if learning_path.exists():
        try:
            result["learning_loop_snapshot"] = json.loads(learning_path.read_text(encoding="utf-8"))
        except Exception:
            result["learning_loop_snapshot"] = {}
    else:
        result["learning_loop_snapshot"] = {}
    result["publish_ready"] = v3_cycle_publish_ready(result)
    governance_dir = cycle_dir / "governance"
    contradiction_path = governance_dir / "contradiction_register.json"
    decision_strip_path = governance_dir / "cio_decision_strip.json"
    if contradiction_path.exists():
        try:
            result["contradiction_register"] = json.loads(contradiction_path.read_text(encoding="utf-8"))
        except Exception:
            result["contradiction_register"] = {}
    else:
        result["contradiction_register"] = {}
    if decision_strip_path.exists():
        try:
            result["cio_decision_strip"] = json.loads(decision_strip_path.read_text(encoding="utf-8"))
        except Exception:
            result["cio_decision_strip"] = {}
    else:
        result["cio_decision_strip"] = {}
    # Load NITE-PEI block if present in this cycle folder
    nite_pei_path = cycle_dir / "nite_pei_block.json"
    if nite_pei_path.exists():
        try:
            result["nite_pei"] = json.loads(nite_pei_path.read_text(encoding="utf-8"))
        except Exception:
            result["nite_pei"] = {}
    else:
        result["nite_pei"] = {}
    return result


def v3_cycle_publish_ready(v3_data: Dict[str, Any]) -> bool:
    """A cycle is publishable only after the orchestrator wrote its completion snapshot."""
    snapshot = v3_data.get("learning_loop_snapshot", {})
    if not isinstance(snapshot, dict) or not snapshot:
        return False
    reports = v3_data.get("agent_reports", [])
    errors = v3_data.get("agent_errors", [])
    if not isinstance(reports, list):
        reports = []
    if not isinstance(errors, list):
        errors = []
    expected = len(V3_AGENT_IDS)
    reported_count = len({str(item.get("agent_id", "")) for item in reports if isinstance(item, dict) and item.get("agent_id")})
    error_count = len({str(item.get("agent_id", "")) for item in errors if isinstance(item, dict) and item.get("agent_id")})
    snapshot_validated = int(safe_float(snapshot.get("validated_agent_reports", 0)))
    snapshot_errors = snapshot.get("agent_errors", [])
    snapshot_error_count = len(snapshot_errors) if isinstance(snapshot_errors, list) else 0
    return (
        reported_count + error_count >= expected
        and snapshot_validated + snapshot_error_count >= expected
    )


def build_degraded_v3_agent_reports(v3_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Render current-cycle LLM failures as explicit degraded agent status cards."""
    errors = {
        str(item.get("agent_id", "")): str(item.get("error", "agent_unavailable"))
        for item in v3_data.get("agent_errors", [])
        if isinstance(item, dict)
    }
    if not errors:
        return []
    cycle_id = str(v3_data.get("cycle_id", ""))
    created_at = display_sgt_time(cycle_id) or now_sgt()
    reports: List[Dict[str, Any]] = []
    for agent_id in V3_AGENT_IDS:
        error = errors.get(agent_id)
        if not error:
            continue
        reports.append({
            "schema_version": "bluelotus_v3_agent_report_v1.0",
            "cycle_id": cycle_id,
            "agent_id": agent_id,
            "agent_name": V3_AGENT_NAMES.get(agent_id, agent_id.replace("_", " ").title()),
            "agent_role": "Current-cycle degraded LLM status",
            "model_used": "bluelotus-qwen3-4b-gpu",
            "input_refs": {},
            "summary": "Current cycle agent output unavailable; Qwen/Ollama call failed before a validated report was produced.",
            "key_findings": [
                "[OPERATOR] Current V3 cycle executed, but this agent did not produce a validated report.",
                f"[DATASET] Failure reason captured: {error[:180]}",
            ],
            "risk_flags": [
                "P1 Agent council degraded: CIO should not treat stale council analysis as current.",
            ],
            "blocked_actions_observed": ["AUTO_EXECUTION_BLOCKED"],
            "allowed_actions_observed": ["WAIT", "REVIEW"],
            "affected_theses": [],
            "affected_assets": [],
            "causal_completeness": "incomplete",
            "blind_spots": ["Validated Qwen desk analysis unavailable for this cycle."],
            "confidence": 0.0,
            "recommendation_to_chief_strategist": "CIO_VERIFICATION_REQUIRED",
            "requires_cio_attention": True,
            "manual_execution_required": True,
            "llm_order_generation": False,
            "created_at_sgt": created_at,
            "degraded_llm_status": True,
        })
    return reports


def load_v3_cycle_data() -> Dict[str, Any]:
    """Find the newest valid V3 council cycle and load briefing + agent reports."""
    if not V3_CYCLES_ROOT.exists():
        return {}
    folders = sorted(
        [d for d in V3_CYCLES_ROOT.iterdir()
         if d.is_dir() and d.name.startswith("v3_cycle_")],
        key=lambda d: d.name
    )
    if not folders:
        return {}

    latest_cycle_id = folders[-1].name
    latest_data = _load_v3_cycle_folder(folders[-1], latest_cycle_id)
    if not latest_data.get("publish_ready"):
        for folder in reversed(folders[:-1]):
            data = _load_v3_cycle_folder(folder, latest_cycle_id)
            if data.get("publish_ready") and data.get("agent_reports"):
                data["fallback_from_cycle_id"] = latest_cycle_id
                data["fallback_reason"] = "latest_cycle_not_publish_ready"
                return data
    if latest_data.get("agent_reports"):
        if latest_data.get("agent_errors"):
            reported_ids = {str(item.get("agent_id", "")) for item in latest_data.get("agent_reports", []) if isinstance(item, dict)}
            missing_errors = [item for item in latest_data.get("agent_errors", []) if str(item.get("agent_id", "")) not in reported_ids]
            if missing_errors:
                partial_data = dict(latest_data)
                partial_data["agent_errors"] = missing_errors
                latest_data["agent_reports"] = list(latest_data.get("agent_reports", [])) + build_degraded_v3_agent_reports(partial_data)
                latest_data["degraded_llm_cycle"] = True
                latest_data["partial_llm_cycle"] = True
                latest_data["fallback_reason"] = "latest_cycle_partial_agent_errors_rendered"
        return latest_data

    # Qwen/Ollama outages can create fresh cycle folders with 0 agent reports.
    # Do not let an empty/error cycle erase the last valid council on the website.
    for folder in reversed(folders[:-1]):
        data = _load_v3_cycle_folder(folder, latest_cycle_id)
        if data.get("agent_reports"):
            data["fallback_from_cycle_id"] = latest_cycle_id
            data["fallback_reason"] = (
                "latest_cycle_all_agent_errors"
                if latest_data.get("agent_errors") else "latest_cycle_has_no_agent_reports"
            )
            data["latest_agent_errors"] = latest_data.get("agent_errors", [])
            return data

    degraded_reports = build_degraded_v3_agent_reports(latest_data)
    if degraded_reports:
        latest_data["agent_reports"] = degraded_reports
        latest_data["degraded_llm_cycle"] = True
        latest_data["fallback_reason"] = "latest_cycle_agent_errors_rendered"
        return latest_data

    return latest_data


def build_v3_agents_json(v3_data: Dict[str, Any]) -> str:
    """Serialize V3 cycle data to JSON for GitHub Pages live fetch."""
    if not v3_data:
        return json.dumps({"error": "no_v3_data", "generated_at": now_sgt()})
    briefing = v3_data.get("briefing", {})
    degraded = bool(v3_data.get("degraded_llm_cycle"))
    recommended_posture = "CIO_VERIFICATION_REQUIRED" if degraded else briefing.get("recommended_posture", "UNKNOWN")
    agent_consensus = [] if degraded else briefing.get("agent_consensus", [])
    cio_attention_items = (
        ["V3 agent council degraded: Qwen/Ollama did not produce validated reports for the latest cycle."]
        if degraded else briefing.get("cio_attention_items", [])
    )
    payload = {
        "generated_at":        now_sgt(),
        "cycle_id":            v3_data.get("cycle_id", ""),
        "latest_cycle_id":     v3_data.get("latest_cycle_id", v3_data.get("cycle_id", "")),
        "fallback_from_cycle_id": v3_data.get("fallback_from_cycle_id", ""),
        "fallback_reason":     v3_data.get("fallback_reason", ""),
        "degraded_llm_cycle":   bool(v3_data.get("degraded_llm_cycle")),
        "agent_errors":         v3_data.get("agent_errors", []),
        "recommended_posture": recommended_posture,
        "agent_consensus":     agent_consensus,
        "disagreements":       briefing.get("disagreements", []),
        "cio_attention_items": cio_attention_items,
        "manual_execution_required": briefing.get("manual_execution_required", True),
        "created_at_sgt":      briefing.get("created_at_sgt", ""),
        "contradiction_register": v3_data.get("contradiction_register", {}),
        "cio_decision_strip":  v3_data.get("cio_decision_strip", {}),
        "nite_pei":            v3_data.get("nite_pei", {}),
        "agents":              v3_data.get("agent_reports", []),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def build_v3_synthesis_section(v3_data: Dict[str, Any]) -> str:
    """V3 Chief Strategist synthesis — replaces V2 Strategist Brief."""
    if not v3_data:
        return ""

    briefing      = v3_data.get("briefing", {})
    agent_reports = v3_data.get("agent_reports", [])
    degraded_llm_cycle = bool(v3_data.get("degraded_llm_cycle"))
    cash_fortress = bool(briefing.get("cash_fortress_mode") or briefing.get("scout_mode"))
    posture       = "CIO_VERIFICATION_REQUIRED" if degraded_llm_cycle else str(briefing.get("recommended_posture", "UNKNOWN")).upper()
    posture_color = V3_REC_COLOR.get(posture, "#8b93a7")
    disagreements = briefing.get("disagreements", [])
    contradiction_register = v3_data.get("contradiction_register", {}) if isinstance(v3_data.get("contradiction_register"), dict) else {}
    cio_decision_strip = v3_data.get("cio_decision_strip", {}) if isinstance(v3_data.get("cio_decision_strip"), dict) else {}
    allowed_actions = []
    for rpt in agent_reports:
        allowed_actions.extend(rpt.get("allowed_actions_observed", []))
    # Deduplicate, preserve order
    seen: set = set()
    unique_actions = []
    for a in allowed_actions:
        if a not in seen:
            seen.add(a)
            unique_actions.append(a)

    # ── Agent Intelligence Summary rows ───────────────────────────────────────
    agent_rows_html = ""
    for rpt in agent_reports:
        aid      = str(rpt.get("agent_id", ""))
        aname    = str(rpt.get("agent_name", aid)).replace(" Agent", "")
        findings = rpt.get("key_findings", [])
        # ISSUE-E INVARIANT: top tile, detail card, and synthesis all use recommendation_to_chief_strategist
        # Never use a different field for any renderer. This ensures alignment across all views.
        rec      = str(rpt.get("recommendation_to_chief_strategist", "UNKNOWN")).upper()
        icon     = V3_AGENT_ICONS.get(aid, "🤖")
        rc_col   = V3_REC_COLOR.get(rec, "#8b93a7")
        top_finding = normalize_cash_fortress_text(findings[0], cash_fortress) if findings else "No findings reported."
        agent_rows_html += (
            f'<div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;'
            f'border-bottom:1px solid rgba(255,255,255,.04)">'
            f'<span style="font-size:14px;flex-shrink:0;line-height:1.4">{icon}</span>'
            f'<div style="flex:1;min-width:0">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:2px">'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;'
            f'text-transform:uppercase;letter-spacing:.1em;color:#c084fc">{html_escape(aname)}</span>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;padding:1px 6px;'
            f'border-radius:3px;background:rgba({hex_to_rgb_css(rc_col)},.15);color:{rc_col};'
            f'font-weight:600">{html_escape(rec)}</span>'
            f'</div>'
            f'<div style="font-size:12px;color:#bfc8d7;line-height:1.5">'
            f'{html_escape(top_finding)}</div>'
            f'</div>'
            f'</div>'
        )
    if not agent_rows_html:
        agent_rows_html = '<p style="font-size:12px;color:#8b93a7">No agent data available.</p>'
    validated_count = sum(1 for rpt in agent_reports if not rpt.get("degraded_llm_status"))
    degraded_count = sum(1 for rpt in agent_reports if rpt.get("degraded_llm_status"))
    if degraded_llm_cycle:
        synthesis_summary = (
            f'{validated_count} validated agent reports synthesized · {degraded_count} current-cycle agent failures captured · '
            f'Qwen3:4B council degraded'
        )
    else:
        synthesis_summary = f'{validated_count} validated agent reports synthesized · Qwen3:4B agentic council'

    # ── Disagreements ─────────────────────────────────────────────────────────
    disag_rows = ""
    for d in disagreements:
        sev     = str(d.get("severity", "medium")).upper()
        sev_col = "#ff5566" if sev == "HIGH" else "#fbbf24"
        topic   = clean_text(d.get("topic", ""), 80)
        disag_rows += (
            f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0">'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;padding:1px 5px;'
            f'border-radius:3px;background:rgba({hex_to_rgb_css(sev_col)},.15);color:{sev_col}">'
            f'{html_escape(sev)}</span>'
            f'<span style="font-size:12px;color:#94a3b8">{html_escape(topic)}</span>'
            f'</div>'
        )

    # ── Allowed actions pills ─────────────────────────────────────────────────
    action_pills = "".join(
        f'<span style="font-family:JetBrains Mono,monospace;font-size:10px;padding:3px 10px;'
        f'border-radius:4px;background:rgba(192,132,252,.12);color:#c084fc;font-weight:600">'
        f'{html_escape(a)}</span>'
        for a in unique_actions[:5]
    )
    strip_posture = str(cio_decision_strip.get("posture", "") or posture).upper()
    strip_color = V3_REC_COLOR.get(strip_posture, "#ff5566" if contradiction_register.get("p1_count") else "#8b93a7")
    contradiction_count = int(safe_float(contradiction_register.get("contradiction_count", 0)))
    p1_count = int(safe_float(contradiction_register.get("p1_count", 0)))
    decision_items = cio_decision_strip.get("cio_decision_required", [])
    if not isinstance(decision_items, list):
        decision_items = [decision_items]
    blocked_items = cio_decision_strip.get("action_blocked", [])
    if not isinstance(blocked_items, list):
        blocked_items = [blocked_items]
    governance_html = ""
    if contradiction_register or cio_decision_strip:
        decision_text = decision_items[0] if decision_items else "No contradiction-triggered CIO decision required."
        blocked_text = ", ".join(str(x) for x in blocked_items[:5]) if blocked_items else "None"
        governance_html = (
            f'<div style="margin-bottom:18px;padding:14px 18px;background:rgba({hex_to_rgb_css(strip_color)},.08);'
            f'border-left:3px solid {strip_color};border-radius:0 8px 8px 0">'
            f'<div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:8px">'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.14em;'
            f'text-transform:uppercase;color:{strip_color}">Contradiction Governance</div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;color:{strip_color};font-weight:700">'
            f'{html_escape(strip_posture)}</div>'
            f'</div>'
            f'<div style="font-size:11px;color:#bfc8d7;line-height:1.5;margin-bottom:6px">'
            f'{contradiction_count} item(s) detected · P1 {p1_count}</div>'
            f'<div style="font-size:11px;color:#dbe5f5;line-height:1.5;margin-bottom:6px">'
            f'CIO decision: {html_escape(str(decision_text))}</div>'
            f'<div style="font-size:10px;color:#94a3b8;line-height:1.45">'
            f'Blocked: {html_escape(blocked_text)}</div>'
            f'</div>'
        )

    return (
        f'<div style="background:rgba(13,16,32,.96);border:1px solid rgba(192,132,252,.35);'
        f'border-radius:18px;padding:28px;margin-bottom:16px">'
        # Header
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;'
        f'margin-bottom:20px;gap:16px">'
        f'<div>'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.18em;'
        f'text-transform:uppercase;color:#c084fc;margin-bottom:8px">V3 Chief Strategist Synthesis</div>'
        f'<div style="font-size:13px;color:#94a3b8;line-height:1.5">'
        f'{html_escape(synthesis_summary)}'
        f'</div>'
        f'</div>'
        f'<div style="text-align:right;flex-shrink:0">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#8b93a7;'
        f'text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px">Posture</div>'
        f'<div style="font-size:22px;font-weight:700;color:{posture_color};'
        f'font-family:JetBrains Mono,monospace">{html_escape(posture)}</div>'
        f'</div>'
        f'</div>'
        # Agent findings
        f'<div style="margin-bottom:18px">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.14em;'
        f'text-transform:uppercase;color:#8b93a7;margin-bottom:10px">Agent Intelligence Summary</div>'
        f'{agent_rows_html}'
        f'</div>'
        f'{governance_html}'
        # Disagreements
        + (f'<div style="margin-bottom:18px">'
           f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.14em;'
           f'text-transform:uppercase;color:#8b93a7;margin-bottom:6px">Council Disagreements</div>'
           f'{disag_rows}'
           f'</div>' if disag_rows else '')
        # CIO action callout
        + f'<div style="padding:14px 18px;background:rgba({hex_to_rgb_css(posture_color)},.08);'
        f'border-left:3px solid {posture_color};border-radius:0 8px 8px 0">'
        f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.14em;'
        f'text-transform:uppercase;color:{posture_color};margin-bottom:8px">CIO Permitted Actions</div>'
        f'<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px">{action_pills}</div>'
        f'<div style="font-size:11px;color:#8b93a7;line-height:1.5">'
        f'Manual execution required · No automatic orders generated by pipeline · '
        f'CIO discretion applies to all entries and exits.'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def build_v3_agent_council_section(v3_data: Dict[str, Any]) -> str:
    """Build the V3 Agent Council HTML section for chief-strategist.html."""
    if not v3_data or not v3_data.get("agent_reports"):
        return ""

    briefing      = v3_data.get("briefing", {})
    agent_reports = v3_data.get("agent_reports", [])
    cash_fortress = bool(briefing.get("cash_fortress_mode") or briefing.get("scout_mode"))
    cycle_id      = v3_data.get("cycle_id", "")
    latest_cycle_id = str(v3_data.get("latest_cycle_id", cycle_id))
    fallback_from_cycle_id = str(v3_data.get("fallback_from_cycle_id", ""))
    degraded_llm_cycle = bool(v3_data.get("degraded_llm_cycle"))
    posture       = "CIO_VERIFICATION_REQUIRED" if degraded_llm_cycle else str(briefing.get("recommended_posture", "UNKNOWN")).upper()
    posture_color = V3_REC_COLOR.get(posture, "#8b93a7")
    created_at    = briefing.get("created_at_sgt", "")
    created_display = display_sgt_time(created_at) or display_sgt_time(cycle_id)
    latest_display = display_sgt_time(latest_cycle_id)
    fallback_html = ""
    if fallback_from_cycle_id:
        fallback_html = (
            f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:#fbbf24;margin-top:5px">'
            f'Latest agent attempt {html_escape(latest_display)} unavailable · showing last valid council snapshot'
            f'</div>'
        )
    elif degraded_llm_cycle:
        fallback_html = (
            f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.12em;'
            f'text-transform:uppercase;color:#ff5566;margin-top:5px">'
            f'Current cycle degraded · Qwen/Ollama agent calls failed · showing current failure state, not stale council analysis'
            f'</div>'
        )

    disagreements = briefing.get("disagreements", [])
    cio_items     = briefing.get("cio_attention_items", [])

    # ── Agent cards ──────────────────────────────────────────────────────────
    def rec_color(rec: str) -> str:
        return V3_REC_COLOR.get(rec.upper(), "#8b93a7")

    def confidence_bar(conf: float) -> str:
        pct_v = int(conf * 100)
        col = "#4ade80" if pct_v >= 80 else ("#fbbf24" if pct_v >= 60 else "#ff5566")
        return (
            f'<div style="display:flex;align-items:center;gap:6px;margin-top:4px">'
            f'<div style="flex:1;height:3px;background:rgba(255,255,255,.1);border-radius:2px">'
            f'<div style="width:{pct_v}%;height:3px;background:{col};border-radius:2px"></div>'
            f'</div>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;color:{col}">'
            f'{pct_v}%</span>'
            f'</div>'
        )

    cards_html = ""
    for rpt in agent_reports:
        aid      = str(rpt.get("agent_id", ""))
        aname    = str(rpt.get("agent_name", aid))
        arole    = str(rpt.get("agent_role", ""))
        # ISSUE-E INVARIANT: top tile, detail card, and synthesis all use recommendation_to_chief_strategist
        # Never use a different field for any renderer. This ensures alignment across all views.
        rec      = str(rpt.get("recommendation_to_chief_strategist", "UNKNOWN")).upper()
        conf     = float(rpt.get("confidence", 0.0))
        findings = rpt.get("key_findings", [])
        flags    = rpt.get("risk_flags", [])
        blind    = rpt.get("blind_spots", [])
        icon     = V3_AGENT_ICONS.get(aid, "🤖")
        rc_col   = rec_color(rec)
        conf_bar = confidence_bar(conf)

        findings_html = "".join(
            f'<div style="padding:2px 0;font-size:11px;color:#bfc8d7;line-height:1.45">'
            f'· {html_escape(normalize_cash_fortress_text(f, cash_fortress))}</div>'
            for f in findings
        ) or '<div style="font-size:11px;color:#8b93a7">No findings</div>'

        flags_html = "".join(
            f'<div style="padding:2px 0;font-size:10px;color:#ff8fa0;line-height:1.4">'
            f'⚠ {html_escape(normalize_cash_fortress_text(fl, cash_fortress))}</div>'
            for fl in flags
        )

        blind_html = "".join(
            f'<div style="padding:2px 0;font-size:10px;color:#94a3b8;line-height:1.4">'
            f'◦ {html_escape(clean_text(b))}</div>'
            for b in blind
        )

        cards_html += (
            f'<div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);'
            f'border-radius:14px;padding:16px 18px;display:flex;flex-direction:column;gap:8px">'
            # Header row
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px">'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<span style="font-size:18px;line-height:1">{icon}</span>'
            f'<div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.14em;'
            f'text-transform:uppercase;color:#c084fc;line-height:1.2">{html_escape(aname)}</div>'
            f'<div style="font-size:10px;color:#8b93a7;line-height:1.3;margin-top:2px">'
            f'{html_escape(clean_text(arole, 120))}</div>'
            f'</div>'
            f'</div>'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;padding:3px 8px;'
            f'border-radius:4px;background:rgba({hex_to_rgb_css(rc_col)},.15);color:{rc_col};'
            f'white-space:nowrap;flex-shrink:0;font-weight:600">{html_escape(rec)}</span>'
            f'</div>'
            # Confidence bar
            f'<div><div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#8b93a7;'
            f'text-transform:uppercase;letter-spacing:.1em">Confidence</div>{conf_bar}</div>'
            # Key findings
            f'<div>'
            f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#8b93a7;'
            f'text-transform:uppercase;letter-spacing:.1em;margin-bottom:3px">Key Findings</div>'
            f'{findings_html}'
            f'</div>'
            # Risk flags (if any)
            + (f'<div>'
               f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#8b93a7;'
               f'text-transform:uppercase;letter-spacing:.1em;margin-bottom:3px">Risk Flags</div>'
               f'{flags_html}'
               f'</div>' if flags_html else '')
            # Blind spots (if any)
            + (f'<div>'
               f'<div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#8b93a7;'
               f'text-transform:uppercase;letter-spacing:.1em;margin-bottom:3px">Blind Spots</div>'
               f'{blind_html}'
               f'</div>' if blind_html else '')
            + f'</div>'
        )

    # ── Disagreements ─────────────────────────────────────────────────────────
    disag_html = ""
    for d in disagreements[:3]:
        sev = str(d.get("severity", "medium")).upper()
        sev_col = "#ff5566" if sev == "HIGH" else "#fbbf24"
        disag_html += (
            f'<div style="padding:8px 0;border-bottom:1px solid rgba(255,255,255,.04)">'
            f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;padding:2px 6px;'
            f'border-radius:3px;background:rgba({hex_to_rgb_css(sev_col)},.15);color:{sev_col}">'
            f'{html_escape(sev)}</span>'
            f'<span style="font-size:12px;color:#e2e8f0;font-weight:500">'
            f'{html_escape(clean_text(d.get("topic", "")))}</span>'
            f'</div>'
            f'<div style="font-size:11px;color:#94a3b8;line-height:1.5">'
            f'{html_escape(clean_text(d.get("chief_strategist_resolution", "")))}</div>'
            f'</div>'
        )
    if not disag_html:
        disag_html = '<p style="font-size:12px;color:#8b93a7">No disagreements logged.</p>'

    # ── Consensus row ─────────────────────────────────────────────────────────
    consensus_pills = ""
    for item in briefing.get("agent_consensus", []):
        # "Macro Strategist Agent: REVIEW"
        parts = str(item).split(": ", 1)
        aname_short = parts[0].replace(" Agent", "").strip() if len(parts) > 1 else parts[0]
        rec_short   = parts[1].strip() if len(parts) > 1 else "?"
        rc_c        = V3_REC_COLOR.get(rec_short.upper(), "#8b93a7")
        consensus_pills += (
            f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px">'
            f'<span style="font-family:JetBrains Mono,monospace;font-size:9px;padding:2px 7px;'
            f'border-radius:4px;background:rgba({hex_to_rgb_css(rc_c)},.18);color:{rc_c};'
            f'font-weight:600;white-space:nowrap">{html_escape(rec_short)}</span>'
            f'<span style="font-size:9px;color:#8b93a7;text-align:center;max-width:70px;line-height:1.2">'
            f'{html_escape(aname_short)}</span>'
            f'</div>'
        )

    return f"""
<div style="margin-bottom:20px">
  <!-- V3 Header -->
  <div style="display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:14px">
    <div>
      <div style="font-family:Cormorant Garamond,serif;font-size:36px;color:#c084fc;line-height:1;margin-bottom:4px">
        V3 Agent Council
      </div>
      <div style="font-family:JetBrains Mono,monospace;font-size:10px;letter-spacing:.16em;
        text-transform:uppercase;color:#8b93a7">
        Qwen3:4B · 9 Agents · {html_escape(cycle_id)} · Snapshot {html_escape(created_display)}
      </div>
      {fallback_html}
    </div>
    <div style="text-align:right">
      <div style="font-family:JetBrains Mono,monospace;font-size:9px;color:#8b93a7;
        text-transform:uppercase;letter-spacing:.1em;margin-bottom:4px">Recommended Posture</div>
      <div style="font-size:20px;font-weight:700;color:{posture_color};
        font-family:JetBrains Mono,monospace">{html_escape(posture)}</div>
    </div>
  </div>

  <!-- Consensus strip -->
  <div style="background:rgba(13,16,32,.94);border:1px solid rgba(192,132,252,.18);
    border-radius:12px;padding:14px 18px;margin-bottom:14px">
    <div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.16em;
      text-transform:uppercase;color:#c084fc;margin-bottom:10px">Agent Consensus</div>
    <div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:flex-start">
      {consensus_pills}
    </div>
  </div>

  <!-- 9 Agent Cards: 3-column grid -->
  <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px">
    {cards_html}
  </div>

  <!-- Disagreements -->
  <div style="background:rgba(13,16,32,.94);border:1px solid rgba(248,113,113,.22);
    border-radius:12px;padding:16px 20px;margin-bottom:14px">
    <div style="font-family:JetBrains Mono,monospace;font-size:9px;letter-spacing:.16em;
      text-transform:uppercase;color:#f87171;margin-bottom:8px">
      Council Disagreements ({len(disagreements)})
    </div>
    {disag_html}
  </div>
</div>
<hr style="border:none;border-top:1px solid rgba(192,132,252,.18);margin:20px 0">
"""


# ── Main ───────────────────────────────────────────────────────────────────────
def run_once() -> None:
    print("=" * 78)
    print(f"BlueLotus Publisher v1.7 [V2 Integrated] — {now_sgt()}")
    print(f"Loop: {'ON' if RUN_LOOP else 'OFF'} · Interval: {RUN_EVERY_MINUTES} min")
    print("=" * 78)

    ds          = load_dataset()
    if master_prompt_is_active and build_chief_strategist_master_prompt and not master_prompt_is_active(ds):
        try:
            build_chief_strategist_master_prompt(dataset_path=Path(DATASET_RAW_PATH))
            ds = load_dataset()
            print("  Chief Strategist master prompt rebuilt for publisher context")
        except Exception as exc:
            print(f"  Master prompt WARNING: {exc}")
    if governance_is_active and build_chief_strategist_governance_pack and not governance_is_active(ds):
        try:
            build_chief_strategist_governance_pack(dataset_path=Path(DATASET_RAW_PATH))
            ds = load_dataset()
            print("  CSG governance pack rebuilt for publisher context")
        except Exception as exc:
            print(f"  CSG governance WARNING: {exc}")
    if capsule_is_active and build_cio_context_capsule and not capsule_is_active(ds):
        try:
            build_cio_context_capsule(dataset_path=Path(DATASET_RAW_PATH))
            ds = load_dataset()
            print("  CIO context capsule rebuilt for publisher context")
        except Exception as exc:
            print(f"  CIO context WARNING: {exc}")
    if build_v3_1_to_v3_4_payload:
        try:
            ds = build_v3_1_to_v3_4_payload(ds)
            Path(DATASET_RAW_PATH).write_text(json.dumps(ds, indent=2, ensure_ascii=False), encoding="utf-8")
            print("  V3.1-V3.4 architecture payload refreshed for publisher context")
        except Exception as exc:
            print(f"  V3.1-V3.4 publisher payload WARNING: {exc}")
    public_dataset = ""
    if build_public_dataset:
        try:
            public_payload = build_public_dataset(ds)
            public_path = Path(PUBLIC_DATASET_PATH)
            public_path.parent.mkdir(parents=True, exist_ok=True)
            public_dataset = json.dumps(public_payload, indent=2, ensure_ascii=False, default=str)
            public_path.write_text(public_dataset, encoding="utf-8")
            print(f"  Public dataset refreshed: {public_path} ({len(public_dataset.encode('utf-8'))} bytes)")
        except Exception as exc:
            print(f"  Public dataset WARNING: {exc}")
    intel_notes = load_manual_intelligence()
    print(f"  Intelligence notes loaded: {len(intel_notes)} active")
    v3_data     = load_v3_cycle_data()
    if v3_data:
        print(f"  V3 cycle loaded: {v3_data.get('cycle_id','?')} ({len(v3_data.get('agent_reports',[]))} agents)")
    else:
        print("  V3 cycle: not found (skipping council section)")

    nite_pei_block = v3_data.get("nite_pei", {}) if v3_data else {}

    report      = append_master_prompt_report(
        append_cio_context_report(
            append_benchmark_report(append_csg_report(append_remediation_report(append_str_report(append_acms_cop_report(build_chief_strategist_report(ds, intel_notes=intel_notes)), ds), ds), ds), ds),
            ds,
        ),
        ds,
    )
    # Append NITE-PEI section to TXT report
    if nite_pei_block and append_nite_pei_report:
        report = append_nite_pei_report(report, nite_pei_block)
    save_local_report(report)

    # NOTE: NITE-PEI content is now embedded inside Bluelotus_V3_Report.* via research_report_generator.py
    # Standalone NITE-PEI files are intentionally NOT generated here (removed per BLV3-ACCOUNTABILITY-001)

    dashboard_html   = build_dashboard_html(ds)
    cs_html          = build_chief_strategist_html(report, ds, intel_notes=intel_notes, v3_data=v3_data)
    portfolio_live   = build_portfolio_live(ds)
    v3_agents_json   = build_v3_agents_json(v3_data)

    ensure_nojekyll()
    assert_publishable(dashboard_html)

    github_push("index.html",                dashboard_html,  f"BlueLotus Dashboard v1.7 — {now_sgt()}")
    github_push("chief-strategist.html",     cs_html,         f"Chief Strategist + V3 Council — {now_sgt()}")
    github_push("data/portfolio_live.json",  portfolio_live,  f"portfolio probe {now_sgt()}")
    github_push("data/chief_strategist_v17.txt", report, f"Archive v1.7 — {now_sgt()}")
    github_push("data/v3_agents_latest.json", v3_agents_json, f"V3 agents {now_sgt()}")
    if public_dataset:
        github_push("data/dataset_public.json", public_dataset, f"V3 compact public dataset {now_sgt()}")

    # Telegram push moved to news_probe_daemon.py (10-min live headlines cycle)

    print(f"  Dashboard URL        : {BASE_URL}/")
    print(f"  Chief Strategist URL : {BASE_URL}/chief-strategist.html")
    print("  Completed.")


def main() -> None:
    """Single-shot publisher — called by V2 pipeline at end of each cycle."""
    run_once()


if __name__ == "__main__":
    main()

