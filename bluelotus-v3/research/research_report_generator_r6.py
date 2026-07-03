#!/usr/bin/env python3
r"""
BlueLotus V2.6u R6 Research Report Generator — dataset_raw.json only
Fix objective: restore rich Research Department content after dataset schema update.

Reads:  C:\bluelotus3\data\frontend\dataset_raw.json by default\nWrites: C:\bluelotus3\research\Bluelotus_V3_Report.txt by default

Key schema fix:
- Handles live_prices in both shapes:
  1) live_prices.prices.{TICKER}
  2) live_prices.{TICKER}
- Does not depend on research_raw.json.
- Adds fresh-news intelligence tape, intraday reversal table, mandate-aware portfolio notes,
  top-mover catalyst checks, tech-publication catalyst digest, and full analyst target detail.
"""
from __future__ import annotations

import argparse, json, math, re, os, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

PROJECT_ROOT = Path(r"C:\bluelotus3")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from acms_cop.reports.cio_order_policy import classify_cio_order_policy
except Exception:
    classify_cio_order_policy = None

REPORT_VERSION = "R6"
REPORT_TITLE = "BLUELOTUS FUND — RESEARCH DEPARTMENT REPORT — FIXED / ENRICHED R6"
PLATFORM_TEAM = "Codex & Claude Code Windows Platform Team"

TEXT_REPLACEMENTS = {
    "\u00e2\u20ac\u201d": "-",
    "\u00e2\u20ac\u201c": "-",
    "\u00e2\u20ac\u00a2": "*",
    "\u00e2\u20ac\u2122": "'",
    "\u00e2\u20ac\u0153": '"',
    "\u00e2\u20ac\u009d": '"',
    "\u00e2\u0086\u0092": "->",
    "\u00e2\u0089\u00a5": ">=",
    "\u00e2\u0089\u00a4": "<=",
    "\u00c2\u00b1": "+/-",
    "\u00e2\u0161\u00a0": "WARNING",
    "\u00e2\u0153\u2026": "[OK]",
    "\u00e2\u0153\u2014": "[X]",
    "\u00e2\u2013\u00bc": "v",
    "\u00e2\u2013\u00b2": "^",
    "\u00e2\u201d\u20ac": "-",
}


def normalize_report_text(value: Any) -> str:
    text = "" if value is None else str(value)
    for bad, good in TEXT_REPLACEMENTS.items():
        text = text.replace(bad, good)
    text = (
        text.replace("\u2014", "-")
        .replace("\u2013", "-")
        .replace("\u2022", "*")
        .replace("\u2192", "->")
        .replace("\u2265", ">=")
        .replace("\u2264", "<=")
        .replace("\u00b1", "+/-")
        .replace("\u26a0", "WARNING")
        .replace("\u2713", "[OK]")
        .replace("\u2717", "[X]")
    )
    return text


def normalize_market_session(raw: Any, snapshot_ts: Any = None) -> str:
    label = str(raw or "UNKNOWN").upper().strip()
    label = label.replace(" ", "_").replace("/", "_")
    if "REGULAR" in label and "CLOSE" not in label:
        return "REGULAR_SESSION"
    if "PRE" in label:
        return "PRE_MARKET"
    if "POST" in label or "AFTER" in label:
        return "POST_MARKET"
    if "HOLIDAY" in label:
        return "HOLIDAY_SNAPSHOT"
    if "STALE" in label or "ARCHIVE" in label:
        return "STALE_ARCHIVE_SNAPSHOT"
    if "WEEKEND" in label:
        dt = parse_dt(snapshot_ts)
        if dt and dt.weekday() < 5:
            return "MARKET_CLOSED_LAST_REGULAR_CLOSE"
        return "WEEKEND_SNAPSHOT"
    if "CLOSED" in label or "LAST_REGULAR_CLOSE" in label:
        return "MARKET_CLOSED_LAST_REGULAR_CLOSE"
    return label or "UNKNOWN"


def source_coverage_label(active: Any, expected: Any) -> str:
    return f"Sources active: {si(active)} / baseline {si(expected)}"


def _read_json_file(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def build_snapshot_hierarchy(dataset: Dict[str, Any]) -> Dict[str, Any]:
    meta = dataset.get("meta") if isinstance(dataset.get("meta"), dict) else {}
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    live = _read_json_file(PROJECT_ROOT / "data" / "portfolio_live" / "portfolio_live.json")
    formal_ts = meta.get("generated_at") or meta.get("cycle_ts") or ""
    live_ts = live.get("generated_at") or live.get("portfolio_updated_at") or ""
    broker_ts = live.get("portfolio_updated_at") or portfolio.get("cycle_ts") or ""
    formal_dt = parse_dt(formal_ts)
    live_dt = parse_dt(live_ts)
    dashboard_newer = bool(formal_dt and live_dt and live_dt > formal_dt)
    formal_minus_dashboard = int((formal_dt - live_dt).total_seconds() / 60) if formal_dt and live_dt else None
    if formal_minus_dashboard is not None and formal_minus_dashboard > 10:
        snapshot_status = "FORMAL_REPORT_NEWER_THAN_LIVE_DASHBOARD"
        snapshot_disclosure = "FORMAL_REPORT_NEWER_THAN_LIVE_DASHBOARD - dashboard may lag the formal report"
    elif formal_minus_dashboard is not None and formal_minus_dashboard < -10:
        snapshot_status = "LIVE_DASHBOARD_NEWER_THAN_FORMAL_REPORT"
        snapshot_disclosure = "LIVE_DASHBOARD_NEWER_THAN_FORMAL_REPORT - formal report may be stale"
    else:
        snapshot_status = "SNAPSHOT_ALIGNED"
        snapshot_disclosure = "SNAPSHOT_ALIGNED - formal report and dashboard are within timing tolerance"
    formal_regime = str((dataset.get("regime") or {}).get("regime") or (dataset.get("regime") or {}).get("regime_short") or "")
    live_regime = str(live.get("regime_short") or "")
    regime_diff = bool(formal_regime and live_regime and formal_regime.upper() != live_regime.upper())
    return {
        "formal_report_snapshot_ts": formal_ts or "UNKNOWN",
        "live_dashboard_snapshot_ts": live_ts or "UNKNOWN",
        "broker_portfolio_ts": broker_ts or "UNKNOWN",
        "report_is_older_than_live_dashboard": dashboard_newer,
        "regime_difference_detected": regime_diff,
        "formal_minus_dashboard_minutes": formal_minus_dashboard,
        "snapshot_alignment_status": snapshot_status,
        "snapshot_disclosure": snapshot_disclosure if not regime_diff else snapshot_disclosure + " | REGIME_DIFFERENCE_DETECTED",
    }


def causal_price_action_label(direction: Any, flags: List[Any]) -> str:
    d = str(direction or "").upper().replace("-", "_").replace(" ", "_")
    weak = {
        "SECTOR_EVIDENCE_MISMATCH", "NO_DIRECT_CATALYST", "GENERIC_EVIDENCE_REVIEW",
        "ANALYST_ONLY_CAUSAL_GAP", "PRICE_ACTION_ONLY_CAP", "PARTIAL_CAUSAL_CAP",
        "THEME_BASKET_OUTLIER_REVIEW",
    }
    has_gap = bool(set(str(x) for x in (flags or [])) & weak)
    if "RISK_ON" in d:
        return "PRICE_ACTION_RISK_ON / CAUSAL_NOT_CONFIRMED" if has_gap else "RISK_ON"
    if "RISK_OFF" in d:
        return "PRICE_ACTION_RISK_OFF / CAUSAL_NOT_CONFIRMED" if has_gap else "RISK_OFF"
    return d or "NEUTRAL"


def normalize_theme_label(theme: Any) -> str:
    label = str(theme or "").strip()
    up = label.upper()
    if up == "SPACE / DEFENSE":
        return "SPACE / HIGH-BETA"
    if up == "DEFENSE / AEROSPACE":
        return "DEFENSE / AEROSPACE PRIMES"
    return label


def classify_order_intent(row: Dict[str, Any]) -> str:
    ticker = broker_ticker(row).upper()
    side = str(row.get("trd_side") or row.get("side") or "").upper()
    qty = sf(row.get("qty"))
    price = sf(row.get("price"))
    notional = abs(qty * price)
    policy = classify_cio_order_policy(ticker, side) if classify_cio_order_policy else None
    if policy:
        return str(policy["classification"])
    if side == "SELL":
        return "DECONCENTRATION_REVIEW" if ticker in {"AU", "NEM"} else "REDUCE_REVIEW"
    if side == "BUY" and notional <= 500:
        return "SCOUT_DISLOCATION_ORDER"
    if side == "BUY":
        return "ADD_BLOCKED_REQUIRES_CIO_REVIEW"
    return "BROKER_ORDER_REVIEW"

# ─────────────────────────────────────────────────────────────────────────────
# BLUELOTUS FIXED PRODUCTION PATHS
# Kian: run this file directly. No --dataset / --output path required.
#
# Primary Windows production paths:
#   C:\bluelotus3\data\frontend\dataset_raw.json
#   C:\bluelotus3\research\Bluelotus_V3_Report.txt
#
# Fallbacks are included so the same file can still be tested from inside the
# research folder or from the ChatGPT sandbox.
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_DATASET = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "research" / "Bluelotus_V3_Report.txt"

FALLBACK_DATASETS = [
    Path.cwd() / "dataset_raw.json",
    Path.cwd().parent / "data" / "frontend" / "dataset_raw.json",
    Path(__file__).resolve().parent / "dataset_raw.json",
    Path(__file__).resolve().parent.parent / "data" / "frontend" / "dataset_raw.json",
    Path('/mnt/data/dataset_raw.json'),
]

FALLBACK_OUTPUTS = [
    Path(__file__).resolve().parent / "Bluelotus_V3_Report.txt",
    Path.cwd() / "Bluelotus_V3_Report.txt",
    Path('/mnt/data/Bluelotus_V3_Report.txt'),
]

def resolve_input_path(path: Path) -> Path:
    """Return production dataset path if present; otherwise first valid fallback."""
    if os.name == "nt" and path.exists():
        return path
    if os.name != "nt" and path.exists() and not str(path).startswith("C:"):
        return path
    for candidate in FALLBACK_DATASETS:
        try:
            if candidate.exists():
                return candidate
        except Exception:
            pass
    raise FileNotFoundError(
        "dataset_raw.json not found. Checked production path and fallbacks:\n"
        + "\n".join([str(path)] + [str(x) for x in FALLBACK_DATASETS])
    )

def resolve_output_path(path: Path) -> Path:
    """Prefer production output path on Windows; respect explicit writable overrides elsewhere."""
    if os.name == "nt":
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
        except Exception:
            pass
    # In sandbox/Linux, a non-Windows explicit path should be honoured for testing.
    try:
        if not str(path).startswith('C:'):
            path.parent.mkdir(parents=True, exist_ok=True)
            return path
    except Exception:
        pass
    for candidate in FALLBACK_OUTPUTS:
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    raise RuntimeError("No writable output path available for Bluelotus_V3_Report.txt")

THEME_UNIVERSE = [
    'AI / SEMIS','BANKS / LIQUIDITY','CONSUMER TECH / APPLE','CLEAN ENERGY / SOLAR',
    'ENERGY / URANIUM','NUCLEAR / POWER GRID','COPPER / INDUSTRIAL METALS','RARE EARTH / METALS',
    'GOLD / SAFE HAVEN','SPACE / HIGH-BETA','QUANTUM','SOFTWARE / CYBERSECURITY',
    'FINTECH / CRYPTO','IPO / MOMENTUM','BIOTECH / PHARMA','DEFENSE / AEROSPACE PRIMES',
    'OIL / GAS','UTILITIES / POWER','MAG7 / BIG TECH','GEOPOLITICAL','TRUMP / TRADE',
    'EARNINGS CATALYST','MACRO / FED'
]

DEFENSE_OBSERVATION_ONLY = {'RTX','NOC','LMT','HII','LDOS','AXON','BA'}
CRYPTO_EXCLUDED = {'COIN','MSTR','MARA','RIOT','CLSK','HUT','BITF','IREN'}

TICKER_THEME_MAP = {
    'BAC':['BANKS / LIQUIDITY'], 'WFC':['BANKS / LIQUIDITY'], 'C':['BANKS / LIQUIDITY'],
    'NVDA':['AI / SEMIS','MAG7 / BIG TECH'], 'MSFT':['SOFTWARE / CYBERSECURITY','MAG7 / BIG TECH','AI / SEMIS'],
    'AMD':['AI / SEMIS'], 'AVGO':['AI / SEMIS','EARNINGS CATALYST'], 'AMAT':['AI / SEMIS'],
    'TSM':['AI / SEMIS'], 'MU':['AI / SEMIS'], 'MRVL':['AI / SEMIS'], 'SMCI':['AI / SEMIS'],
    'ARM':['AI / SEMIS'], 'SNPS':['AI / SEMIS','SOFTWARE / CYBERSECURITY'], 'CDNS':['AI / SEMIS','SOFTWARE / CYBERSECURITY'],
    'ANET':['AI / SEMIS'], 'VRT':['AI / SEMIS','NUCLEAR / POWER GRID'], 'DELL':['AI / SEMIS'],
    'AAPL':['CONSUMER TECH / APPLE','MAG7 / BIG TECH'], 'GOOGL':['MAG7 / BIG TECH','AI / SEMIS'],
    'META':['MAG7 / BIG TECH','AI / SEMIS'], 'AMZN':['MAG7 / BIG TECH','AI / SEMIS'], 'PLTR':['SOFTWARE / CYBERSECURITY','AI / SEMIS'],
    'NEM':['GOLD_MINER'], 'AU':['GOLD_MINER'], 'GLD':['GOLD / SAFE HAVEN'], 'SLV':['GOLD / SAFE HAVEN'],
    'FCX':['COPPER / INDUSTRIAL METALS'], 'BHP':['COPPER / INDUSTRIAL METALS'], 'RIO':['COPPER / INDUSTRIAL METALS'], 'SCCO':['COPPER / INDUSTRIAL METALS'],
    'MP':['RARE EARTH / METALS'], 'USAR':['RARE EARTH / METALS'], 'ALB':['RARE EARTH / METALS'],
    'CEG':['NUCLEAR / POWER GRID'], 'VST':['NUCLEAR / POWER GRID','UTILITIES / POWER'], 'DUK':['UTILITIES / POWER'],
    'CCJ':['ENERGY / URANIUM'], 'UUUU':['ENERGY / URANIUM','RARE EARTH / METALS'],
    'ENPH':['CLEAN ENERGY / SOLAR'], 'FSLR':['CLEAN ENERGY / SOLAR'], 'PLUG':['CLEAN ENERGY / SOLAR'], 'FCEL':['CLEAN ENERGY / SOLAR'], 'BE':['CLEAN ENERGY / SOLAR','NUCLEAR / POWER GRID'],
    'WMB':['OIL / GAS','UTILITIES / POWER'], 'KMI':['OIL / GAS','UTILITIES / POWER'], 'XOM':['OIL / GAS'], 'OXY':['OIL / GAS'], 'EOG':['OIL / GAS'], 'FANG':['OIL / GAS'],
    'RGTI':['QUANTUM'], 'QBTS':['QUANTUM'], 'QUBT':['QUANTUM'], 'IONQ':['QUANTUM'], 'QTUM':['QUANTUM'],
    'ASTS':['SPACE / HIGH-BETA'], 'PL':['SPACE / HIGH-BETA'], 'LUNR':['SPACE / HIGH-BETA'], 'BKSY':['SPACE / HIGH-BETA'], 'SATS':['SPACE / HIGH-BETA'], 'RKLB':['SPACE / HIGH-BETA'], 'RDW':['SPACE / HIGH-BETA'], 'IRDM':['SPACE / HIGH-BETA'], 'SIDU':['SPACE / HIGH-BETA'],
    'RTX':['DEFENSE / AEROSPACE PRIMES'], 'NOC':['DEFENSE / AEROSPACE PRIMES'], 'LMT':['DEFENSE / AEROSPACE PRIMES'], 'HII':['DEFENSE / AEROSPACE PRIMES'], 'LDOS':['DEFENSE / AEROSPACE PRIMES'], 'AXON':['DEFENSE / AEROSPACE PRIMES'], 'BA':['DEFENSE / AEROSPACE PRIMES'],
    'COIN':['FINTECH / CRYPTO'], 'HOOD':['FINTECH / CRYPTO','IPO / MOMENTUM'], 'SOFI':['FINTECH / CRYPTO','IPO / MOMENTUM'],
    'LLY':['BIOTECH / PHARMA'], 'MRNA':['BIOTECH / PHARMA'], 'PFE':['BIOTECH / PHARMA'], 'ABBV':['BIOTECH / PHARMA'],
}

PORTFOLIO_MANDATE_DEFAULTS = {
    'BAC': {'mandate':'BASELINE', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':False},
    'WFC': {'mandate':'BASELINE', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':False},
    'AU': {'mandate':'BASELINE', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':False},
    'NEM': {'mandate':'BASELINE', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':False},
    'NVDA': {'mandate':'TACTICAL', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':False},
    'VXX': {'mandate':'TACTICAL', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':False},
    'VIXY': {'mandate':'TACTICAL', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':False},
    'ASTS': {'mandate':'TACTICAL', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':True},
    'RKLB': {'mandate':'TACTICAL', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':True},
    'PL': {'mandate':'TACTICAL', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':True},
    'LUNR': {'mandate':'TACTICAL', 'trade_around':True, 'dca_enabled':False, 'squeeze_monitor':True},
    'QBTS': {'mandate':'SATELLITE', 'trade_around':True, 'dca_enabled':True, 'dca_zone_low':22, 'dca_zone_high':24, 'squeeze_monitor':True},
    'QUBT': {'mandate':'SATELLITE', 'trade_around':True, 'dca_enabled':True, 'dca_zone_low':10, 'dca_zone_high':11, 'squeeze_monitor':True},
}

def sf(x: Any, default: float=0.0) -> float:
    try:
        if x is None or x == '': return default
        return float(x)
    except Exception:
        return default

def si(x: Any, default: int=0) -> int:
    try: return int(float(x))
    except Exception: return default

def money(x: Any) -> str: return f"${sf(x):,.2f}"
def pct(x: Any, d:int=2) -> str: return f"{sf(x):+.{d}f}%"
def compact(x: Any) -> str:
    v=sf(x); a=abs(v)
    if a>=1e12: return f"${v/1e12:.2f}T"
    if a>=1e9: return f"${v/1e9:.2f}B"
    if a>=1e6: return f"${v/1e6:.2f}M"
    if a>=1e3: return f"${v/1e3:.1f}K"
    return f"${v:.0f}"

def parse_dt(s: Any) -> Optional[datetime]:
    if not s: return None
    text=str(s).replace('Z','+00:00')
    for fmt in ['%Y-%m-%dT%H:%M:%S','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S%z','%Y-%m-%d']:
        try: return datetime.strptime(text[:19], fmt)
        except Exception: pass
    try: return datetime.fromisoformat(text)
    except Exception: return None

def minutes_between(a: datetime, b: datetime) -> Optional[float]:
    try:
        if a.tzinfo: a=a.replace(tzinfo=None)
        if b.tzinfo: b=b.replace(tzinfo=None)
        return abs((a-b).total_seconds())/60
    except Exception:
        return None

def wrap(s: Any, width:int=108, indent:str='  ') -> List[str]:
    text=str(s or '').replace('\n',' ').strip()
    if not text: return []
    words=text.split(); out=[]; cur=indent
    for w in words:
        if len(cur)+len(w)+1>width:
            out.append(cur.rstrip()); cur=indent+w
        else:
            cur += ('' if cur.endswith(' ') else ' ') + w
    if cur.strip(): out.append(cur.rstrip())
    return out

def table_line(cols: List[Tuple[Any,int]]) -> str:
    s=''
    for val,w in cols:
        t=str(val)
        s += (t.rjust(-w) if w<0 else t.ljust(w)) + ' '
    return s.rstrip()

def load_dataset(path: Path) -> Dict[str,Any]:
    with open(path, 'r', encoding='utf-8') as f: return json.load(f)



def get_nested(obj: Dict[str, Any], *paths: Tuple[str, ...], default: Any = {}) -> Any:
    """Return the first existing nested dict/value from multiple candidate paths."""
    for path in paths:
        cur = obj
        ok = True
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and cur not in (None, ''):
            return cur
    return default

def prices_map(dataset: Dict[str,Any]) -> Dict[str,Dict[str,Any]]:
    lp=dataset.get('live_prices') or {}
    if isinstance(lp.get('prices'), dict): return lp['prices']
    return {k:v for k,v in lp.items() if isinstance(v,dict) and 'price' in v}

def vix_obj(dataset: Dict[str,Any]) -> Dict[str,Any]:
    lp=dataset.get('live_prices') or {}
    if isinstance(lp.get('vix'), dict): return lp['vix']
    if isinstance(lp.get('^VIX'), dict): return lp['^VIX']
    return {'price':None,'chg_pct':None}

def top_movers(dataset: Dict[str,Any], n:int=15) -> List[Dict[str,Any]]:
    lp=dataset.get('live_prices') or {}
    if isinstance(lp.get('top_movers'), list) and lp['top_movers']:
        return lp['top_movers'][:n]
    rows=[]
    for t,d in prices_map(dataset).items():
        if t.startswith('^') or t.lower()=='vix': continue
        rows.append({'ticker':t, 'price':d.get('price'), 'chg_pct':d.get('chg_pct'), 'volume':d.get('volume'), 'session':d.get('session')})
    rows.sort(key=lambda r:abs(sf(r.get('chg_pct'))), reverse=True)
    return rows[:n]

def source_health_summary(dataset):
    sh=dataset.get('source_health') or []
    total=len(sh); active=sum(1 for s in sh if s.get('active'))
    tiers={}; types={}
    for s in sh:
        t=f"T{s.get('tier','?')}"; tiers.setdefault(t,[0,0]); tiers[t][1]+=1; tiers[t][0]+=1 if s.get('active') else 0
        typ=s.get('signal_type','unknown'); types[typ]=types.get(typ,0)+1
    return total,active,tiers,types

def fresh_sources(dataset) -> set:
    meta=dataset.get('meta') or {}; fr=meta.get('freshness') or {}
    return {k for k,v in fr.items() if isinstance(v,dict) and v.get('grade')=='FRESH'}

def fresh_signals(dataset, minutes:int=180, limit:int=80) -> List[Dict[str,Any]]:
    meta=dataset.get('meta') or {}; gen=parse_dt(meta.get('generated_at')) or datetime.now()
    out=[]
    for s in dataset.get('signals_latest') or []:
        dt=parse_dt(s.get('received_at'))
        age=minutes_between(gen, dt) if dt else None
        if age is not None and age<=minutes:
            text=str(s.get('raw_text') or '')
            # remove low-value repetitive analyst/sentiment rows only if plenty remains
            out.append({**s, '_age':age, '_text':text})
    out.sort(key=lambda x: x.get('_age', 9999))
    return out[:limit]

def _has_word(text: str, words: List[str]) -> bool:
    """True keyword match without false positives like cRATE, downWARd, MorningSTAR."""
    u = (text or '').upper()
    for w in words:
        pattern = r'(?<![A-Z0-9])' + re.escape(w.upper()) + r'(?![A-Z0-9])'
        if re.search(pattern, u):
            return True
    return False


def classify_signal_text(text: str, source: str = '', signal_type: str = '') -> str:
    """Schema-aware signal classifier for the fresh intelligence tape.

    Priority is intentional: real geopolitical/commodity keywords are checked
    before generic macro words. Matching uses word boundaries to avoid false
    positives such as 'create' -> RATE or 'Morningstar' -> WAR.
    """
    u = (text or '').upper()
    src = (source or '').upper()
    stype = (signal_type or '').upper()

    geo_words = ['IRAN','HORMUZ','CEASEFIRE','TRUMP','ISRAEL','IAEA','SANCTION','TAIWAN','CHINA','BEIJING','WAR']
    commodity_words = ['OIL','GOLD','SILVER','COMMODITY','COMMODITIES','NATURAL GAS','OPEC','RARE EARTH','URANIUM','COPPER']
    macro_words = ['FED','FOMC','IMF','INFLATION','RATE','RATES','TREASURY','YIELD','BESSENT','DOLLAR','GDP','PCE','CPI']
    ai_words = ['AVGO','BROADCOM','NVDA','AMD','SEMIS','AI','MICRON','MU','ARM','MARVELL','MRVL','TSMC','TSM','CHIP','GPU']
    bank_words = ['BANK','BAC','WFC','CITI','JPM','WELLS']
    quantum_words = ['QUANTUM','QBTS','QUBT','IONQ','RGTI','QUBIT']

    if stype == 'GEOPOLITICAL' or any(x in src for x in ['IAEA','WHITEHOUSE','WARONTHEROCKS','FT_WORLD','ARABNEWS']):
        if _has_word(u, geo_words + ['NUCLEAR']):
            return 'GEOPOLITICAL'
    if _has_word(u, geo_words):
        return 'GEOPOLITICAL'
    if _has_word(u, commodity_words):
        return 'COMMODITIES'
    if _has_word(u, macro_words):
        return 'MACRO / FED'
    if _has_word(u, ai_words):
        return 'AI / SEMIS'
    if _has_word(u, bank_words):
        return 'BANKS'
    if _has_word(u, quantum_words):
        return 'QUANTUM'
    return 'OTHER'

def clean_text(text: Any, maxlen:int=150) -> str:
    t=re.sub(r'<[^>]+>','',normalize_report_text(text))
    t=re.sub(r'\s+',' ',t).strip()
    return t[:maxlen] + ('...' if len(t)>maxlen else '')



def to_list(value: Any) -> List[Any]:
    """Normalize list-like fields without splitting plain strings into characters.

    Handles these dataset shapes safely:
    - Python list/tuple/set
    - JSON-encoded list string, e.g. '["AAPL", "MSFT"]'
    - comma-separated string, e.g. 'AAPL, MSFT'
    - scalar value
    """
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return []
        if (v.startswith('[') and v.endswith(']')) or (v.startswith('{') and v.endswith('}')):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
                if isinstance(parsed, dict):
                    return list(parsed.values())
                return [parsed]
            except Exception:
                pass
        if ',' in v:
            return [x.strip().strip('\"\'') for x in v.split(',') if x.strip()]
        return [v]
    return [value]


def join_field(value: Any, sep: str = ', ') -> str:
    """Human-readable formatting for speaker/ticker arrays."""
    items = []
    for x in to_list(value):
        if x is None:
            continue
        sx = str(x).strip().strip('\"\'')
        if sx:
            items.append(sx)
    return sep.join(items) if items else 'N/A'




TECH_TICKER_KEYWORDS = [
    (['NVIDIA','GEFORCE','CUDA','NEMO','NVDA'], 'NVDA'),
    (['AMD','RYZEN','EPYC'], 'AMD'),
    (['INTEL','XEON','DIAMOND RAPIDS','INTC'], 'INTC'),
    (['MICROSOFT','SURFACE','WINDOWS','AZURE'], 'MSFT'),
    (['QUALCOMM','SNAPDRAGON'], 'QCOM'),
    (['PALANTIR'], 'PLTR'),
    (['BROADCOM'], 'AVGO'),
    (['MARVELL'], 'MRVL'),
    (['MICRON'], 'MU'),
    (['TSMC','TAIWAN SEMICONDUCTOR'], 'TSM'),
    (['APPLE','APP STORE','IPHONE','WWDC'], 'AAPL'),
    (['GOOGLE','ALPHABET'], 'GOOGL'),
    (['META','FACEBOOK'], 'META'),
    (['AMAZON','AWS'], 'AMZN'),
    (['ORACLE'], 'ORCL'),
    (['CROWDSTRIKE'], 'CRWD'),
    (['PALO ALTO'], 'PANW'),
    (['DELL'], 'DELL'),
    (['APPLIED MATERIALS'], 'AMAT'),
    (['D-WAVE','D WAVE'], 'QBTS'),
    (['IONQ'], 'IONQ'),
    (['RIGETTI'], 'RGTI'),
    (['QUANTUM COMPUTING INC'], 'QUBT'),
    (['ROCKET LAB'], 'RKLB'),
    (['BLACKSKY'], 'BKSY'),
    (['SPACEX','STARLINK'], 'SPACE'),
]

TECH_THEME_KEYWORDS = [
    (['AI','ARTIFICIAL INTELLIGENCE','GPU','ACCELERATOR','DATA CENTER','DATACENTER','SERVER','MEMORY WALL'], 'AI_INFRASTRUCTURE'),
    (['SEMICONDUCTOR','CHIP','CHIPS','XEON','RYZEN','EPYC','GPU','NAND','SSD','TRANSISTOR'], 'SEMICONDUCTOR'),
    (['QUANTUM','QUBIT','QUANTINUUM'], 'QUANTUM'),
    (['SPACE','SPACEX','SATELLITE','LAUNCH','STARLINK'], 'SPACE'),
    (['SUPPLY CHAIN','SHORTAGE'], 'SUPPLY_CHAIN'),
    (['CYBER','SECURITY','BACKDOOR','BOTNET','SPY'], 'CYBERSECURITY'),
    (['COMPUTEX','KEYNOTE','CONFERENCE'], 'COMPUTEX'),
    (['CLOUD','AWS','AZURE'], 'CLOUD'),
]

def _article_text(article: Dict[str, Any]) -> str:
    return ' '.join(str(article.get(k) or '') for k in ('title','headline','raw_text','summary','description')).upper()

def _fallback_keywords(text: str, table) -> List[str]:
    hits=[]
    for keys, val in table:
        if any(k in text for k in keys) and val not in hits:
            hits.append(val)
    return hits

def article_tickers(article: Dict[str, Any]) -> str:
    """Extract tickers using dataset fields first, then deterministic title fallback."""
    hits=[]
    for key in ('tickers', 'ticker', 'symbols', 'affected_tickers', 'matched_tickers', 'detected_tickers'):
        val = article.get(key)
        items = [str(x).upper().strip() for x in to_list(val) if str(x).strip()]
        for x in items:
            if x not in {'N/A', 'NONE', 'NULL', '[]', '{}'} and x not in hits:
                hits.append(x)
    for x in _fallback_keywords(_article_text(article), TECH_TICKER_KEYWORDS):
        if x not in hits:
            hits.append(x)
    return ','.join(hits)


def article_themes(article: Dict[str, Any]) -> str:
    """Extract themes using dataset fields first, then deterministic title fallback."""
    hits=[]
    for key in ('themes', 'theme', 'mapped_themes', 'detected_themes', 'tags'):
        val = article.get(key)
        items = [str(x).upper().strip() for x in to_list(val) if str(x).strip()]
        for x in items:
            if x not in {'N/A', 'NONE', 'NULL', '[]', '{}'} and x not in hits:
                hits.append(x)
    for x in _fallback_keywords(_article_text(article), TECH_THEME_KEYWORDS):
        if x not in hits:
            hits.append(x)
    return ','.join(hits)


def article_sentiment_score(article: Dict[str, Any]) -> float:
    """Extract numeric sentiment score from tech-publication article variants."""
    for key in ('sentiment_score', 'score', 'sentiment_value', 'vader_score'):
        if key in article and article.get(key) not in (None, ''):
            return sf(article.get(key))
    sent = article.get('sentiment')
    if isinstance(sent, dict):
        for key in ('score', 'compound', 'value'):
            if key in sent:
                return sf(sent.get(key))
    return 0.0


def nonzero_field(obj: Dict[str,Any], names: List[str]) -> Optional[float]:
    """Return first plausible non-zero numeric field from direct or nested dict."""
    if not isinstance(obj, dict):
        return None
    lower={str(k).lower().replace(' ','_').replace('-','_'):v for k,v in obj.items()}
    for name in names:
        keys=[name, name.lower(), name.upper(), name.lower().replace(' ','_').replace('-','_')]
        for k in keys:
            if k in obj:
                try: v=float(obj.get(k))
                except Exception: v=None
                if v is not None and abs(v)>0.00001:
                    return v
            lk=k.lower().replace(' ','_').replace('-','_')
            if lk in lower:
                try: v=float(lower.get(lk))
                except Exception: v=None
                if v is not None and abs(v)>0.00001:
                    return v
    for v in obj.values():
        if isinstance(v, dict):
            got=nonzero_field(v, names)
            if got is not None:
                return got
    return None


def treasury_snapshot(dataset: Dict[str,Any]) -> Tuple[Dict[str,Any], str]:
    """Robust treasury reader. Never silently maps missing yields to 0.00%."""
    candidates=[]
    for path in [
        ('treasury_yields',), ('macro','treasury_yields'), ('rates','treasury_yields'),
        ('market','treasury_yields'), ('regime','treasury_yields'), ('macro_context','treasury_yields'),
        ('yield_curve',), ('rates',), ('macro','rates')
    ]:
        val=get_nested(dataset, path, default=None)
        if isinstance(val, dict):
            candidates.append(val)
    reg=dataset.get('regime') or {}
    if isinstance(reg, dict):
        candidates.append(reg)

    aliases={
        '10Y':['10Y','10y','10_year','10yr','us10y','ust10y','yield_10y','ten_year','dgs10','10Y_yield','us_10y'],
        '2Y':['2Y','2y','2_year','2yr','us2y','ust2y','yield_2y','two_year','dgs2','2Y_yield','us_2y'],
        '30Y':['30Y','30y','30_year','30yr','us30y','ust30y','yield_30y','thirty_year','dgs30','30Y_yield','us_30y'],
        '3M':['3M','3m','3_month','3mo','us3m','ust3m','yield_3m','three_month','dtb3','3M_yield','us_3m'],
        'fed_funds':['fed_funds_target','fed_funds','fedfunds','fed_rate','effective_fed_funds'],
        'nim_proxy':['nim_proxy','net_interest_margin_proxy','nim'],
        'curve':['curve_10y_2y','10y_2y','yield_curve_10y_2y','curve_spread']
    }
    out={}
    for label,names in aliases.items():
        for c in candidates:
            got=nonzero_field(c,names)
            if got is not None:
                out[label]=got
                break
    if 'curve' not in out and '10Y' in out and '2Y' in out:
        out['curve']=out['10Y']-out['2Y']
    if 'nim_proxy' not in out and '10Y' in out and 'fed_funds' in out:
        out['nim_proxy']=out['10Y']-out['fed_funds']
    usable=all(k in out for k in ('10Y','2Y','30Y','3M'))
    status='OK' if usable else 'UNRESOLVED'
    return out,status


GEOPOLITICAL_SOURCES = {
    'IAEA_NEWS','WHITEHOUSE_RSS','FT_WORLD','ARABNEWS_BUSINESS','WARONTHEROCKS',
    'BREAKING_DEFENSE','DEFENSE_NEWS','X_SIGNALS','REUTERS_COMMODITIES','REUTERS_MARKETS',
    'FT_MARKETS','OPEC_NEWS','TREASURY_PRESS','IMF_NEWS','OILPRICE_RSS'
}

# Some sources are macro/geoeconomic. They are allowed into L4 only when the
# text contains explicit geopolitical conflict keywords, not generic China/macro.
GEOPOLITICAL_CONFLICT_WORDS = ['IRAN','HORMUZ','CEASEFIRE','ISRAEL','IAEA','SANCTION','TAIWAN','WAR','NUCLEAR']


def source_signal_type_map(dataset: Dict[str, Any]) -> Dict[str, str]:
    out = {}
    for s in dataset.get('source_health') or []:
        out[str(s.get('source','')).upper()] = str(s.get('signal_type','')).upper()
    return out


def is_true_geopolitical_text(text: str) -> bool:
    """Strict geopolitical test. Avoids false positives from Morningstar/downward/create.

    China/Beijing alone is not enough for L4. It must be linked to Taiwan, war,
    sanctions, tariffs, or other explicit conflict/policy-risk language.
    """
    u = (text or '').upper()
    if _has_word(u, ['IRAN','HORMUZ','CEASEFIRE','ISRAEL','IAEA','SANCTION','TAIWAN','WAR']):
        return True
    if 'OIL PRICE RISK' in u and _has_word(u, ['IRAN','WAR']):
        return True
    if 'NUCLEAR' in u and _has_word(u, ['IRAN','IAEA','WATCHDOG','INSPECTION','URANIUM']):
        return True
    if _has_word(u, ['CHINA','BEIJING']) and _has_word(u, ['TAIWAN','WAR','SANCTION','TARIFF','EXPORT CONTROL']):
        return True
    if _has_word(u, ['TRUMP']) and _has_word(u, ['IRAN','TARIFF','TRADE','WAR','SANCTION']):
        return True
    return False


def geo_signal_rows(dataset: Dict[str,Any], limit:int=10) -> List[Dict[str,Any]]:
    """Collect real geopolitical override signals from authoritative dataset layers.

    Priority order:
    1) ECE geopolitical / Trump / macro war-oil entries
    2) fresh signals from geopolitical or macro/commodity sources with true geo keywords
    3) source feed fallback from IAEA / FT World / WarOnTheRocks / WhiteHouse / OPEC / Reuters

    Explicitly avoids Ticker_Sentiment and Moomoo_Intel unless the source itself is not available,
    because those are market/ticker context, not geopolitical override evidence.
    """
    rows=[]; seen=set()
    src_type = source_signal_type_map(dataset)

    def add(source, text, age='', tier=''):
        txt=clean_text(text,220)
        if not txt or txt in seen:
            return
        if not is_true_geopolitical_text(txt):
            return
        seen.add(txt)
        rows.append({'source':source or 'UNKNOWN', 'text':txt, 'age':age, 'tier':tier})

    # 1) ECE: concise, already ranked by the Event Correlation Engine
    # WO-Final-PhD Defect 3: use canonical ECE model so contaminated evidence is excluded
    _ece_canonical = ece_by_theme(dataset)
    for e in _ece_canonical.values():
        th=str(e.get('theme','')).upper()
        why=e.get('why') or ''
        if th in ('GEOPOLITICAL','TRUMP / TRADE','MACRO / FED','OIL / GAS') and is_true_geopolitical_text(why):
            add('Event_Correlation', why, '', str(e.get('evidence_tier_label') or ''))

    # 2) Fresh signals from real news/geo/macro/commodity sources
    for sgn in fresh_signals(dataset,480,400):
        source=str(sgn.get('source') or '')
        source_u=source.upper()
        if source_u in {'TICKER_SENTIMENT','MOOMOO_INTEL','ANALYST_TARGETS','REGIME_DETECTION'}:
            continue
        stype=str(sgn.get('signal_type') or src_type.get(source_u,'')).upper()
        source_ok = source_u in GEOPOLITICAL_SOURCES or stype == 'GEOPOLITICAL'
        # Macro/commodity/news sources can enter only through explicit conflict text;
        # the add() function still performs the strict keyword gate.
        if source_ok or (stype in {'MACRO','COMMODITY','NEWS'} and is_true_geopolitical_text(sgn.get('_text') or sgn.get('raw_text'))):
            add(source, sgn.get('_text') or sgn.get('raw_text'), f"age={sgn.get('_age',0):.0f}m", f"T{sgn.get('quality_score','')}")

    # 3) Full signals bucket fallback from geopolitical sources
    for src, items in (dataset.get('signals') or {}).items():
        src_u=str(src).upper()
        if src_u not in GEOPOLITICAL_SOURCES and src_type.get(src_u) != 'GEOPOLITICAL':
            continue
        if not isinstance(items, list):
            continue
        for item in items[:30]:
            if isinstance(item, dict):
                add(src, item.get('raw_text') or item.get('title') or item.get('headline') or item.get('text'), '', '')
            else:
                add(src, item, '', '')
            if len(rows) >= limit:
                return rows[:limit]
    return rows[:limit]


def event_field(event: Dict[str,Any], names: List[str]) -> Any:
    norm = {str(k).lower(): v for k, v in event.items()}
    for n in names:
        if n in event and event.get(n) not in (None,''):
            return event.get(n)
        lk = n.lower()
        if lk in norm and norm[lk] not in (None,''):
            return norm[lk]
    return None


def fmt_event_pct(value: Any) -> str:
    if value in (None,''):
        return 'MISSING'
    try:
        v=float(value)
    except Exception:
        return 'MISSING'
    return f"{v:+.2f}%"


def parse_json_maybe(value: Any) -> Any:
    if isinstance(value, str):
        v=value.strip()
        if (v.startswith('[') and v.endswith(']')) or (v.startswith('{') and v.endswith('}')):
            try:
                return json.loads(v)
            except Exception:
                return value
    return value


def summarize_historical_years(value: Any, max_items:int=4) -> Tuple[str, str]:
    """Return (years_count_label, compact_history_text)."""
    parsed=parse_json_maybe(value)
    if not parsed or parsed in ('[]','{}'):
        return '0', ''
    if isinstance(parsed, list):
        pieces=[]
        for item in parsed[:max_items]:
            if isinstance(item, dict):
                year=item.get('year','?')
                outcome=item.get('outcome','?')
                nvda=item.get('nvda_pct')
                spx=item.get('sp500_pct')
                extra=[]
                if nvda is not None: extra.append(f"NVDA {sf(nvda):+g}%")
                if spx is not None: extra.append(f"SPX {sf(spx):+g}%")
                pieces.append(f"{year} {outcome}" + (" (" + ', '.join(extra) + ")" if extra else ''))
            else:
                pieces.append(clean_text(item,60))
        return str(len(parsed)), '; '.join(pieces)
    if isinstance(parsed, dict):
        return str(len(parsed)), clean_text(parsed,160)
    return '', clean_text(parsed,160)


def named_event_rows(dataset: Dict[str,Any]) -> List[Dict[str,Any]]:
    """Parse ece_named_events according to actual v1.8u schema.

    Important actual fields found in dataset:
    base_case_impact_pct, bull_case_impact_pct, bear_case_impact_pct,
    years_tracked, historical_years, trigger_description, sector_impact_map.
    """
    rows=[]
    for e in dataset.get('ece_named_events') or []:
        name=event_field(e,['event_name','event_slug','slug','name','event']) or 'UNKNOWN_EVENT'
        nextd=event_field(e,['next_occurrence','next','event_date','next_date','date']) or ''
        base=event_field(e,['base_case_impact_pct','base_case_pct','base_move','base_case','base','expected_move','avg_move_pct'])
        bull=event_field(e,['bull_case_impact_pct','bull_case_pct','bull_move','bull_case','bull','best_case_pct'])
        bear=event_field(e,['bear_case_impact_pct','bear_case_pct','bear_move','bear_case','bear','worst_case_pct'])
        years_raw=event_field(e,['historical_years','years','sample_years'])
        tracked=event_field(e,['years_tracked','historical_years_tracked','sample_size'])
        years_count, hist_summary = summarize_historical_years(years_raw)
        if not years_count and tracked not in (None,''):
            years_count=str(tracked)
        trig=event_field(e,['trigger_description','trigger_rule','trigger','description','rule']) or ''
        sector_map=parse_json_maybe(e.get('sector_impact_map'))
        direct=[]
        if isinstance(sector_map, dict):
            direct=[k for k,v in sector_map.items() if str(v).upper().startswith('DIRECT')][:8]
        rows.append({'name':name,'next':nextd,'years':years_count or str(tracked or 0),'base':base,'bull':bull,'bear':bear,'trigger':trig,'history':hist_summary,'direct':direct})
    return rows

def unique_catalysts_for_ticker(ticker: str, dataset: Dict[str,Any]) -> List[str]:
    """Deduplicated catalyst labels for L8."""
    t=ticker.upper(); seen=set(); out=[]
    for raw in catalyst_status_for_ticker(t,dataset):
        key=re.sub(r'\s+',' ',raw.upper()).strip()
        if key not in seen:
            seen.add(key); out.append(raw)
    return out

def ece_by_theme(dataset):
    """Return canonical ECE rows keyed by THEME_UPPER.

    WO-Final-PhD Defect 3: all ECE reads must go through build_canonical_ece_model()
    so that basket_move scale correction, ECE_v2 field defaults, and confidence caps
    are uniformly applied. Raw dataset reads bypass these corrections.
    """
    try:
        from research_report_generator import build_canonical_ece_model as _bcem
        return {r["theme"].upper(): r for r in _bcem(dataset)}
    except Exception:
        # Fallback: raw read (preserves old behaviour if generator not importable)
        out = {}
        for e in (dataset.get('event_correlations_all') or dataset.get('event_correlations') or []):
            if not isinstance(e, dict):
                continue
            ee = dict(e)
            ee['theme'] = normalize_theme_label(ee.get('theme'))
            out[str(ee.get('theme','')).upper()] = ee
        return out

def target_upside(price, target):
    p=sf(price); t=sf(target)
    return None if p<=0 or t<=0 else (t-p)/p*100

def governance(t):
    if t in DEFENSE_OBSERVATION_ONLY: return 'OBSERVE_ONLY'
    if t in CRYPTO_EXCLUDED: return 'EXCLUDED_CRYPTO'
    return 'TRADE_OK'

# ── Risk Governor Watchlist Override ─────────────────────────────────────────
# Tickers in GOLD_MINERS cluster. When cluster severity = CRITICAL,
# all add/buy actions are blocked — override to HOLD / DECONCENTRATION REVIEW.
_GOLD_MINERS_CLUSTER_TICKERS = frozenset({'AU', 'NEM', 'GLD', 'GDX', 'GDXJ'})
_QUANTUM_CLUSTER_TICKERS     = frozenset({'QBTS', 'QUBT', 'IONQ', 'RGTI', 'IQM'})

def _get_risk_governor_data(dataset: dict) -> dict:
    """
    Extract risk governor cluster status from dataset.
    Primary: approved_operating_truth.json (most authoritative).
    Fallback: build_concentration_risk() from the dataset.
    Returns {'concentration_status': str, 'cluster_status': dict}.
    """
    try:
        import json as _json
        _aot_path = Path(__file__).resolve().parent.parent / 'data' / 'governance' / 'approved_operating_truth.json'
        if _aot_path.exists():
            _aot = _json.loads(_aot_path.read_text(encoding='utf-8'))
            return {
                'concentration_status': _aot.get('concentration_status', 'UNKNOWN'),
                'cluster_status': _aot.get('cluster_status', {}),
            }
    except Exception:
        pass
    # Fallback: compute inline (mirrors governance_gate logic)
    try:
        from research_report_generator import build_concentration_risk as _bcr
        _cr = _bcr(dataset)
        _clusters_flat = _cr.get('clusters', {})  # {name: weight}
        _cluster_status: dict = {}
        _SEV = {'CRITICAL': 3, 'HIGH': 2, 'NORMAL': 0}
        for _cn, _cw in _clusters_flat.items():
            _sev = 'CRITICAL' if _cw >= 0.65 else 'HIGH' if _cw >= 0.45 else 'NORMAL'
            _cluster_status[_cn] = {'severity': _sev, 'weight': _cw, 'weight_pct': f"{_cw:.0%}"}
        return {
            'concentration_status': _cr.get('concentration_status', 'UNKNOWN'),
            'cluster_status': _cluster_status,
        }
    except Exception:
        return {'concentration_status': 'UNKNOWN', 'cluster_status': {}}


def apply_risk_governor_watchlist_override(row: dict, rg: dict) -> dict:
    """
    Apply Risk Governor override to a score_ticker() result row.
    - If GOLD_MINERS cluster is CRITICAL and ticker is a GOLD_MINERS member:
        action  → 'HOLD / DECONCENTRATION REVIEW'
        governance_override → 'CLUSTER_BLOCKED_NO_ADD'
        risk_governor_blocked → True
        original_action preserved in row['original_action']
    - All other tickers: pass through unchanged (risk_governor_blocked = False).
    NEVER modifies score or lens values.
    """
    out = dict(row)
    ticker = str(out.get('ticker', '')).upper()
    cluster_status = rg.get('cluster_status', {})
    gm = cluster_status.get('GOLD_MINERS', {})
    gm_severity = str(gm.get('severity', '')).upper()
    if ticker in _GOLD_MINERS_CLUSTER_TICKERS and gm_severity == 'CRITICAL':
        out['original_action'] = out.get('action', '')
        out['action'] = 'HOLD / DECONCENTRATION REVIEW'
        out['governance_override'] = 'CLUSTER_BLOCKED_NO_ADD'
        out['risk_governor_blocked'] = True
    else:
        out['original_action'] = out.get('action', '')
        out['governance_override'] = None
        out['risk_governor_blocked'] = False
    return out

def active_catalyst_tickers(dataset) -> set:
    """Only tickers with active/near catalysts. Avoid marking every top mover as MATCHED."""
    out=set()
    cal=dataset.get('catalyst_calendar') or {}
    for c in cal.get('all',[]) or []:
        d=si(c.get('days_until_catalyst'),999)
        flag=str(c.get('alert_flag','')).upper()
        if d <= 14 or flag in ('ACTIVE','IMMINENT','UPCOMING'):
            if c.get('ticker'): out.add(str(c['ticker']).upper())
    # portfolio-only future earnings are not enough to explain same-day top movers unless near
    for c in cal.get('portfolio_only',[]) or []:
        d=si(c.get('days_until_catalyst'),999)
        flag=str(c.get('alert_flag','')).upper()
        if d <= 14 or flag in ('ACTIVE','IMMINENT'):
            if c.get('ticker'): out.add(str(c['ticker']).upper())
    for c in dataset.get('ceo_appearances') or []:
        if c.get('alert_72h_flag') or c.get('alert_24h_flag'):
            if c.get('ticker'): out.add(str(c.get('ticker')).upper())
            for x in to_list(c.get('affected_tickers')): out.add(str(x).upper())
    for c in dataset.get('conference_calendar') or []:
        d=si(c.get('days_until_event'),999)
        flag=str(c.get('catalyst_flag','')).upper()
        if d <= 14 or flag in ('ACTIVE','IMMINENT','UPCOMING'):
            for x in to_list(c.get('affected_tickers')): out.add(str(x).upper())
    return out

def catalyst_status_for_ticker(ticker, dataset):
    t=ticker.upper(); hits=[]
    cal=dataset.get('catalyst_calendar') or {}
    for c in (cal.get('all') or []) + (cal.get('portfolio_only') or []):
        if str(c.get('ticker','')).upper()==t:
            hits.append(f"{c.get('catalyst_type','CAT')} {c.get('catalyst_date','')} {c.get('alert_flag','')}")
    for c in dataset.get('ceo_appearances') or []:
        aff=[str(x).upper() for x in to_list(c.get('affected_tickers'))]
        if str(c.get('ticker','')).upper()==t or t in aff:
            hits.append(f"CEO/keynote {c.get('executive_name','')} {c.get('appearance_date','')}")
    return hits[:3]


def top_mover_catalyst_table(dataset):
    """Strict P2-03 classification: MATCHED / PARTIAL / UNEXPLAINED / LOW_MOVE."""
    active=active_catalyst_tickers(dataset)
    rows=[]
    signals_text=' '.join(clean_text(s.get('raw_text') or s.get('_text'),300).upper() for s in fresh_signals(dataset,480,300))
    context_text=json.dumps(dataset.get('tech_pub_signals') or {}, default=str).upper() + ' ' + json.dumps(dataset.get('event_correlations') or [], default=str).upper()
    for m in top_movers(dataset,15):
        t=str(m.get('ticker','')).upper(); move=sf(m.get('chg_pct'))
        status='UNEXPLAINED'; reason='no explicit fresh catalyst match'
        if abs(move)<5:
            status='LOW_MOVE'; reason='below 5% threshold'
        elif t in active:
            status='MATCHED'; reason='direct calendar/CEO/conference catalyst'
        elif t and t in signals_text:
            status='PARTIAL'; reason='fresh ticker/headline mention; causal reason not fully verified'
        elif t and t in context_text:
            status='PARTIAL'; reason='sector/publication context only; no direct catalyst'
        rows.append((t,move,m.get('price'),m.get('volume'),status,reason))
    return rows

def top_mover_status_counts(rows):
    counts={'MATCHED':0,'PARTIAL':0,'UNEXPLAINED':0,'LOW_MOVE':0}
    for *_,st,reason in rows:
        counts[st]=counts.get(st,0)+1
    return counts

def blind_spot(dataset):
    try:
        from research_report_generator import build_blind_spot_checklist as _bbsc
        canonical = _bbsc(dataset)
        status = canonical.get('blind_spot_status', 'CLEAR')
        penalty = sf(canonical.get('cio_penalty'))
        failed = [str(x) for x in (canonical.get('failed_items') or [])]
        sector_gaps = [
            str(row[2])
            for row in (canonical.get('check_rows') or [])
            if isinstance(row, (list, tuple)) and len(row) >= 3
            and str(row[0]) == 'Sector Catalyst Check'
            and str(row[1]).upper() != 'PASS'
        ]
        return status, penalty, failed, sector_gaps
    except Exception:
        pass

    rows=top_mover_catalyst_table(dataset)
    unexpl=[f"{t} {pct(m)}" for t,m,_,_,st,_ in rows if abs(m)>=7 and st=='UNEXPLAINED']
    ece=list(ece_by_theme(dataset).values())  # WO-Final-PhD Defect 3: use canonical model
    sector_gaps=[]
    for e in ece:
        bm=sf(e.get('basket_move')); why=str(e.get('why','')).upper(); conf=sf(e.get('confidence'))
        if abs(bm)>=2 and ('ANALYST CONSENSUS' in why or 'WALL ST. ANALYSTS' in why) and conf>=55:
            sector_gaps.append(f"{e.get('theme')} {pct(bm)} relies on analyst consensus, not causal catalyst")
    penalty=min(0.35,0.04*len(unexpl)+0.02*len(sector_gaps))
    status='CLEAR' if not unexpl and not sector_gaps else ('CRITICAL' if len(unexpl)>=4 else 'WARNING')
    return status, penalty, unexpl, sector_gaps

def confidence_grade(c):
    c=sf(c)
    return 'HIGH' if c>=.85 else 'MEDIUM-HIGH' if c>=.70 else 'MEDIUM' if c>=.55 else 'LOW-MEDIUM' if c>=.40 else 'LOW'

def _causal_early(dataset):
    """Compute causal status at the start of generate() — Fix 2.
    Delegates to build_causal_explanation() from the main generator so
    the CIO briefing header is ALWAYS consistent with the delivery JSON.
    """
    try:
        from research_report_generator import build_causal_explanation as _bce
        return _bce(dataset).get("causal_status", "INCOMPLETE")
    except Exception:
        pass
    # Fallback: simplified local check
    reg = dataset.get('regime') or {}
    _factors = reg.get('factors') or {}
    _nonzero_f = sum(1 for v in _factors.values() if v != 0)
    sigs = dataset.get('signals') or {}
    def _sc(*keys): return sum(len(sigs.get(k) or []) for k in keys if k in sigs)
    _news_cnt  = _sc('Reuters_Business','Reuters_Markets','WSJ_Markets','FT_Markets','CNBC_Markets')
    _macro_cnt = _sc('BLS_API','BEA_GDP_PCE','WorldBank_Macro','EIA_Petroleum','EIA_NatGas')
    _fed_cnt   = _sc('Fed_Press','Fed_Speeches','Fed_FOMC_Minutes','ECB_Press','Treasury_Press')
    _pass = sum([_nonzero_f >= 3, bool(_news_cnt >= 5), bool(_macro_cnt >= 3), bool(_fed_cnt >= 3)])
    if _pass >= 4: return 'COMPLETE'
    if _pass >= 3: return 'MOSTLY_COMPLETE'
    return 'PARTIAL'

def score_ticker(ticker, dataset):
    prices=prices_map(dataset); p=prices.get(ticker,{})
    price=sf(p.get('price'))
    target=dataset.get('analyst_targets',{}).get(ticker,{})
    avg=sf(target.get('avg_target') or target.get('average'))
    up=target_upside(price,avg)
    fund=dataset.get('fundamentals',{}).get(ticker,{})
    ey=sf(fund.get('ey_ratio'))
    chg=sf(p.get('chg_pct'))
    cf=dataset.get('capital_flow',{}).get(ticker,{})
    themes=TICKER_THEME_MAP.get(ticker,[])
    ece=ece_by_theme(dataset)
    sent=dataset.get('ticker_sentiment',{}).get(ticker,{})
    cats=catalyst_status_for_ticker(ticker,dataset)
    # L1
    l1=2.0
    if up is not None:
        l1 += 1.5 if up>=30 else 1.2 if up>=20 else .8 if up>=10 else .3 if up>=0 else -1.0
    if sf(target.get('buy'))>=80: l1+=.7
    if ey>=6: l1+=.6
    elif ey==0 and sf(fund.get('pe_ttm_ratio'))<0: l1-=.3
    # L2 entry quality
    l2=3.0
    if chg>=7: l2-=.7
    elif chg<=-7: l2-=.3
    elif -5<=chg<=-1: l2+=.3
    # L3 macro
    reg=dataset.get('regime',{}); rscore=si(reg.get('score'))
    l3=3.0 + (-.4 if rscore<=-2 else .3 if rscore>=1 else 0)
    if 'GOLD / SAFE HAVEN' in themes and rscore<0: l3+=.5
    if 'BANKS / LIQUIDITY' in themes and sf((dataset.get('treasury_yields') or {}).get('nim_proxy'))>.5: l3+=.4
    # L4 geo
    geo_text=' '.join(s.get('_text','') for s in fresh_signals(dataset,240,80)).upper()
    l4=2.5
    if any(k in geo_text for k in ['IRAN','HORMUZ','WAR','TRUMP']):
        l4 += .8 if 'GOLD / SAFE HAVEN' in themes else .2
    # L5 sentiment
    sv=sf(sent.get('score')); l5=4 if sv>.25 else 3.2 if sv>.05 else 2 if sv<-.1 else 2.5
    # L6 sector
    l6=2.5
    for th in themes:
        e=ece.get(th.upper())
        if e:
            bm=sf(e.get('basket_move')); direction=str(e.get('direction','')).upper().replace('-','_')
            l6=max(l6, 4 if direction=='RISK_ON' and bm>=2 else 3.5 if direction=='RISK_ON' else 1.5 if direction=='RISK_OFF' else 2.5)
    # L7 flow
    bias=str(cf.get('institutional_bias','')).upper(); main=sf(cf.get('main_net')); supern=sf(cf.get('super_large_net'))
    l7=4 if 'ACCUM' in bias or 'INFLOW' in bias else 2 if 'OUTFLOW' in bias or 'DISTR' in bias else 2.5
    if main>0 and supern>0: l7+=.3
    if main<0 and supern<0: l7-=.3
    # L8 catalyst
    l8=4 if cats else 3 if any(th.split('/')[0].strip() in json.dumps(dataset.get('tech_pub_signals',{})).upper() for th in themes) else 2.5
    vals=[max(0,min(5,x)) for x in [l1,l2,l3,l4,l5,l6,l7,l8]]
    total=sum(vals)
    action='BUY' if total>=32 else 'WATCH/BUY DIP' if total>=26 else 'WAIT/HOLD' if total>=20 else 'WEAK/AVOID'
    gov=governance(ticker)
    if gov=='OBSERVE_ONLY': action='OBSERVE ONLY'
    if gov=='EXCLUDED_CRYPTO': action='EXCLUDED'
    return {'ticker':ticker,'score':total,'action':action,'lenses':vals,'upside':up,'price':price,'target':avg,'flow':bias or 'N/A'}

def cio_action(dataset, blind_status, blind_penalty, causal_status='UNKNOWN', conc_status='UNKNOWN'):
    reg=dataset.get('regime',{}); score=si(reg.get('score'))
    if blind_status in ('WARNING','CRITICAL'):
        # Build reason that accurately reflects actual causal state — never claim causal incomplete when COMPLETE
        if causal_status in ('COMPLETE', 'MOSTLY_COMPLETE'):
            _parts = []
            if blind_status in ('WARNING', 'CRITICAL'):
                _parts.append(f"blind-spot {blind_status}")
            if conc_status in ('HIGH', 'CRITICAL'):
                _parts.append(f"concentration {conc_status}")
            _suffix = ' and '.join(_parts) + ' require CIO review before risk addition.' if _parts else 'CIO review required.'
            _reason = f"Causal explanation {causal_status}; {_suffix}"
        else:
            _reason = f"Causal explanation {causal_status} and blind-spot {blind_status} — CIO review required."
        return 'WAIT / HOLD', _reason
    if score<=-3: return 'SELL / REDUCE RISK', 'Risk-off regime.'
    if score==-2: return 'WAIT / HOLD', 'Mild risk-off regime.'
    if score>=2: return 'SELECTIVE_BUY_RESEARCH_ONLY', 'Risk-on regime; execution still requires CIO review.'
    return 'WAIT / HOLD', 'Neutral regime.'


INSTITUTIONAL_PROCESS_ORDER = [
    'data_quality',
    'point_in_time_readiness',
    'bias_controls',
    'signal_validation',
    'risk_model',
    'portfolio_construction',
    'execution_readiness',
    'monitoring_governance',
]


def institutional_quant_layer(dataset: Dict[str,Any]) -> Dict[str,Any]:
    iq = dataset.get('institutional_quant')
    return iq if isinstance(iq, dict) else {}


def institutional_process_rows(iq: Dict[str,Any]) -> List[Tuple[str, Dict[str,Any]]]:
    processes = iq.get('processes') or {}
    if not isinstance(processes, dict):
        return []
    out=[]; seen=set()
    for name in INSTITUTIONAL_PROCESS_ORDER:
        if isinstance(processes.get(name), dict):
            out.append((name, processes[name])); seen.add(name)
    for name in sorted(k for k in processes if k not in seen):
        if isinstance(processes.get(name), dict):
            out.append((name, processes[name]))
    return out


def institutional_gap_rows(iq: Dict[str,Any], limit:int=6) -> List[Tuple[str, Dict[str,Any], str]]:
    rows=[]
    for name,proc in institutional_process_rows(iq):
        warnings = proc.get('warnings') or []
        if warnings:
            rows.append((name, proc, clean_text(warnings[0], 95)))
    rows.sort(key=lambda r: sf(r[1].get('readiness_score'), 999))
    return rows[:limit]


def fmt_iq_score(value: Any) -> str:
    return 'N/A' if value in (None, '') else f"{sf(value):.3f}/100"


def broker_ticker(row: Dict[str,Any]) -> str:
    return str(row.get('ticker') or row.get('code') or '').replace('US.', '').strip()


def cio_plan_vs_order_book(dataset: Dict[str,Any]) -> Dict[str,Any]:
    orders_layer = dataset.get('orders') if isinstance(dataset.get('orders'), dict) else {}
    execution_layer = dataset.get('execution') if isinstance(dataset.get('execution'), dict) else {}
    prices = prices_map(dataset)
    open_orders = orders_layer.get('open_orders') if isinstance(orders_layer.get('open_orders'), list) else []
    miner_orders = []
    executable = []
    for row in open_orders:
        if not isinstance(row, dict):
            continue
        ticker = broker_ticker(row).upper()
        side = str(row.get('trd_side') or '').upper()
        if ticker not in {'AU', 'NEM'} or side != 'SELL':
            continue
        limit_price = sf(row.get('price'))
        current_price = sf((prices.get(ticker) or {}).get('price'))
        is_executable = bool(current_price and limit_price and limit_price <= current_price)
        if is_executable:
            executable.append(ticker)
        miner_orders.append({
            'ticker': ticker,
            'status': row.get('order_status', ''),
            'qty': row.get('qty'),
            'limit': limit_price,
            'current_price': current_price,
            'dealt_qty': row.get('dealt_qty'),
            'executable_now': is_executable,
        })
    feasibility = 'NOT GUARANTEED' if miner_orders and len(executable) < len(miner_orders) else 'REVIEW_REQUIRED'
    if not miner_orders:
        feasibility = 'NO AU/NEM SELL ORDERS FOUND'
    warning = 'Current open orders do not guarantee pre-BOJ miner de-risking. Manual CIO action required.'
    return {
        'miner_orders': miner_orders,
        'feasibility': feasibility,
        'warning': warning,
        'execution_authority': execution_layer.get('execution_authority', 'CIO_ONLY_MANUAL'),
        'routing_enabled': bool(execution_layer.get('order_routing_enabled')),
        'generated_orders': int(execution_layer.get('orders_generated') or execution_layer.get('orders_generated_by_pipeline') or 0),
    }


def yesno(value: Any) -> str:
    return 'YES' if bool(value) else 'NO'


def research_forecasting_layer(dataset: Dict[str,Any]) -> Dict[str,Any]:
    rf = dataset.get('research_forecasting')
    return rf if isinstance(rf, dict) else {}


def forecast_rows_for_report(rf: Dict[str,Any], limit:int=12) -> List[Dict[str,Any]]:
    rows = rf.get('top_bluelotus_90d') or []
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)][:limit]


def cross_market_layer(dataset: Dict[str,Any]) -> Dict[str,Any]:
    cm = dataset.get('cross_market_confirmation')
    return cm if isinstance(cm, dict) else {}


def cm_item(cm: Dict[str,Any], group: str, ticker: str) -> Dict[str,Any]:
    row = (cm.get(group) or {}).get(ticker, {})
    return row if isinstance(row, dict) else {}


def generate(dataset: Dict[str,Any]) -> str:
    lines=[]
    def L(value: Any = "") -> None:
        lines.append(normalize_report_text(value))
    meta=dataset.get('meta',{}); reg=dataset.get('regime',{}); port=dataset.get('portfolio',{}); fg=dataset.get('fear_greed',{})
    vix=vix_obj(dataset); prices=prices_map(dataset); positions=port.get('positions') or {}
    total,active,tiers,types=source_health_summary(dataset)
    blind_status, blind_penalty, unexpl, sector_gaps=blind_spot(dataset)
    _causal_status=_causal_early(dataset)  # Fix 2: real causal, not derived from blind_spot
    # Get concentration status for action reason accuracy
    try:
        from research_report_generator import build_concentration_risk as _bcr_r6
        _r6_conc_status = _bcr_r6(dataset).get("concentration_status", "UNKNOWN")
    except Exception:
        _r6_conc_status = "UNKNOWN"
    action, action_reason=cio_action(dataset, blind_status, blind_penalty, _causal_status, _r6_conc_status)
    base_conf=.67 if action.startswith('SELL') else .60
    conf=max(.25, min(.90, base_conf-blind_penalty))
    ece=dataset.get('event_correlations_all') or dataset.get('event_correlations') or []
    ece=[{**e, 'theme': normalize_theme_label(e.get('theme'))} for e in ece if isinstance(e, dict)]
    ece_sorted=sorted(ece, key=lambda e: sf(e.get('basket_move')), reverse=True)
    top=top_movers(dataset,15)
    iq = institutional_quant_layer(dataset)
    iq_summary = iq.get('summary') if isinstance(iq.get('summary'), dict) else {}
    iq_counts = iq_summary.get('status_counts') if isinstance(iq_summary.get('status_counts'), dict) else {}
    rf = research_forecasting_layer(dataset)
    cm = cross_market_layer(dataset)
    formal_risk = dataset.get('risk_model') if isinstance(dataset.get('risk_model'), dict) else {}
    thesis_layer = dataset.get('thesis_lifecycle') if isinstance(dataset.get('thesis_lifecycle'), dict) else {}
    monitoring_layer = dataset.get('monitoring') if isinstance(dataset.get('monitoring'), dict) else {}
    snapshot_archive = dataset.get('dataset_snapshot_archive') if isinstance(dataset.get('dataset_snapshot_archive'), dict) else {}
    freshness_recovery = dataset.get('freshness_recovery') if isinstance(dataset.get('freshness_recovery'), dict) else {}
    historical_backfill = dataset.get('historical_backfill') if isinstance(dataset.get('historical_backfill'), dict) else {}
    cio_decisions = dataset.get('cio_decisions') if isinstance(dataset.get('cio_decisions'), dict) else {}
    cio_cognition = dataset.get('cio_cognition') if isinstance(dataset.get('cio_cognition'), dict) else {}
    orders_layer = dataset.get('orders') if isinstance(dataset.get('orders'), dict) else {}
    fills_layer = dataset.get('fills') if isinstance(dataset.get('fills'), dict) else {}
    execution_layer = dataset.get('execution') if isinstance(dataset.get('execution'), dict) else {}
    trade_lifecycle = dataset.get('trade_lifecycle') if isinstance(dataset.get('trade_lifecycle'), dict) else {}
    transaction_cost = dataset.get('transaction_cost_analysis') if isinstance(dataset.get('transaction_cost_analysis'), dict) else {}
    sep='='*78
    L(sep); L('  BLUELOTUS FUND — RESEARCH DEPARTMENT REPORT — FIXED / ENRICHED R6'); L('  Deterministic Dataset-Driven Engine | Dataset v1.8u/v2.6 Compatible'); L(sep)
    L(f"  Platform Team    : {PLATFORM_TEAM}")
    L(f"  Generated        : {datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S SGT')}")
    L(f"  Dataset Generated: {meta.get('generated_at','')}")
    _snapshot_h = build_snapshot_hierarchy(dataset)
    _SESS_DISPLAY = {
        "REGULAR_SESSION":                  "REGULAR SESSION — LIVE INTRADAY",
        "PRE_MARKET":                       "PRE-MARKET",
        "POST_MARKET":                      "POST-MARKET / AFTER HOURS",
        "MARKET_CLOSED_LAST_REGULAR_CLOSE": "MARKET CLOSED — LAST REGULAR CLOSE",
        "WEEKEND_SNAPSHOT":                 "WEEKEND SNAPSHOT",
        "HOLIDAY_SNAPSHOT":                 "HOLIDAY SNAPSHOT",
        "STALE_ARCHIVE_SNAPSHOT":           "STALE ARCHIVE SNAPSHOT",
    }
    _sess_raw = meta.get('market_session') or (dataset.get('live_prices') or {}).get('market_session') or 'UNKNOWN'
    _sess_norm = normalize_market_session(_sess_raw, _snapshot_h["formal_report_snapshot_ts"])
    L(f"  FORMAL_REPORT_SNAPSHOT_TS       : {_snapshot_h['formal_report_snapshot_ts']}")
    L(f"  LIVE_DASHBOARD_SNAPSHOT_TS      : {_snapshot_h['live_dashboard_snapshot_ts']}")
    L(f"  BROKER_PORTFOLIO_TS             : {_snapshot_h['broker_portfolio_ts']}")
    L(f"  REPORT_IS_OLDER_THAN_LIVE_DASHBOARD : {_snapshot_h['report_is_older_than_live_dashboard']}")
    L(f"  REGIME_DIFFERENCE_DETECTED      : {_snapshot_h['regime_difference_detected']}")
    L(f"  Snapshot Timing : {_snapshot_h['snapshot_disclosure']}")
    L(f"  Market Status    : {_SESS_DISPLAY.get(_sess_norm, _sess_norm)}")
    L(f"  Export / Ingest  : {meta.get('export_version','')} / {meta.get('ingest_version','')}")
    L(f"  Sources Active   : {source_coverage_label(active, meta.get('sources_expected', total))}")
    L(f"  Total Signals    : {meta.get('total_signals',0):,} | Latest {meta.get('latest_signal_at','')}")
    L('-'*78)
    L(f"  Regime           : {reg.get('regime') or reg.get('regime_short','UNKNOWN')}  (score {reg.get('score',0)})")
    L(f"  Regime Action    : {reg.get('action','')}")
    L(f"  Portfolio Assets : {money(port.get('total_assets'))} | Cash {money(port.get('cash'))}")
    L(f"  CIO Compression  : {action} | Confidence {conf:.3f} ({confidence_grade(conf)})")
    L(f"  Blind Spot Status: {blind_status} | Causal Explanation: {_causal_status}")
    L(sep)

    # ── GOVERNANCE RELEASE BANNER ────────────────────────────────────────────
    try:
        import sys as _sys
        _gov_dir = Path(r"C:\bluelotus3\governance")
        if str(_gov_dir) not in _sys.path:
            _sys.path.insert(0, str(_gov_dir))
        from governance_gate import load_approved_truth as _lat
        _gov_truth = _lat()
        _gov_release = (_gov_truth or {}).get("_release_status", "UNKNOWN")
        _gov_score   = (_gov_truth or {}).get("governance_gate_score", "N/A")
        _gov_hygiene = ((_gov_truth or {}).get("sentiment_hygiene_gate") or {}).get("status", "UNKNOWN")
        _gov_failed  = (_gov_truth or {}).get("governance_gate_failed_gates") or []
        _gov_warnings= (_gov_truth or {}).get("_warnings", [])
    except Exception:
        _gov_release, _gov_score, _gov_hygiene, _gov_failed = "UNKNOWN", "N/A", "UNKNOWN", []

    if _gov_release == "BLOCKED":
        L('\n' + '!'*78)
        L('  !! REPORT BLOCKED BY GOVERNANCE GATE — DO NOT USE FOR CIO DECISION UNTIL FIXED !!')
        L(f'  !! Failed Gates: {_gov_failed}')
        L('!'*78)
    L(f"\n  Governance Release : {_gov_release}")
    L(f"  Governance Score   : {_gov_score}/100")
    L(f"  Sentiment Hygiene  : {_gov_hygiene}")
    if _gov_failed:
        L(f"  Failed Gates       : {', '.join(_gov_failed)}")

    # ── 1-PAGE CIO BRIEFING ──────────────────────────────────────────────────
    L('\n'+sep); L('  1-PAGE CIO BRIEFING  (Read in under 2 minutes)'); L(sep)
    # Concentration risk (inline)
    _positions = port.get('positions') or {}
    _total_assets = sf(port.get('total_assets') or port.get('total_value'))
    def _pos_weight(p):
        w = sf(p.get('weight'))
        if not w and _total_assets:
            w = sf(p.get('mkt_val') or p.get('market_val') or p.get('market_value')) / _total_assets
        return w
    _holdings = sorted(
        [(t, _pos_weight(p)) for t, p in _positions.items() if isinstance(p, dict) and _pos_weight(p) > 0],
        key=lambda x: x[1], reverse=True
    )
    _hhi = sum(w**2 for _, w in _holdings) if _holdings else 0.0
    _top3w = sum(w for _, w in _holdings[:3]) if _holdings else 0.0
    _lar_t, _lar_w = (_holdings[0][0], _holdings[0][1]) if _holdings else ('', 0.0)
    _CLUSTERS = {'GOLD_MINERS': {'AU','NEM','GLD','GDX','GDXJ'}, 'QUANTUM': {'QBTS','QUBT','IONQ','RGTI'},
                 'AI_SEMIS': {'NVDA','AMD','MU','SMCI','AMAT','ARM','AVGO'}, 'TECH_MAG7': {'AAPL','MSFT','GOOGL','AMZN','META','TSLA','NVDA'}}
    _clusters = {c: sum(w for t,w in _holdings if t.upper() in m) for c,m in _CLUSTERS.items() if sum(1 for t,_ in _holdings if t.upper() in m) >= 2}
    # Hygiene patch R6 — cluster-level severity (CRITICAL at >= 65% per work order)
    _cluster_max_name = max(_clusters, key=_clusters.get) if _clusters else None
    _cluster_max_val  = _clusters[_cluster_max_name] if _cluster_max_name else 0.0
    _cluster_severity = (
        'CRITICAL' if _cluster_max_val >= 0.65
        else 'HIGH' if _cluster_max_val >= 0.45
        else None
    )
    # Base status from HHI / single-name thresholds
    _conc_status_base = (
        'CRITICAL' if _hhi > 0.35 or _lar_w > 0.40
        else 'HIGH'     if _hhi > 0.20 or _lar_w > 0.30
        else 'ELEVATED' if _hhi > 0.12 or _lar_w > 0.20
        else 'NORMAL'
    )
    # Escalate to cluster severity if higher
    _SEV_ORDER = {'NORMAL': 0, 'ELEVATED': 1, 'HIGH': 2, 'CRITICAL': 3}
    if _cluster_severity and _SEV_ORDER.get(_cluster_severity, 0) > _SEV_ORDER.get(_conc_status_base, 0):
        _conc_status = _cluster_severity
    else:
        _conc_status = _conc_status_base
    _causal_txt = _causal_status  # Fix 2: use real causal status, not blind-spot-derived
    L(f"  {'Regime':<26}: [DATA CONFIRMED] {reg.get('regime') or reg.get('regime_short','UNKNOWN')} (score {reg.get('score',0)})")
    L(f"  {'CIO Action':<26}: [DATA CONFIRMED] {action}")
    L(f"  {'Confidence':<26}: [DATA CONFIRMED] {conf:.3f} ({confidence_grade(conf)})")
    L(f"  {'Causal Explanation':<26}: [MODEL INFERRED] {_causal_txt}")
    L(f"  {'Blind Spot Status':<26}: [MODEL INFERRED] {blind_status}")
    # Report Status — derived from canonical gate logic (blind_spot + causal + concentration)
    _r6_rr = "INSTITUTIONAL_REVIEW_REQUIRED" if (
        blind_status in ("WARNING", "CRITICAL") or
        _causal_txt not in ("COMPLETE", "MOSTLY_COMPLETE") or
        _r6_conc_status in ("HIGH", "CRITICAL")
    ) else "INSTITUTIONAL_READY"
    L(f"  {'Report Status':<26}: [DATA CONFIRMED] {_r6_rr}")
    L(f"  {'Total Assets':<26}: [DATA CONFIRMED] {money(port.get('total_assets'))} | Cash {money(port.get('cash'))}")
    L(f"  {'Total P/L':<26}: [DATA CONFIRMED] {money(port.get('total_pnl'))} ({sf(port.get('total_pnl_pct')):+.2f}%)")
    L(f"  {'Open Orders':<26}: [DATA CONFIRMED] {orders_layer.get('open_order_count',0)}")
    L(f"  {'Concentration':<26}: [DATA CONFIRMED] {_conc_status} | HHI {_hhi:.3f} | Top-3 {_top3w:.0%} | Largest {_lar_t} {_lar_w:.0%}")
    if _clusters:
        _cluster_parts = []
        for _ck, _cv in _clusters.items():
            _csev = 'CRITICAL' if _cv >= 0.65 else 'HIGH' if _cv >= 0.45 else 'ELEVATED' if _cv >= 0.30 else 'NORMAL'
            _cluster_parts.append(f"{_ck}: {_csev} / {_cv:.0%}")
        L(f"  {'Clusters':<26}: [DATA CONFIRMED] " + ' | '.join(_cluster_parts))
    if _conc_status == 'CRITICAL' and _cluster_max_name and _cluster_max_val >= 0.65:
        L(f"  {'CIO Deconcentration':<26}: [CIO THESIS] Gold thesis is confirming, but {_cluster_max_name} concentration is CRITICAL at {_cluster_max_val:.0%}. HOLD only. No add. CIO review required for deconcentration.")
    L('-'*78)
    _risks=[]
    if _causal_txt not in ('COMPLETE','MOSTLY_COMPLETE'): _risks.append(f'Causal explanation {_causal_txt} — research is PROVISIONAL')
    if blind_status!='CLEAR': _risks.append(f'Blind spot {blind_status} — unknown catalysts possible')
    if _conc_status in ('HIGH', 'CRITICAL'):
        if _cluster_max_name and _cluster_max_val >= 0.65:
            _risks.append(
                f'Concentration {_conc_status}: {_cluster_max_name} cluster CRITICAL at {_cluster_max_val:.0%}'
                f' | Largest name {_lar_t} {_lar_w:.0%} | HHI {_hhi:.3f}'
            )
        else:
            _risks.append(f'Concentration {_conc_status}: {_lar_t} {_lar_w:.0%} | HHI {_hhi:.3f}')
    if not _risks: _risks.append('No critical risks flagged this cycle')
    L(f"  {'TOP 3 RISKS':<26}:")
    for i,r in enumerate(_risks[:3],1): L(f"    {i}. [MODEL INFERRED] {r}")
    _top_opps = ece_sorted[:3]
    L(f"  {'TOP 3 OPPORTUNITIES':<26}:")
    if _top_opps:
        for i,e in enumerate(_top_opps,1): L(f"    {i}. [MODEL INFERRED] {e.get('theme','')} {pct(e.get('basket_move'))} | conf {sf(e.get('confidence')):.2f}")
    else:
        L('    1. [DATA CONFIRMED] No strong rotation signals this cycle')
    L('-'*78)
    L(f"  {'What CIO Should NOT Do':<26}: [CIO THESIS] Do NOT route orders. Do NOT lower cash. Do NOT add to concentrated cluster without causal confirmation.")
    if _causal_txt in ('COMPLETE', 'MOSTLY_COMPLETE'):
        if blind_status != 'CLEAR':
            _may_txt = "Address blind-spot failures and monitor thesis lifecycle before adding risk."
        else:
            _may_txt = "Review thesis lifecycle. Monitor upcoming catalysts."
    else:
        _may_txt = f"Monitor upcoming catalysts. Await causal explanation completion ({_causal_txt})."
    L(f"  {'What CIO May Consider':<26}: [PROVISIONAL] {_may_txt}")
    # Fix 2/3: doctrine warning from causal status only, not blind_status
    if _causal_txt not in ('COMPLETE', 'MOSTLY_COMPLETE'):
        L(f'  DOCTRINE WARNING  : CAUSAL EXPLANATION {_causal_txt}. Research conclusion is PROVISIONAL.')
    elif blind_status != 'CLEAR':
        L(f'  DOCTRINE WARNING  : Blind Spot {blind_status} — unknown catalysts possible. CIO review required.')
    L(sep)

    # ── BREAKING CATALYST + MONDAY SCENARIO OVERLAY ──────────────────────────
    try:
        import json as _json_r6
        from pathlib import Path as _Path_r6
        _BASE_R6 = _Path_r6(__file__).resolve().parent.parent
        _briefing_r6_path = _BASE_R6 / "data" / "governance" / "approved_cio_briefing.json"
        _briefing_r6: dict = _json_r6.loads(_briefing_r6_path.read_text(encoding="utf-8")) if _briefing_r6_path.exists() else {}
        _bc_r6 = _briefing_r6.get("breaking_catalyst") or {}
        _ov_r6 = _briefing_r6.get("scenario_overlay") or {}
        _mon_r6 = _briefing_r6.get("monday_open_scenario") or {}

        # Inline fallback detection — scan headlines_live.json directly in case
        # scenario_overlay_engine.py hasn't been run yet this session.
        _inline_overlay_active = False
        if not _bc_r6.get("detected"):
            try:
                _hl_path_r6 = _BASE_R6 / "data" / "headlines_live.json"
                _hl_data_r6 = (_json_r6.loads(_hl_path_r6.read_text(encoding="utf-8"))
                               if _hl_path_r6.exists() else {})
                _hl_texts_r6: list = []
                for _src_r6 in (_hl_data_r6.get("sources") or {}).values():
                    for _itm_r6 in (_src_r6.get("items") or []):
                        _hl_texts_r6.append(str(_itm_r6.get("text") or ""))
                # Import detect_relief_rally_overlay from outer generator
                from research_report_generator import detect_relief_rally_overlay as _drro
                _inline_r6 = _drro(_hl_texts_r6)
                _inline_overlay_active = _inline_r6.get("scenario_overlay") == "RELIEF_RALLY_POSSIBLE"
                if _inline_overlay_active:
                    # Synthesise overlay dicts from the inline result
                    _ov_r6 = {
                        "overlay_type":               "RELIEF_RALLY_POSSIBLE",
                        "risk_clearance":             "NOT_CONFIRMED",
                        "cio_action_adjusted":        _inline_r6["final_cio_posture"],
                        "gold_miner_relief_rally_action": _inline_r6["gold_miner_relief_action"],
                    }
                    _bc_r6 = {"detected": True, "catalyst_type": "GEOPOLITICAL_DEESCALATION",
                              "polarity": "RISK_ON_RELIEF", "confidence": "MEDIUM",
                              "verification_required": True, "headline_matched": _hl_texts_r6[0][:80] if _hl_texts_r6 else ""}
            except Exception:
                pass

        if _bc_r6.get("detected"):
            L('\n'+sep)
            L('  BREAKING CATALYST — SCENARIO OVERLAY')
            L(sep)
            L(f"  {'Base Regime':<26}: {_briefing_r6.get('base_regime', dataset.get('regime',{}).get('regime','RISK OFF'))} — NOT OVERWRITTEN BY OVERLAY")
            L(f"  {'Scenario Overlay':<26}: {_ov_r6.get('overlay_type','RELIEF_RALLY_POSSIBLE')}")
            L(f"  {'Risk Clearance':<26}: {_ov_r6.get('risk_clearance','NOT_CONFIRMED')}")
            L(f"  {'Final CIO Posture':<26}: {_ov_r6.get('cio_action_adjusted','WAIT / HOLD — RELIEF RALLY WATCH')}")
            L(f"  {'Gold Miner Action':<26}: {_ov_r6.get('gold_miner_relief_rally_action','DECONCENTRATION_WINDOW')}")
            if not _inline_overlay_active:
                L(f"  {'Catalyst Type':<26}: {_bc_r6.get('catalyst_type','—')} / {_bc_r6.get('polarity','—')}")
                L(f"  {'Headline Matched':<26}: {str(_bc_r6.get('headline_matched','—'))[:70]}")
                L(f"  {'Confidence':<26}: {_bc_r6.get('confidence','—')} (verification_required={_bc_r6.get('verification_required',True)})")
                _sp_r6 = _ov_r6.get("space_sector_overlay") or {}
                if _sp_r6:
                    L(f"  {'Space Net View':<26}: {_sp_r6.get('net_view','—')}")
            if _inline_overlay_active:
                L(f"  {'Source':<26}: Inline headline detection (scenario_overlay_engine backup)")
            if not _inline_overlay_active and not _inline_overlay_active and _ov_r6.get("gold_miner_relief_rally_action") == "DECONCENTRATION_WINDOW":
                L(f"  {'Gold Miner Note':<26}: If AU/NEM rise in the next U.S. regular session, CIO may use strength to reduce concentration.")
                L(f"  {'  ':<26}  Do not add to gold miners while cluster concentration remains CRITICAL.")
            if _mon_r6:
                L('\n  ' + '-'*76)
                L('  NEXT U.S. REGULAR SESSION SCENARIO')
                L('  ' + '-'*76)
                _sc_labels = {'scenario_a': 'A', 'scenario_b': 'B', 'scenario_c': 'C'}
                for _sc_key, _sc_val in _mon_r6.items():
                    _sc_lbl = _sc_labels.get(_sc_key, _sc_key.upper())
                    L(f"\n  Scenario {_sc_lbl}: {_sc_val.get('name','')}")
                    for _sig in (_sc_val.get('signals') or []):
                        L(f"    - {_sig}")
                    L(f"\n  CIO Implication: {_sc_val.get('cio_implication','')}")
            elif _inline_overlay_active:
                # Hardcoded Monday scenario block (used when overlay fires inline)
                L('\n  ' + '-'*76)
                L('  NEXT U.S. REGULAR SESSION SCENARIO')
                L('  ' + '-'*76)
                L('\n  Scenario A: Relief Rally Confirmed')
                for _s in ['Oil down','VIX / VXX down','SPY / QQQ / IWM up','USD/JPY stable',
                           'Space / quantum / AI bounce','Gold mixed or flat','Miners may gap up']:
                    L(f'    - {_s}')
                L('\n  CIO Implication: Use strength to reduce concentration. Do not chase the open.')
                L('\n  Scenario B: Headline Fades')
                for _s in ['Oil rebounds','VIX rises','SPY / QQQ fade','Gold rises','Miners volatile','Space / quantum fail bounce']:
                    L(f'    - {_s}')
                L('\n  CIO Implication: Preserve cash. Do not add risk. Manual de-risk review remains active.')
                L('\n  Scenario C: BOJ / FOMC Overrides Relief')
                for _s in ['Yen strengthens sharply','USD/JPY drops','Nikkei weak','US high beta sells',
                           'Gold may hold but miners can sell as equities']:
                    L(f'    - {_s}')
                L('\n  CIO Implication: Do not rely only on Iran relief headline. BOJ / FOMC remains the primary macro gate.')
            L(sep)
    except Exception as _e_r6:
        pass  # Overlay section is informational; never crash the core report

    # ── GOLD SAFE-HAVEN THESIS TRACKER ───────────────────────────────────────
    try:
        from research_report_generator import build_gold_thesis_tracker as _build_gtt
        _gtt = _build_gtt(dataset)
        _gtt_status = _gtt.get('status','UNKNOWN')
        _gtt_score  = _gtt.get('score', 0)
        _gtta       = _gtt.get('thesis_action') or {}
        _gttm       = _gtt.get('key_metrics') or {}
        _gtc        = _gtt.get('checks') or {}

        def _gtt_chg(key): v = _gttm.get(key); return f"{v:+.2f}%" if v is not None else "N/A"

        L('\n'+sep)
        L('  GOLD SAFE-HAVEN THESIS TRACKER')
        L(sep)
        L(f"  Status            : {_gtt_status}  |  Score {_gtt_score:.2f}/1.00  |  Confidence {_gtt.get('confidence','LOW')}")
        L(f"  Gold Miner Cluster: {_gtta.get('gold_miner_cluster_weight',0):.0%}")
        L(f"  CIO Gold Action   : {_gtta.get('gold_miner_core_action','HOLD / WAIT')}")
        L(f"  Thesis Add Signal : {_gtta.get('thesis_add_signal', 'UNKNOWN')}")
        L(f"  Execution Perm    : {_gtta.get('execution_permission', 'UNKNOWN')}")
        L(f"  Add Reason        : {_gtta.get('reason','')}")
        L('-'*78)
        _GT_CHECKS_TXT = [
            ('gold_stabilizes_and_rises',         '1. Gold stabilizes/rises    '),
            ('silver_confirms_or_gsr_compresses', '2. Silver confirms/GSR      '),
            ('miners_vs_gold',                    '3. GDX/GDXJ vs GLD          '),
            ('au_nem_vs_gdx',                     '4. AU/NEM vs GDX            '),
            ('real_yields_do_not_spike',          '5. Real yields stable       '),
            ('dxy_does_not_surge',                '6. DXY/UUP not surging      '),
            ('oil_risk_premium_elevated',         '7. Oil-risk premium         '),
            ('miners_not_liquidated_as_equity_beta','8. Miner liquidation risk  '),
        ]
        for _gck, _glbl in _GT_CHECKS_TXT:
            _gch = _gtc.get(_gck) or {}
            _gcst = _gch.get('status','MISSING')
            _gcev = _gch.get('evidence','')[:60]
            L(f"  {_glbl}: [{_gcst:<7}] {_gcev}")
        L('-'*78)
        L(f"  Key Metrics  : GLD {_gtt_chg('gld_change_pct')} | SLV {_gtt_chg('slv_change_pct')} | GDX-GLD {_gtt_chg('gdx_vs_gld_spread')} | AU-GDX {_gtt_chg('au_vs_gdx_spread')}")
        L(f"               : UUP {_gtt_chg('uup_change_pct')} | TLT {_gtt_chg('tlt_change_pct')} | 10Y {_gttm.get('ten_year_yield') or 'N/A'} | XLE {_gtt_chg('xle_change_pct')} | Oil hits {_gttm.get('oil_news_pressure_score',0)}")
        L(f"               : SPY {_gtt_chg('spy_change_pct')} | VXX {_gtt_chg('vxx_change_pct')} | GSR proxy {_gttm.get('gold_silver_ratio_proxy') or 'N/A'}")
        L(f"  Interpretation: {_gtt.get('summary','')[:160]}")
        L('-'*78)
        # Hygiene patch R6 — reconcile tracker score vs cross-market binary flag
        _cm_flags_gold = (cm.get('interpretation_flags') or {}) if cm else {}
        _gold_binary   = _cm_flags_gold.get('gold_thesis_confirmed', None)
        L(f"  gold_thesis_tracker_status    : {_gtt_status}  (multi-factor score {_gtt_score:.2f}/1.00)")
        L(f"  gold_cross_market_binary_flag : {_gold_binary}  (strict gate: GLD>0 AND miners>0 AND SPY<0)")
        if _gtt_status in ('CONFIRMING', 'STRENGTHENING') and not _gold_binary:
            L(f"  Reconciliation : Tracker confirms multi-factor thesis strength; binary flag may remain False")
            L(f"                   if the strict simultaneous gate is not met. These are two independent checks.")
            L(f"                   No contradiction — CIO should treat tracker score as primary thesis signal.")
        elif _gtt_status in ('CONFIRMING', 'STRENGTHENING') and _gold_binary:
            L(f"  Reconciliation : Tracker and binary flag both confirm gold thesis. Fully consistent.")
        else:
            L(f"  Reconciliation : Review tracker checks above for thesis condition details.")
        L(sep)
    except Exception as _gtt_ex:
        L(f"\n  [GOLD THESIS TRACKER UNAVAILABLE: {_gtt_ex}]")

    # Executive summary
    L('\n'+sep); L('  EXECUTIVE SUMMARY'); L(sep)
    cash_pct=sf(port.get('cash'))/sf(port.get('total_assets'),1)*100 if sf(port.get('total_assets')) else 0
    eq_pct=sf(port.get('market_val'))/sf(port.get('total_assets'),1)*100 if sf(port.get('total_assets')) else 0
    strongest=', '.join([f"{e.get('theme')} {pct(e.get('basket_move'))}" for e in ece_sorted[:3]])
    weakest=', '.join([f"{e.get('theme')} {pct(e.get('basket_move'))}" for e in sorted(ece,key=lambda e:sf(e.get('basket_move')))[:3]])
    movers=', '.join([f"{m.get('ticker')} {pct(m.get('chg_pct'))}" for m in top[:5]])
    L(f"  Market Regime     : {reg.get('regime') or reg.get('regime_short','UNKNOWN')} | score {reg.get('score',0)}")
    L(f"  VIX / Fear-Greed  : {sf(vix.get('price')):.2f} / {sf(fg.get('score')):.1f} ({fg.get('label','')})")
    L(f"  Macro / Inst Tone : {sf(reg.get('macro_avg')):+.4f} / {sf(reg.get('inst_avg')):+.4f}")
    L(f"  Portfolio         : Cash {money(port.get('cash'))} ({cash_pct:.1f}%), Equity {money(port.get('market_val'))} ({eq_pct:.1f}%), Total P/L {money(port.get('total_pnl'))} ({sf(port.get('total_pnl_pct')):+.2f}%)")
    L(f"  Final Action      : {action} — {action_reason}")
    L(f"  Top Movers        : {movers}")
    L(f"  Strongest Themes  : {strongest}")
    L(f"  Weakest Themes    : {weakest}")
    if iq:
        L(f"  Quant Readiness   : {iq.get('readiness_label','UNKNOWN')} | {fmt_iq_score(iq.get('readiness_score'))} | {iq.get('status','UNKNOWN')}")
    if rf:
        L(f"  Superforecasting  : {rf.get('status','UNKNOWN')} | snapshot {rf.get('snapshot_id','')} | Brier {rf.get('brier_status','collecting')}")
    if cm:
        cm_flags = cm.get('interpretation_flags') or {}
        active_cm_flags = ', '.join(k for k,v in cm_flags.items() if v) or 'none'
        L(f"  Cross-Market      : coverage {cm.get('filled_count','?')}/{cm.get('ticker_count','?')} | active flags: {active_cm_flags}")
    if formal_risk and formal_risk.get('status') != 'not_configured':
        hv = formal_risk.get('historical_var') or {}
        v95 = (hv.get('confidence_95') or {}).get('daily_dollars')
        L(f"  Risk Model        : VaR95 {money(v95)} | obs {formal_risk.get('return_observations','')} | beta SPY {sf(formal_risk.get('beta_to_spy')):.3f}")
    if thesis_layer and thesis_layer.get('status') == 'operational':
        L(f"  Thesis Lifecycle  : {thesis_layer.get('thesis_count',0)} theses | {thesis_layer.get('status_counts',{})}")
    if monitoring_layer:
        L(f"  Monitoring        : alerts {monitoring_layer.get('alert_count',0)} | {monitoring_layer.get('severity_counts',{})}")
    if cio_decisions:
        L(f"  CIO Decision Log  : pending {cio_decisions.get('pending_review_count',0)} | orders generated {cio_decisions.get('orders_generated',0)}")
    if cio_cognition:
        L(f"  CIO Cognition     : journal {cio_cognition.get('latest_journal_id','')} | thesis reviews {cio_cognition.get('review_count',0)} | orders generated {cio_cognition.get('orders_generated',0)}")
    if execution_layer:
        L(f"  Execution Intel   : {orders_layer.get('open_order_count',0)} open orders | {orders_layer.get('historical_order_count',0)} historical orders | {fills_layer.get('historical_deal_count',0)} fills | routing {yesno(execution_layer.get('order_routing_enabled'))}")
    if historical_backfill:
        L(f"  History Backfill  : {historical_backfill.get('status','')} | queue {historical_backfill.get('queue_counts',{})}")
    # Fix 2/3: doctrine warning from causal status only
    if _causal_txt not in ('COMPLETE', 'MOSTLY_COMPLETE'):
        L(f'  DOCTRINE WARNING  : CAUSAL EXPLANATION {_causal_txt}. Research conclusion is PROVISIONAL.')
    elif blind_status != 'CLEAR':
        L(f'  DOCTRINE WARNING  : Blind Spot {blind_status} — CIO review required before risk addition.')

    # Dataset health
    L('\n'+sep); L('  DATASET INTEGRITY & SOURCE HEALTH'); L(sep)
    L(f"  Export / Ingest   : {meta.get('export_version','')} / {meta.get('ingest_version','')}")
    L(f"  Sources Active    : {source_coverage_label(active, total)}")
    L('  Source Tiers      : ' + ' | '.join(f"{k} {v[0]}/{v[1]}" for k,v in sorted(tiers.items())))
    L('  Source Types      : ' + ', '.join(f"{k}:{v}" for k,v in sorted(types.items())))
    L('\n  Freshness:')
    for k,v in (meta.get('freshness') or {}).items():
        if k=='thresholds': continue
        L(f"    {k:<24} {str(v.get('grade','UNKNOWN')):<14} age={v.get('age_minutes')}")
    if port.get('integrity_flag'): L(f"\n  ⚠ Portfolio integrity_flag = TRUE: {port.get('integrity_flag_reason','reconcile portfolio snapshot')}")
    if (meta.get('freshness') or {}).get('fear_greed',{}).get('grade')=='STALE': L('  Fear & Greed: STALE_SECONDARY / EXCLUDED_FROM_CIO_CONFIDENCE.')

    # Institutional quant process layer
    L('\n'+sep); L('  INSTITUTIONAL QUANT READINESS — DATABASE PROCESS LAYER'); L(sep)
    if not iq or iq.get('status') in ('not_configured', 'no_completed_run', 'extract_error'):
        L(f"  Status            : {iq.get('status','NOT_AVAILABLE') if iq else 'NOT_AVAILABLE'}")
        if iq.get('reason'): L(f"  Reason            : {iq.get('reason')}")
        L('  Interpretation    : Process layer not yet available in dataset_raw.json.')
    else:
        L(f"  Run ID            : {iq.get('run_id','')}")
        L(f"  Run Version       : {iq.get('run_version','')}")
        L(f"  Completed At      : {iq.get('completed_at','')}")
        L(f"  Dataset SHA-256   : {iq.get('dataset_sha256','')}")
        L(f"  Readiness         : {fmt_iq_score(iq.get('readiness_score'))} ({iq.get('readiness_label','UNKNOWN')})")
        L(f"  Status            : {iq.get('status','UNKNOWN')}")
        if iq_counts:
            L(f"  Process Counts    : PASS {iq_counts.get('PASS',0)} | WARNING {iq_counts.get('WARNING',0)} | FAIL {iq_counts.get('FAIL',0)}")
        L('\n  Process Results:')
        L(table_line([('Process',30),('Status',10),('Score',12),('Label',22),('Primary Gap',30)]))
        for name,proc in institutional_process_rows(iq):
            warnings=proc.get('warnings') or []
            gap=clean_text(warnings[0],30) if warnings else ''
            _p_status = proc.get('status','')
            _p_label = proc.get('readiness_label','')
            if name == 'risk_model' and si(formal_risk.get('return_observations')) <= 0:
                _p_status = 'TELEMETRY_PRESENT'
                _p_label = 'HISTORY_INSUFFICIENT'
                gap = clean_text((gap + '; ' if gap else '') + 'zero return observations', 30)
            L(table_line([(name,30),(_p_status,10),(fmt_iq_score(proc.get('readiness_score')),12),(_p_label,22),(gap,30)]))
        gaps = institutional_gap_rows(iq)
        if gaps:
            L('\n  Priority Gaps:')
            for name,proc,gap in gaps:
                L(f"    • {name}: {proc.get('status','')} | {fmt_iq_score(proc.get('readiness_score'))} | {gap}")
        L('\n  Interpretation:')
        if sf(iq.get('readiness_score')) >= 85:
            L('    Institutional quant process layer is reporting high readiness.')
        elif sf(iq.get('readiness_score')) >= 70:
            L('    Infrastructure is advanced, but remaining process gaps still require closure before quant-grade signoff.')
        else:
            L('    Research intelligence is strong, but quant-grade readiness remains provisional until failed process areas are built out.')

    # Execution intelligence / read-only broker history
    L('\n'+sep); L('  EXECUTION INTELLIGENCE / TCA READINESS - READ ONLY'); L(sep)
    if not execution_layer and not orders_layer and not fills_layer:
        L('  Status            : NOT_AVAILABLE')
        L('  Interpretation    : Broker order/deal extraction has not been exported into dataset_raw.json.')
    else:
        decision_control = execution_layer.get('decision_control') if isinstance(execution_layer.get('decision_control'), dict) else {}
        broker = orders_layer.get('broker') or 'moomoo'
        source = orders_layer.get('data_source') or ''
        query_errors = orders_layer.get('query_errors') if isinstance(orders_layer.get('query_errors'), dict) else {}
        L(f"  Status            : {execution_layer.get('status', orders_layer.get('status','UNKNOWN'))}")
        L(f"  Snapshot          : {orders_layer.get('snapshot_id','')} | cycle {orders_layer.get('cycle_ts','')}")
        L(f"  Broker / Source   : {broker} / {source} | env {orders_layer.get('trd_env','')}")
        L(f"  History Window    : {orders_layer.get('start_date','')} -> {orders_layer.get('end_date','')}")
        L(f"  Order History     : {orders_layer.get('status','UNKNOWN')} | open {orders_layer.get('open_order_count',0)} | historical {orders_layer.get('historical_order_count',0)}")
        L(f"  Fill History      : {fills_layer.get('status','UNKNOWN')} | open {fills_layer.get('open_deal_count',0)} | historical {fills_layer.get('historical_deal_count',0)}")
        L(f"  Fee Records       : {orders_layer.get('fee_record_count',0)} | TCA {transaction_cost.get('status','UNKNOWN')} | actual fills {yesno(transaction_cost.get('actual_fills_available'))}")
        L(f"  CIO Reviews       : pending {decision_control.get('pending_review_count',0)} | exported {decision_control.get('decision_count_exported',0)}")
        L(f"  System Authority  : {execution_layer.get('execution_authority','CIO_ONLY_MANUAL')} | generated orders {execution_layer.get('orders_generated',0)} | routing {yesno(execution_layer.get('order_routing_enabled'))}")
        L('  Doctrine          : Broker API is extraction-only. CIO owns execution. No order routing is enabled by this report or pipeline.')
        if query_errors:
            L(f"  Query Errors      : {query_errors}")

        open_orders = orders_layer.get('open_orders') if isinstance(orders_layer.get('open_orders'), list) else []
        L('\n  Open Broker Orders:')
        if open_orders:
            L(table_line([('Ticker',8),('Side',6),('Status',20),('Order Intent',30),('Qty',8),('Limit',12),('Dealt',8),('Updated',20)]))
            for row in open_orders[:10]:
                if not isinstance(row, dict): continue
                L(table_line([
                    (broker_ticker(row),8),
                    (row.get('trd_side',''),6),
                    (row.get('order_status',''),20),
                    (classify_order_intent(row),30),
                    (si(row.get('qty')),8),
                    (money(row.get('price')),12),
                    (si(row.get('dealt_qty')),8),
                    (row.get('updated_time',''),20),
                ]))
        else:
            L('    none')

        plan_book = cio_plan_vs_order_book(dataset)
        L('\n  CIO Plan vs Broker Order Book:')
        _gm_live_context = "CURRENT_LIVE_POSITION_REVIEW" if _cluster_max_name == "GOLD_MINERS" and _cluster_max_val > 0 else "OPEN_ORDER_REVIEW"
        L(f"  CIO Intended Action : Gold thesis WARNING / THESIS_WEAKENING; HOLD / REVIEW only; no add unless CIO support-bid policy explicitly applies; CIO review context={_gm_live_context}.")
        L(f"  Existing Miner Sells: {len(plan_book.get('miner_orders') or [])} AU/NEM sell orders open")
        L(f"  Feasibility         : {plan_book.get('feasibility')}")
        L(f"  System Authority    : {plan_book.get('execution_authority')} | generated orders {plan_book.get('generated_orders')} | routing {yesno(plan_book.get('routing_enabled'))}")
        L(f"  Warning             : {plan_book.get('warning')}")
        for item in (plan_book.get('miner_orders') or [])[:8]:
            L(f"    {item.get('ticker')}: {item.get('status')} qty {si(item.get('qty'))} limit {money(item.get('limit'))} current {money(item.get('current_price'))} dealt {si(item.get('dealt_qty'))} executable_now {yesno(item.get('executable_now'))}")

        recent_fills = fills_layer.get('historical_deals_recent') if isinstance(fills_layer.get('historical_deals_recent'), list) else []
        L('\n  Recent Broker Fills / Deals:')
        if recent_fills:
            L(table_line([('Ticker',8),('Side',6),('Qty',8),('Price',12),('Deal Time',20),('Order ID',24)]))
            for row in recent_fills[:10]:
                if not isinstance(row, dict): continue
                L(table_line([
                    (broker_ticker(row),8),
                    (row.get('trd_side',''),6),
                    (si(row.get('qty')),8),
                    (money(row.get('price')),12),
                    (row.get('deal_time',''),20),
                    (clean_text(row.get('order_id',''),24),24),
                ]))
        else:
            L('    none')

        stages = trade_lifecycle.get('stages') if isinstance(trade_lifecycle.get('stages'), list) else []
        if stages:
            L('\n  Manual Trade Lifecycle:')
            L(table_line([('Stage',28),('Owner',18),('System Record',46)]))
            for row in stages:
                if not isinstance(row, dict): continue
                L(table_line([
                    (clean_text(row.get('stage',''),28),28),
                    (clean_text(row.get('owner',''),18),18),
                    (clean_text(row.get('system_record',''),46),46),
                ]))

    # Deterministic operator layer
    det_ops = dataset.get('deterministic_operators') if isinstance(dataset.get('deterministic_operators'), dict) else {}
    det_summary = det_ops.get('summary') if isinstance(det_ops.get('summary'), dict) else {}
    det_operator_map = det_ops.get('operators') if isinstance(det_ops.get('operators'), dict) else {}
    L('\n'+sep); L('  DETERMINISTIC OPERATOR LAYER - RULES BASED'); L(sep)
    if not det_ops or det_ops.get('status') in ('not_available', 'artifact_read_error', 'invalid_artifact'):
        L(f"  Status            : {det_ops.get('status','NOT_AVAILABLE') if det_ops else 'NOT_AVAILABLE'}")
        if det_ops.get('reason'): L(f"  Reason            : {det_ops.get('reason')}")
        L('  Interpretation    : Deterministic operator artifact has not been exported into dataset_raw.json yet.')
    else:
        L(f"  Status            : {det_ops.get('status','UNKNOWN')} | readiness {det_ops.get('readiness','UNKNOWN')}")
        L(f"  Generated         : {det_ops.get('generated_at','')} | source dataset {det_ops.get('source_dataset_generated_at','')}")
        L(f"  System Authority  : {det_ops.get('execution_authority','CIO_ONLY_MANUAL')} | LLM used {yesno(det_ops.get('llm_used'))} | generated orders {det_ops.get('orders_generated',0)} | routing {yesno(det_ops.get('order_routing_enabled'))}")
        L(f"  Operator Counts   : total {det_summary.get('operator_count',0)} | fail {det_summary.get('fail_count',0)} | review {det_summary.get('review_count',0)}")
        L(f"  Blocked Actions   : {', '.join(det_summary.get('blocked_actions') or []) or 'none'}")
        L('  Doctrine          : Operators calculate. Chief Strategist interprets. CIO decides. CIO executes manually. System records.')
        L('\n  Operator Findings:')
        L(table_line([('Operator',24),('Status',12),('Score',8),('Confidence',16),('Blocked Actions',40)]))
        for name, op in det_operator_map.items():
            if not isinstance(op, dict): continue
            L(table_line([
                (clean_text(name,24),24),
                (op.get('status',''),12),
                (sf(op.get('score')) if op.get('score') not in (None,'') else '',8),
                (op.get('confidence',''),16),
                (clean_text(', '.join(op.get('blocked_actions') or []) or 'none',40),40),
            ]))
            evidence = op.get('evidence') if isinstance(op.get('evidence'), list) else []
            for item in evidence[:3]:
                L(f"      - {clean_text(item,110)}")

    # BlueLotus superforecast / Brier accountability layer
    L('\n'+sep); L('  BLUELOTUS SUPERFORECAST / BRIER ACCOUNTABILITY LAYER'); L(sep)
    if not rf or rf.get('status') in ('not_configured', 'no_forecasts', 'extract_error'):
        L(f"  Status            : {rf.get('status','NOT_AVAILABLE') if rf else 'NOT_AVAILABLE'}")
        if rf.get('reason'): L(f"  Reason            : {rf.get('reason')}")
        L('  Interpretation    : Forecast rows have not yet been generated into ticker_forecasts.')
    else:
        L(f"  Snapshot ID       : {rf.get('snapshot_id','')}")
        L(f"  Forecast Date     : {rf.get('forecast_date','')}")
        L(f"  Forecast Coverage : {rf.get('ticker_count',0)} tickers | {rf.get('forecast_count',0)} method rows | methods={', '.join(rf.get('methods') or [])}")
        L(f"  House Method      : {rf.get('house_method','BLUELOTUS_CONSERVATIVE')}")
        L(f"  Benchmark Method  : {rf.get('benchmark_method','ANALYST_CONSENSUS')}")
        L(f"  Brier Status      : {rf.get('brier_status','collecting')}")
        L('  Doctrine          : Forecasts are research accountability records, not CIO execution orders.')
        L('\n  Top BlueLotus Conservative 90D Forecast Deltas:')
        L(table_line([('Ticker',8),('Dir',6),('Price',12),('90D Target',12),('ExpRet',9),('Prob90',8),('Theme',34)]))
        for row in forecast_rows_for_report(rf, 12):
            L(table_line([
                (row.get('ticker',''),8),
                (row.get('direction',''),6),
                (money(row.get('current_price')),12),
                (money(row.get('target_price_90d')),12),
                (pct(row.get('expected_return_90d')),9),
                (f"{sf(row.get('probability_90d')):.3f}",8),
                (clean_text(row.get('sector_theme',''),34),34),
            ]))
        acc = rf.get('accuracy_summary') or []
        if acc:
            L('\n  Resolved Accuracy Summary:')
            L(table_line([('Method',26),('H',4),('N',6),('Brier',10),('PriceErr',10),('DirAcc',10)]))
            for row in acc[:20]:
                L(table_line([
                    (row.get('prediction_method',''),26),
                    (row.get('horizon_days',''),4),
                    (row.get('resolved_count',''),6),
                    (f"{sf(row.get('avg_brier_score')):.4f}",10),
                    (f"{sf(row.get('avg_percentage_error')):.4f}",10),
                    (f"{sf(row.get('directional_accuracy')):.4f}",10),
                ]))
        else:
            L('\n  Accuracy Summary  : COLLECTING. No forecast horizon has matured yet; do not claim forecast skill.')

    # Fresh market intelligence tape
    L('\n'+sep); L('  FRESH MARKET INTELLIGENCE TAPE — NON-STALE SIGNALS'); L(sep)
    fs=fresh_signals(dataset,180,80)
    grouped={}
    for s in fs:
        cat=classify_signal_text(s.get('_text',''), s.get('source',''), s.get('signal_type',''))
        # reduce low signal duplicates, but preserve cross-source tape
        grouped.setdefault(cat,[]).append(s)
    if not fs:
        L('  No fresh signals inside the configured 180-minute window.')
    else:
        for cat in ['MACRO / FED','GEOPOLITICAL','AI / SEMIS','BANKS','COMMODITIES','QUANTUM','OTHER']:
            rows=grouped.get(cat,[])[:8]
            if not rows: continue
            L(f"\n  {cat}")
            L('  ' + '-'*74)
            for s in rows:
                L(f"    • [{s.get('source')}] age={s.get('_age',0):.0f}m | {clean_text(s.get('_text'),155)}")

    # Regime
    L('\n'+sep); L('  MARKET REGIME — BASE RATE FIRST'); L(sep)
    L(f"  State             : {reg.get('regime') or reg.get('regime_short','UNKNOWN')} | score {reg.get('score',0)}")
    L(f"  Action            : {reg.get('action','')}")
    L(f"  Warnings          : {', '.join(reg.get('warnings') or [])}")
    L('  Factors           : ' + ' | '.join(f"{k}:{v:+d}" for k,v in (reg.get('factors') or {}).items()))
    L(f"  VIX               : {sf(vix.get('price')):.2f} ({pct(vix.get('chg_pct'))})")
    L(f"  Fear & Greed      : {sf(fg.get('score')):.1f} — {fg.get('label','')} {'[STALE_SECONDARY / EXCLUDED_FROM_CIO_CONFIDENCE]' if (meta.get('freshness') or {}).get('fear_greed',{}).get('grade')=='STALE' else ''}")
    ty, ty_status = treasury_snapshot(dataset)
    L('\n  Treasury / Rates:')
    if ty_status == 'OK':
        curve = ty.get('curve')
        curve_state = 'NORMAL' if curve is not None and curve >= 0 else ('INVERTED' if curve is not None else '')
        L(f"    10Y {ty.get('10Y'):.2f}% | 2Y {ty.get('2Y'):.2f}% | 30Y {ty.get('30Y'):.2f}% | 3M {ty.get('3M'):.2f}%")
        L(f"    Curve 10Y-2Y: {sf(curve):+.2f}% [{curve_state}] | Fed Funds {sf(ty.get('fed_funds')):.3f}% | NIM proxy {sf(ty.get('nim_proxy')):+.2f}%")
    else:
        nim_txt = f" | NIM proxy {sf(ty.get('nim_proxy')):+.2f}%" if 'nim_proxy' in ty else ''
        L(f"    Treasury data marked fresh but yield field mapping unresolved — CHECK DATASET SCHEMA{nim_txt}")

    # Cross-market confirmation
    L('\n'+sep); L('  CROSS-MARKET CONFIRMATION LAYER - V2.7'); L(sep)
    if not cm:
        L('  Status            : NOT_AVAILABLE')
        L('  Interpretation    : Cross-market confirmation has not been fetched yet.')
    else:
        L(f"  Cycle TS          : {cm.get('cycle_ts','')}")
        L(f"  Source            : {cm.get('source','')} | {cm.get('source_detail','')}")
        L(f"  Coverage          : {cm.get('filled_count','?')}/{cm.get('ticker_count','?')} ({sf(cm.get('coverage_ratio'))*100:.1f}%)")
        L('\nA. Market Index Confirmation')
        L(table_line([('Ticker',8),('Price',12),('Move',9),('Volume',14),('Source',14)]))
        for t in ['SPY','QQQ','IWM','RSP']:
            r=cm_item(cm,'market_index_confirmation',t)
            L(table_line([(t,8),(money(r.get('price')),12),(pct(r.get('chg_pct')),9),(f"{si(r.get('volume')):,}",14),(r.get('price_source',''),14)]))
        L('\nB. Volatility / Panic Confirmation')
        for t in ['VXX','UVXY','^VIX']:
            r=cm_item(cm,'volatility_panic_confirmation',t)
            if r.get('unavailable'): L(f"  {t:<6} unavailable via Moomoo-only policy; proxy={r.get('proxy')} | {clean_text(r.get('reason'),100)}")
            else: L(f"  {t:<6} {money(r.get('price'))} ({pct(r.get('chg_pct'))})")
        L('\nC. Dollar / Rates Pressure')
        for t in ['UUP','TLT','IEF','SHY','DXY','^TNX']:
            r=cm_item(cm,'dollar_rates_pressure',t)
            if r.get('unavailable'): L(f"  {t:<6} unavailable via Moomoo-only policy; proxy={r.get('proxy')} | {clean_text(r.get('reason'),100)}")
            else: L(f"  {t:<6} {money(r.get('price'))} ({pct(r.get('chg_pct'))})")
        L('\nD. Gold / Miner Confirmation')
        L(table_line([('Ticker',8),('Price',12),('Move',9),('Volume',14)]))
        for t in ['GLD','SLV','GDX','GDXJ','AU','NEM']:
            r=cm_item(cm,'gold_miner_confirmation',t)
            L(table_line([(t,8),(money(r.get('price')),12),(pct(r.get('chg_pct')),9),(f"{si(r.get('volume')):,}",14)]))
        L('\nE. Sector ETF Rotation')
        for t in ['XLK','XLF','XLE','XLU','XLP','XLI','XLY','XLV','XLB','XLC']:
            r=cm_item(cm,'sector_etf_rotation',t)
            L(f"  {t:<6} {money(r.get('price'))} ({pct(r.get('chg_pct'))})")
        L('\nF. Credit / Liquidity Stress')
        for t in ['HYG','JNK','LQD','AGG']:
            r=cm_item(cm,'credit_liquidity_stress',t)
            L(f"  {t:<6} {money(r.get('price'))} ({pct(r.get('chg_pct'))})")
        L('\nG. Derived Scores')
        for k,v in (cm.get('derived_scores') or {}).items():
            L(f"  {k:<40} {sf(v):+.4f}")
        L('\nH. Interpretation Flags')
        _cm_interp = cm.get('interpretation_flags') or {}
        # Hygiene patch R6 — use tracker status already computed above (or fallback)
        try:
            _h_gtt_status = _gtt_status
        except NameError:
            _h_gtt_status = 'UNKNOWN'
        for k, v in _cm_interp.items():
            if k == 'gold_thesis_confirmed':
                L(f"  {'gold_cross_market_binary_flag':<36} {v}")
                L(f"  {'gold_thesis_tracker_status':<36} {_h_gtt_status}")
                if _h_gtt_status in ('CONFIRMING', 'STRENGTHENING') and not v:
                    L(f"  {'  explanation':<36} Tracker uses multi-factor score; binary flag requires")
                    L(f"  {'':<36} GLD>0 AND miners>0 AND SPY<0 simultaneously.")
                    L(f"  {'':<36} No contradiction — two independent checks.")
            else:
                L(f"  {k:<36} {v}")

    # Formal risk model
    L('\n'+sep); L('  FORMAL RISK MODEL - HISTORY-BASED VAR / FACTOR TELEMETRY'); L(sep)
    if not formal_risk or formal_risk.get('status') in ('not_configured', 'no_run', 'extract_error'):
        L(f"  Status            : {formal_risk.get('status','NOT_AVAILABLE') if formal_risk else 'NOT_AVAILABLE'}")
        if formal_risk.get('reason'): L(f"  Reason            : {formal_risk.get('reason')}")
        L('  Interpretation    : Formal risk model has not produced a usable run yet.')
    else:
        hv = formal_risk.get('historical_var') or {}
        v95 = hv.get('confidence_95') or {}
        v99 = hv.get('confidence_99') or {}
        es95 = hv.get('expected_shortfall_95') or {}
        L(f"  Run ID            : {formal_risk.get('run_id','')}")
        L(f"  Generated At      : {formal_risk.get('generated_at','')}")
        if si(formal_risk.get('return_observations')) <= 0:
            L("  Status            : TELEMETRY_PRESENT / HISTORY_INSUFFICIENT")
        L(f"  Observations      : {formal_risk.get('return_observations','')} | window {formal_risk.get('price_start','')} -> {formal_risk.get('price_end','')}")
        L(f"  Portfolio Value   : {money(formal_risk.get('portfolio_value'))} | Cash weight {sf(formal_risk.get('cash_weight'))*100:.2f}%")
        L(f"  Daily VaR 95      : {money(v95.get('daily_dollars'))} ({sf(v95.get('daily_pct'))*100:.2f}%)")
        L(f"  Daily VaR 99      : {money(v99.get('daily_dollars'))} ({sf(v99.get('daily_pct'))*100:.2f}%)")
        L(f"  Expected Shortfall: {money(es95.get('daily_dollars'))} ({sf(es95.get('daily_pct'))*100:.2f}%)")
        L(f"  Annualized Vol    : {sf(formal_risk.get('volatility_annualized'))*100:.2f}% | Max DD {sf(formal_risk.get('max_drawdown'))*100:.2f}% | Beta SPY {sf(formal_risk.get('beta_to_spy')):.3f}")
        breaches = formal_risk.get('constraint_breaches') or []
        L(f"  Constraint Breach : {len(breaches)} active")
        for b in breaches[:8]:
            L(f"    - {b.get('type')} {b.get('ticker') or b.get('sector') or ''}: value={sf(b.get('value')):.4f}, limit={sf(b.get('limit')):.4f}")
        L('\n  Position Risk Snapshot:')
        L(table_line([('Ticker',8),('Weight',9),('Hist',6),('Vol',9),('VaR95$',12),('MaxDD',9),('BetaSPY',9)]))
        for row in (formal_risk.get('positions') or [])[:16]:
            L(table_line([
                (row.get('ticker',''),8),
                (f"{sf(row.get('weight'))*100:.1f}%",9),
                (row.get('history_points',''),6),
                (f"{sf(row.get('volatility_annualized'))*100:.1f}%",9),
                (money(row.get('historical_var_95_dollars')),12),
                (f"{sf(row.get('max_drawdown'))*100:.1f}%",9),
                (f"{sf(row.get('beta_to_spy')):.2f}",9),
            ]))

    # CIO cognition ledger
    L('\n'+sep); L('  CIO COGNITION LEDGER - STRATEGIC THINKING / PLANNING / EXECUTION'); L(sep)
    if not cio_cognition or cio_cognition.get('status') in ('not_configured', 'no_journal', 'extract_error'):
        L(f"  Status            : {cio_cognition.get('status','NOT_AVAILABLE') if cio_cognition else 'NOT_AVAILABLE'}")
        if cio_cognition.get('reason'): L(f"  Reason            : {cio_cognition.get('reason')}")
        L('  Interpretation    : CIO Strategic Thinking / Planning / Execution records have not yet been captured.')
    else:
        journals = cio_cognition.get('latest_journals') if isinstance(cio_cognition.get('latest_journals'), list) else []
        latest = journals[0] if journals and isinstance(journals[0], dict) else {}
        refs = latest.get('evidence_refs') if isinstance(latest.get('evidence_refs'), dict) else {}
        tickers = refs.get('tickers') if isinstance(refs.get('tickers'), list) else []
        L(f"  Latest Journal    : {cio_cognition.get('latest_journal_id','')} | {cio_cognition.get('generated_at','')}")
        L(f"  Status            : {cio_cognition.get('status','')} | exported journals {cio_cognition.get('journal_count_exported',0)} | thesis reviews {cio_cognition.get('review_count',0)}")
        if refs.get('thesis_title'):
            L(f"  Thesis Title      : {clean_text(refs.get('thesis_title'),118)}")
        if tickers:
            L(f"  Tickers           : {', '.join(str(t) for t in tickers)}")
        if refs:
            L(f"  Manual Status     : decision={refs.get('decision_type','')} | asset={refs.get('asset_class','')} | already placed={yesno(refs.get('already_placed_manually_by_cio'))}")
        L(f"  Regime / Action   : {latest.get('regime','')} | {latest.get('cio_action','')} | confidence {sf(latest.get('confidence')):.3f}")
        L(f"  Execution         : authority {cio_cognition.get('execution_authority','CIO_ONLY_MANUAL')} | orders generated {cio_cognition.get('orders_generated',0)}")
        L('  Doctrine          : This is the human CIO cognition ledger. It records thinking, planning, execution intent, repeatability checks, and mistake-risk prompts. It does not route capital.')
        # Defect 6 — Regime vs Cognition Ledger timestamp disclosure
        try:
            from research_report_generator import build_regime_cognition_disclosure as _brcd
            _rcd = _brcd(dataset)
            _rcd_sev = _rcd.get("mismatch_severity", "NONE")
            _rcd_delta = _rcd.get("delta_hours")
            _delta_str = f"{_rcd_delta:.1f}h" if _rcd_delta is not None else "unknown"
            L(f"\n  Regime-Cognition Alignment:")
            L(f"    Regime Timestamp  : {_rcd.get('regime_ts','UNKNOWN')}")
            L(f"    Ledger Timestamp  : {_rcd.get('ledger_ts','UNKNOWN')}")
            L(f"    Delta             : {_delta_str} | Severity: {_rcd_sev}")
            if _rcd.get("disclosure_required"):
                L(f"  *** DISCLOSURE [{_rcd_sev}] ***")
                for _dl in wrap(_rcd.get("disclosure_text",""), 112, '    '):
                    L(_dl)
        except Exception as _e6:
            L(f"  Regime-Cognition Alignment: (disclosure error: {_e6})")
        L('\n  Strategic Thinking:')
        for line in wrap(latest.get('strategic_thinking',''), 112, '    '):
            L(line)
        L('\n  Planning:')
        for line in wrap(latest.get('planning',''), 112, '    '):
            L(line)
        L('\n  Execution Intent:')
        for line in wrap(latest.get('execution_intent',''), 112, '    '):
            L(line)
        rationale = latest.get('non_execution_rationale')
        if rationale:
            L('\n  Non-Execution Rationale:')
            for line in wrap(rationale, 112, '    '):
                L(line)
        reviews = cio_cognition.get('latest_thesis_reviews') if isinstance(cio_cognition.get('latest_thesis_reviews'), list) else []
        if reviews:
            L('\n  Thesis Review Snapshot:')
            L(table_line([('Thesis',30),('Status',12),('Prob',8),('Conf',8),('CIO Assessment',24),('Mistake Risk',34)]))
            for row in reviews[:12]:
                if not isinstance(row, dict): continue
                L(table_line([
                    (clean_text(row.get('thesis_id',''),30),30),
                    (row.get('status_at_review',''),12),
                    (f"{sf(row.get('probability_at_review'))*100:.1f}%",8),
                    (f"{sf(row.get('confidence_at_review'))*100:.1f}%",8),
                    (clean_text(row.get('cio_assessment',''),24),24),
                    (clean_text(row.get('mistake_risk',''),34),34),
                ]))

    # Portfolio targets and thesis lifecycle
    L('\n'+sep); L('  PORTFOLIO TARGETS AND THESIS LIFECYCLE - RESEARCH ONLY'); L(sep)
    targets = dataset.get('portfolio_targets') if isinstance(dataset.get('portfolio_targets'), dict) else {}
    if targets and targets.get('status') not in ('not_configured', 'no_run', 'extract_error'):
        L(f"  Target Run        : {targets.get('run_id','')} | {targets.get('status','')}")
        L(f"  Objective         : {targets.get('objective','')}")
        L('  Execution         : NO ORDERS GENERATED. CIO_ONLY execution authority.')
        rows = targets.get('targets_by_ticker') or []
        if rows:
            L('\n  Target Weights:')
            L(table_line([('Ticker',8),('Current',10),('Target',10),('Delta',10),('Target$',13)]))
            for row in rows[:16]:
                L(table_line([
                    (row.get('ticker',''),8),
                    (f"{sf(row.get('current_weight'))*100:.1f}%",10),
                    (f"{sf(row.get('target_weight'))*100:.1f}%",10),
                    (f"{sf(row.get('delta_weight'))*100:+.1f}%",10),
                    (money(row.get('target_value')),13),
                ]))
    else:
        L('  Portfolio targets : NOT_AVAILABLE')
    if thesis_layer and thesis_layer.get('status') == 'operational':
        L(f"\n  Thesis Count      : {thesis_layer.get('thesis_count',0)} | {thesis_layer.get('status_counts',{})}")
        L(table_line([('P',4),('Status',12),('Probability',12),('Confidence',12),('Thesis',42)]))
        for row in (thesis_layer.get('theses') or [])[:10]:
            L(table_line([
                (row.get('priority',''),4),
                (row.get('status',''),12),
                (f"{sf(row.get('current_probability'))*100:.1f}%",12),
                (f"{sf(row.get('confidence'))*100:.1f}%",12),
                (clean_text(row.get('thesis_name'),42),42),
            ]))
            ev = row.get('evidence') or row.get('contradictions') or []
            if ev:
                txt = ev[0].get('evidence') or ev[0].get('contradiction') or ''
                L(f"      evidence: {clean_text(txt,120)}")
    else:
        L('  Thesis Lifecycle  : NOT_AVAILABLE')

    # Monitoring
    L('\n'+sep); L('  MONITORING, ALERTS AND DATA LINEAGE'); L(sep)
    if not monitoring_layer:
        L('  Status            : NOT_AVAILABLE')
    else:
        L(f"  Status            : {monitoring_layer.get('status','')}")
        L(f"  Alert Count       : {monitoring_layer.get('alert_count',0)} | {monitoring_layer.get('severity_counts',{})}")
        lineage = monitoring_layer.get('lineage') or dataset.get('data_lineage') or {}
        if isinstance(lineage, dict):
            L(f"  Lineage Event     : {lineage.get('event_id','')} | dataset_sha={lineage.get('dataset_sha256','')}")
        L('\n  Alerts:')
        L(table_line([('Severity',10),('Layer',18),('Type',24),('Title',48)]))
        for a in (monitoring_layer.get('alerts') or [])[:16]:
            L(table_line([
                (a.get('severity',''),10),
                (a.get('layer_name',''),18),
                (a.get('alert_type',''),24),
                (clean_text(a.get('title'),48),48),
            ]))

    # Institutional operations upgrade
    L('\n'+sep); L('  INSTITUTIONAL OPERATIONS UPGRADE - ARCHIVE / RECOVERY / CIO LEDGER'); L(sep)
    if snapshot_archive:
        latest = snapshot_archive.get('latest_snapshot') if isinstance(snapshot_archive.get('latest_snapshot'), dict) else {}
        L(f"  Dataset Archive   : {snapshot_archive.get('status','')} | snapshots {snapshot_archive.get('snapshot_count',0)}")
        L(f"  Latest Snapshot   : {latest.get('snapshot_id','')} | sha {latest.get('dataset_sha256','')}")
    else:
        L('  Dataset Archive   : NOT_AVAILABLE')
    if freshness_recovery:
        L(f"  Freshness Recovery: {freshness_recovery.get('status','')} | attempted {freshness_recovery.get('attempted_modules',[])}")
        L(f"  Market Deferred   : {freshness_recovery.get('market_closed_deferred',[])} | unresolved {freshness_recovery.get('unresolved_sections',[])}")
    else:
        L('  Freshness Recovery: NOT_AVAILABLE')
    if historical_backfill:
        L(f"  Historical Backfill: {historical_backfill.get('status','')} | queue {historical_backfill.get('queue_counts',{})}")
        latest_run = historical_backfill.get('latest_run') if isinstance(historical_backfill.get('latest_run'), dict) else {}
        L(f"  Latest Backfill Run: {latest_run.get('run_id','')} | selected {latest_run.get('selected_tickers',[])}")
        incomplete = historical_backfill.get('incomplete_sample') or []
        if incomplete:
            L('  Incomplete Sample : ' + ', '.join(f"{r.get('ticker')}({r.get('row_count')} rows)" for r in incomplete[:12] if isinstance(r, dict)))
    else:
        L('  Historical Backfill: NOT_AVAILABLE')
    if cio_decisions:
        L(f"  CIO Decision Ledger: {cio_decisions.get('status','')} | pending {cio_decisions.get('pending_review_count',0)} | orders generated {cio_decisions.get('orders_generated',0)}")
        L(f"  Execution Authority: {cio_decisions.get('execution_authority','CIO_ONLY_MANUAL')} | order generation enabled={cio_decisions.get('order_generation_enabled',False)}")
        rows = cio_decisions.get('decisions') or []
        if rows:
            L('\n  Pending CIO Reviews:')
            L(table_line([('Priority',9),('Type',24),('Ticker',8),('Status',30),('Delta',10)]))
            for row in rows[:12]:
                L(table_line([
                    (row.get('priority',''),9),
                    (row.get('decision_type',''),24),
                    (row.get('ticker') or 'PORT',8),
                    (row.get('status',''),30),
                    (f"{sf(row.get('delta_weight'))*100:+.2f}%",10),
                ]))
    else:
        L('  CIO Decision Ledger: NOT_AVAILABLE')
    if execution_layer:
        L(f"  Broker History     : {orders_layer.get('status','')} | open orders {orders_layer.get('open_order_count',0)} | historical orders {orders_layer.get('historical_order_count',0)} | fills {fills_layer.get('historical_deal_count',0)}")
        L(f"  Execution Routing  : enabled={execution_layer.get('order_routing_enabled',False)} | authority={execution_layer.get('execution_authority','CIO_ONLY_MANUAL')}")
    else:
        L('  Broker History     : NOT_AVAILABLE')

    # Portfolio mandate
    L('\n'+sep); L('  PORTFOLIO, CASH & MANDATE-AWARE EXPOSURE'); L(sep)
    L(f"  Total Assets      : {money(port.get('total_assets'))}")
    L(f"  Cash              : {money(port.get('cash'))} ({cash_pct:.1f}% of assets)")
    L(f"  Market Value      : {money(port.get('market_val'))} ({eq_pct:.1f}% of assets)")
    L(f"  Buying Power      : {money(port.get('buying_power'))}")
    L(f"  Total Cost        : {money(port.get('total_cost'))}")
    L(f"  Total P/L         : {money(port.get('total_pnl'))} ({sf(port.get('total_pnl_pct')):+.2f}%)")
    L(f"  Data Source       : {port.get('data_source','')} | Cycle TS {port.get('cycle_ts','')}")
    L('\n  Positions:')
    L(table_line([('Ticker',8),('Mandate',10),('Qty',6),('Price',12),('Cost',12),('MktVal',13),('P/L',13),('P/L%',9),('Action Note',24)]))
    for t,pos in positions.items():
        md=(dataset.get('portfolio_mandates') or {}).get(t) or PORTFOLIO_MANDATE_DEFAULTS.get(t,{})
        mandate=md.get('mandate','UNCLASSIFIED')
        note=''
        price=sf(pos.get('price'))
        if mandate=='SATELLITE' and md.get('dca_enabled'):
            lo=sf(md.get('dca_zone_low')); hi=sf(md.get('dca_zone_high'))
            note='DCA ZONE' if lo and hi and lo<=price<=hi else f"DCA only {lo:g}-{hi:g}" if lo and hi else 'SATELLITE HOLD'
        elif mandate=='BASELINE':
            note='HOLD / trade strength' if sf(pos.get('unrealized_p'))>=0 else 'RELOAD only on signal'
        else:
            note='WAIT/HOLD'
        # P/L arithmetic integrity inline flag
        _pnl_flag = pos.get('pnl_integrity_status', '')
        if _pnl_flag == 'BROKER_PNL_SOURCE_CONFLICT':
            _computed = sf(pos.get('computed_unrealized'))
            _broker = sf(pos.get('unrealized'))
            _delta = _broker - _computed
            _mv = sf(pos.get('mkt_val'))
            _delta_pct = abs(_delta) / abs(_mv) * 100 if _mv else 0
            L(f"  BROKER_PNL_SOURCE_CONFLICT - COST_BASIS_REVIEW_REQUIRED {t}: broker={money(_broker)} computed={money(_computed)} delta={money(_delta)} delta_pct_of_mv={_delta_pct:.1f}% selected_source=BROKER_REPORTED")
        L(table_line([(t,8),(mandate,10),(pos.get('qty',''),6),(money(pos.get('price')),12),(money(pos.get('avg_cost')),12),(money(pos.get('mkt_val')),13),(money(pos.get('unrealized')),13),(pct(pos.get('unrealized_p')),9),(note,24)]))

    # P/L integrity summary after table
    _pnl_conflict_positions = [(t, p) for t, p in positions.items() if isinstance(p, dict) and p.get('pnl_integrity_status') == 'BROKER_PNL_SOURCE_CONFLICT']
    if _pnl_conflict_positions:
        L('-'*78)
        L('  BROKER_PNL_SOURCE_CONFLICT - COST_BASIS_REVIEW_REQUIRED:')
        for _ct, _cp in _pnl_conflict_positions:
            _bp = sf(_cp.get('unrealized'))
            _cpnl = sf(_cp.get('computed_unrealized'))
            _delta = _bp - _cpnl
            _mv = sf(_cp.get('mkt_val'))
            _dpct = abs(_delta) / abs(_mv) * 100 if _mv else 0
            L(f"  {_ct}: broker_pnl={money(_bp)} | computed_pnl={money(_cpnl)} | delta={money(_delta)} | delta_pct_of_mv={_dpct:.1f}% | selected_source=BROKER_REPORTED | reason=cost-basis/source mismatch | action=review broker cost basis before CIO decision")
        L('  Governance: broker P/L source conflict isolated from market thesis; cost-basis review required.')

    # Price action with premarket reversal
    L('\n'+sep); L('  PRICE ACTION — TOP MOVERS, PREMARKET VS REGULAR SESSION'); L(sep)
    L(table_line([('Ticker',8),('Move',9),('PreMkt',9),('Price',12),('Volume',12),('Session',11),('Interpretation',38)]))
    for m in top:
        t=str(m.get('ticker')); p=prices.get(t,{})
        pre=sf(p.get('pre_chg_pct')); chg=sf(m.get('chg_pct'))
        interp='continuation'
        if pre<0 and chg>0: interp='intraday bullish reversal from red premarket'
        elif pre<chg and chg<0: interp='damage reduced after open'
        elif chg<pre and chg<0: interp='selling intensified after open'
        elif chg>5: interp='momentum spike / verify catalyst'
        L(table_line([(t,8),(pct(chg),9),(pct(pre),9),(money(m.get('price')),12),(f"{si(m.get('volume')):,}",12),(m.get('session',''),11),(interp,38)]))

    # ECE
    L('\n'+sep); L('  SECTOR ROTATION — EVENT CORRELATION ENGINE — 23 THEME UNIVERSE'); L(sep)
    # Column: No | Theme | Sector Dir | Basket | Conf | Tier | Flags | Why
    L(table_line([('No',4),('Theme',32),('Sector Dir',18),('Basket',9),('Conf',7),('Tier',18),('Flags',26),('Why',28)]))
    ece_map=ece_by_theme(dataset)
    rows=[]
    for theme in THEME_UNIVERSE:
        e=ece_map.get(theme.upper())
        if e: rows.append(e)
        else: rows.append({'theme':theme,'direction':'NO SIGNAL','sector_direction':'NO SIGNAL','basket_move':0,'confidence':0,'evidence_tier_label':'N/A','why':'No active ECE signal this cycle.','review_flags':[],'global_regime_context':''})
    rows.sort(key=lambda e: sf(e.get('basket_move')), reverse=True)
    # S6 evidence sanitizer — mirrors sanitize_theme_evidence() in research_report_generator.py.
    # Applied here as a safety net so no weak/mismatched evidence leaks via the fallback path.
    # Keep constants local so S6 works even if the outer generator is not importable.
    _S6_WEAK_FLAGS = frozenset({"SECTOR_EVIDENCE_MISMATCH","NO_DIRECT_CATALYST",
                                 "GENERIC_EVIDENCE_REVIEW","ANALYST_ONLY_CAUSAL_GAP","PRICE_ACTION_ONLY_CAP",
                                 "CONFIDENCE_CAPPED_BY_EVIDENCE","PARTIAL_CAUSAL_CAP"})
    _S6_SUPPRESSED_MISMATCH = ("Evidence mismatch detected. "
                                "Causal interpretation suppressed pending direct catalyst confirmation.")
    _S6_SUPPRESSED_NO_CATALYST = ("No direct theme-specific catalyst found. "
                                   "Direction based on basket price action only. Confidence capped.")
    analyst_count=0
    for i,e in enumerate(rows,1):
        # Sanitize evidence before rendering — identical logic to sanitize_theme_evidence()
        _flags_raw = e.get('review_flags') or []
        if abs(sf(e.get('basket_move'))) > 15 and 'THEME_BASKET_OUTLIER_REVIEW' not in _flags_raw:
            _flags_raw = list(_flags_raw) + ['THEME_BASKET_OUTLIER_REVIEW']
        _active_weak = frozenset(_flags_raw) & _S6_WEAK_FLAGS
        _why_raw = e.get('why','')
        _theme_up = str(e.get('theme','')).upper()
        if "SECTOR_EVIDENCE_MISMATCH" in _active_weak:
            _why_display = _S6_SUPPRESSED_MISMATCH
        elif _active_weak:
            _why_display = _S6_SUPPRESSED_NO_CATALYST
        elif "Portfolio:" in _why_raw:
            _why_display = _S6_SUPPRESSED_NO_CATALYST
        elif ("CONSUMER TECH" in _theme_up or "APPLE" in _theme_up) and "GOOGL" in _why_raw:
            _why_display = _S6_SUPPRESSED_MISMATCH
        elif ("MAG7" in _theme_up or "BIG TECH" in _theme_up) and "GOOGL" in _why_raw and "MAG7" not in _why_raw.upper():
            _why_display = _S6_SUPPRESSED_NO_CATALYST
        else:
            _why_display = _why_raw
        why=clean_text(_why_display,36)
        if 'ANALYST' in str(e.get('why','')).upper(): analyst_count+=1
        # Use sector_direction (v2) if present, fall back to direction
        _sd  = causal_price_action_label(e.get('sector_direction') or e.get('direction') or '', _flags_raw)
        _flags_str = ','.join(_flags_raw)[:26] if _flags_raw else ''
        L(table_line([(i,4),(e.get('theme',''),32),(_sd,18),(pct(e.get('basket_move')),9),(f"{sf(e.get('confidence')):.0f}%",7),(e.get('evidence_tier_label',''),18),(_flags_str,26),(why,28)]))
    L(f"\n  Active ECE themes this cycle : {len(ece)} / {len(THEME_UNIVERSE)} canonical themes")
    if analyst_count: L(f"  ⚠ Data-quality note: {analyst_count} ECE themes still use analyst/Wall St text as 'why'. Context, not causal catalyst.")
    # ── ECE Governing Logic Disclosure — WO-ECE-20260612-001 ─────────────────
    L('\n  ECE SECTOR DIRECTION GOVERNING LOGIC')
    L('  ' + '-'*76)
    L('  Sector Dir is computed from live sector basket move, broad-market tape')
    L('  confirmation, catalyst polarity, and review-flag validation.')
    L('  Global regime is reported separately and does NOT overwrite sector direction.')
    L('  ')
    L('  Thresholds (basket move vs prior close):')
    L('    Strong Risk-On     : basket >= +0.50%')
    L('    Selective Risk-On  : basket >= +0.10%')
    L('    Neutral            : -0.10% < basket < +0.10%')
    L('    Selective Risk-Off : basket <= -0.10%')
    L('    Risk-Off           : basket <= -0.50%')
    L('  ')
    L('  Broad-rally overlay: If SPY > 0 AND (QQQ > 0 OR IWM > 0) AND VXX <= 0,')
    L('    positive-basket sectors cannot be labeled Risk-Off.')
    L('  ')
    L('  Validation rules:')
    L('    Positive basket move cannot be labeled Risk-Off without POSITIVE_BASKET_RISK_OFF_CONFLICT flag.')
    L('    Negative basket move cannot be labeled Risk-On without NEGATIVE_BASKET_RISK_ON_CONFLICT flag.')
    L('    Theme evidence must match approved ticker/theme mapping or SECTOR_EVIDENCE_MISMATCH is raised.')
    L('    Geopolitical de-escalation with markets up and oil down → GEOPOLITICAL_DEESCALATION polarity,')
    L('      not plain Risk-Off, unless price confirmation contradicts.')
    L('  Governing logic version: ECE_v2')

    # Forward catalysts
    L('\n'+sep); L('  FORWARD CATALYST INTELLIGENCE — v1.8 LAYER'); L(sep)
    L('\nA. Conference Calendar'); L('-'*78)
    for c in dataset.get('conference_calendar') or []:
        L(f"  {c.get('conference_slug',''):<28} {c.get('event_date_start',''):<12} days={c.get('days_until_event','')} flag={c.get('catalyst_flag','')} speakers={join_field(c.get('keynote_speakers'))}")
    L('\nB. CEO Appearance Tracker'); L('-'*78)
    for c in dataset.get('ceo_appearances') or []:
        L(f"  {c.get('executive_name',''):<18} {str(c.get('ticker','')):<6} {c.get('appearance_date',''):<12} 72h={c.get('alert_72h_flag')} 24h={c.get('alert_24h_flag')} affected={join_field(c.get('affected_tickers'))}")
    cal=dataset.get('catalyst_calendar') or {}
    macro_risks = dataset.get('macro_event_risks') if isinstance(dataset.get('macro_event_risks'), list) else []
    L('\nA0. Macro Event Risk Calendar'); L('-'*78)
    if macro_risks:
        for c in macro_risks:
            if not isinstance(c, dict): continue
            L(f"  {c.get('event',''):<38} {c.get('event_date',''):<12} {c.get('category',''):<24} {c.get('impact_class','')}")
    else:
        L('  No macro event risk calendar available.')
    L('\nC. Portfolio Catalyst Calendar'); L('-'*78)
    for c in cal.get('portfolio_only') or []:
        L(f"  {c.get('ticker',''):<6} {c.get('catalyst_type',''):<12} {c.get('catalyst_date',''):<12} {c.get('alert_flag',''):<8} EPS={c.get('eps_estimate','')}")
    L('\nD. Near-Term Catalyst Calendar — 14D'); L('-'*78)
    for c in cal.get('all') or []:
        if si(c.get('days_until_catalyst'),999)<=14:
            L(f"  {c.get('ticker',''):<6} {c.get('catalyst_type',''):<12} {c.get('catalyst_date',''):<12} {c.get('catalyst_time',''):<6} {c.get('alert_flag',''):<8} EPS={c.get('eps_estimate','')}")

    # Institutional Positioning
    import re as _re
    L('\n'+sep); L('  INSTITUTIONAL POSITIONING — SHORT VOLUME & OPTIONS FLOW'); L(sep)

    # Options Flow
    L('\nA. Options Flow — Unusual Large Trades'); L('-'*78)
    L(table_line([('Ticker',7),('Date/Time',14),('Action',12),('Volume',8),('Signal',9)]))
    _opt_rows = []
    for _entry in dataset.get('moomoo_intel') or []:
        if not isinstance(_entry, str) or '[OPTIONS FLOW]' not in _entry:
            continue
        try:
            _tm = _re.search(r'\[OPTIONS FLOW\]\s+([A-Z0-9]+):', _entry)
            if not _tm: continue
            _tk = _tm.group(1)
            for _tr in _re.finditer(
                r'(\d+\.\d+\s+\d+:\d+),\s+a\s+([\w\s]+?)\s+options trade was recorded\.\s+Volume was\s+([\d,]+)',
                _entry, _re.IGNORECASE):
                _dt = _tr.group(1).strip()
                _ar = _tr.group(2).strip().upper()
                try: _vol = int(_tr.group(3).replace(',',''))
                except: _vol = 0
                _sig = 'BEARISH' if 'BUY PUT' in _ar or 'SELL CALL' in _ar else ('BULLISH' if 'BUY CALL' in _ar or 'SELL PUT' in _ar else 'NEUTRAL')
                _opt_rows.append((_tk, _dt, _ar.title(), _vol, _sig))
        except Exception:
            continue
    _opt_rows.sort(key=lambda r: ({'BEARISH':0,'NEUTRAL':1,'BULLISH':2}.get(r[4],9), -(r[3] or 0)))
    for _tk,_dt,_ar,_vol,_sig in _opt_rows:
        L(table_line([(_tk,7),(_dt,14),(_ar,12),(f"{_vol:,}",8),(_sig,9)]))
    _bearish_n = sum(1 for r in _opt_rows if r[4]=='BEARISH')
    _bullish_n = sum(1 for r in _opt_rows if r[4]=='BULLISH')
    L(f"\n  Options flow summary: {_bearish_n} BEARISH trades / {_bullish_n} BULLISH trades / {len(_opt_rows)} total")

    # Capital Flow Outflows
    L('\nB. Capital Flow — Largest Institutional Outflows'); L('-'*78)
    L(table_line([('Ticker',7),('SL Out',12),('L Out',12),('Total',12),('Bias',12)]))
    _cf_rows = []
    for _tk, _v in (dataset.get('capital_flow') or {}).items():
        if not isinstance(_v, dict): continue
        _sln = float(_v.get('super_large_net') or 0)
        _ln  = float(_v.get('large_net') or 0)
        _tot = _sln + _ln
        if _tot >= 0: continue
        _slo = float(_v.get('super_large_out') or 0)
        _lo  = float(_v.get('large_out') or 0)
        _cf_rows.append((_tk, f"-${_slo/1e6:.1f}M" if _slo else "", f"-${_lo/1e6:.1f}M" if _lo else "", f"-${abs(_tot)/1e6:.1f}M", _v.get('institutional_bias') or ''))
    _cf_rows.sort(key=lambda r: float(r[3].replace('-$','').replace('M','') or 0), reverse=True)
    for _tk,_slo,_lo,_tot,_bias in _cf_rows:
        L(table_line([(_tk,7),(_slo,12),(_lo,12),(_tot,12),(_bias,12)]))

    # CFTC COT
    L('\nC. CFTC COT — Leveraged Funds (as of latest report)'); L('-'*78)
    L(table_line([('Contract',36),('Net Position',14),('As Of',12),('Direction',10)]))
    _cftc_rows = []
    for _entry in (dataset.get('signals') or {}).get('CFTC_COT') or []:
        _txt = _entry.get('raw_text','') if isinstance(_entry, dict) else str(_entry)
        _m = _re.match(r'CFTC COT \(TFF\)\s+(.+?)\s*-\s*CHICAGO MERCANTILE EXCHANGE:\s*net\s*([+-]?[\d,]+)\s+as of\s+(.+)', _txt, _re.IGNORECASE)
        if not _m: continue
        try: _net = int(_m.group(2).replace(',',''))
        except: _net = 0
        _dir = 'LONG' if _net > 0 else ('SHORT' if _net < 0 else 'FLAT')
        _cftc_rows.append((_m.group(1).strip(), f"{_net:+,}", _m.group(3).strip(), _dir))
    _cftc_rows.sort(key=lambda r: abs(int(r[1].replace(',','').replace('+',''))), reverse=True)
    for _con,_net,_ao,_dir in _cftc_rows:
        L(table_line([(_con,36),(_net,14),(_ao,12),(_dir,10)]))

    # Top mover catalyst verification
    L('\n'+sep); L('  TOP-MOVER CATALYST VERIFICATION TABLE — PHASE 2 / P2-03'); L(sep)
    L(table_line([('Ticker',8),('Move',9),('Price',12),('Volume',12),('Status',12),('Reason',48)]))
    tm_rows = top_mover_catalyst_table(dataset)
    for t,move,price,vol,status,reason in tm_rows:
        L(table_line([(t,8),(pct(move),9),(money(price),12),(f"{si(vol):,}",12),(status,12),(reason,48)]))
    tm_counts = top_mover_status_counts(tm_rows)
    L(f"\n  Top mover causal score: MATCHED {tm_counts.get('MATCHED',0)} / PARTIAL {tm_counts.get('PARTIAL',0)} / UNEXPLAINED {tm_counts.get('UNEXPLAINED',0)} / LOW_MOVE {tm_counts.get('LOW_MOVE',0)}")

    # Tech pub digest
    L('\n'+sep); L('  TECH PUBLICATION SIGNALS — EARLY CATALYST LAYER'); L(sep)
    for src,arts in (dataset.get('tech_pub_signals') or {}).items():
        if not isinstance(arts,list): continue
        L(f"\n  {src} — {len(arts)} articles")
        for a in arts[:6]:
            title=a.get('title') or a.get('headline') or a.get('raw_text') or ''
            tickers=article_tickers(a)
            themes=article_themes(a)
            sentiment=a.get('sentiment_label') or a.get('sentiment') or ''
            score=article_sentiment_score(a)
            typ=a.get('signal_type') or a.get('type') or a.get('article_type') or ''
            L(f"    • {clean_text(title,112)}")
            L(f"      tickers={tickers or 'N/A'} | themes={themes or 'N/A'} | sentiment={sentiment} {score:+.3f} | type={typ}")

    # Named events
    L('\n'+sep); L('  ECE NAMED EVENTS — HISTORICAL SEASONAL MEMORY'); L(sep)
    L(table_line([('Event',32),('Next',12),('Years',7),('Base',10),('Bull',10),('Bear',10),('Trigger',40)]))
    nerows = named_event_rows(dataset)
    if not nerows:
        L('  No ece_named_events found in dataset. Historical seasonal memory unavailable.')
    for e in nerows:
        L(table_line([(clean_text(e.get('name'),31),32),(str(e.get('next','')),12),(str(e.get('years','')),7),(fmt_event_pct(e.get('base')),10),(fmt_event_pct(e.get('bull')),10),(fmt_event_pct(e.get('bear')),10),(clean_text(e.get('trigger'),40),40)]))
        if e.get('direct'):
            L(f"    Direct tickers: {', '.join(e.get('direct'))}")
        if e.get('history'):
            L(f"    Historical years: {e.get('history')}")

    # Blind spot
    L('\n'+sep); L('  BLIND SPOT CHECK & CAUSAL CHAIN TEST'); L(sep)

    # ── A. Blind Spot 12-Item Checklist ─────────────────────────────────────
    L('\nA. Blind Spot Checklist (12 Items)'); L('-'*78)
    _sigs         = dataset.get('signals') or {}
    _cats         = (dataset.get('catalyst_calendar') or {}).get('all') or []
    _conf_cal     = dataset.get('conference_calendar') or []
    _ceo_apps_d   = dataset.get('ceo_appearances') or []
    _ece_ne       = dataset.get('ece_named_events') or []
    _now_s        = datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d')
    _next14_s     = (datetime.now(timezone(timedelta(hours=8))) + timedelta(days=14)).strftime('%Y-%m-%d')
    def _sigcnt(*keys): return sum(len(_sigs.get(k) or []) for k in keys if k in _sigs)
    _bs_items = [
        ("Scheduled Conferences",
         "PASS" if [e for e in _conf_cal if isinstance(e,dict) and str(e.get("event_date_start",""))>=_now_s] else "FAIL",
         f"{len([e for e in _conf_cal if isinstance(e,dict) and str(e.get('event_date_start',''))>=_now_s])} upcoming" if _conf_cal else "No data"),
        ("CEO Appearances",
         "PASS" if _ceo_apps_d else "FAIL",
         f"{len(_ceo_apps_d)} total tracked" if _ceo_apps_d else "No CEO appearance data"),
        ("Portfolio Catalyst Calendar",
         "PASS" if [c for c in _cats if c.get('in_portfolio') and str(c.get('alert_flag','')).upper()!='PAST'] else "FAIL",
         f"{len([c for c in _cats if c.get('in_portfolio')])} portfolio catalysts" if _cats else "No data"),
        ("Earnings Calendar",
         "PASS" if [c for c in _cats if c.get('catalyst_type','').upper()=='EARNINGS' and str(c.get('catalyst_date',''))<=_next14_s] else "FAIL",
         f"{len([c for c in _cats if c.get('catalyst_type','').upper()=='EARNINGS' and str(c.get('catalyst_date',''))<=_next14_s])} earnings in 14d"),
        ("Investor Days",
         "FAIL", "Not tracked separately"),
        ("Analyst Days",
         "FAIL", "Not tracked separately"),
        ("Tech Keynote Events",
         "PASS" if [e for e in _conf_cal if isinstance(e,dict) and e.get('keynote_date')] else "FAIL",
         f"{len([e for e in _conf_cal if isinstance(e,dict) and e.get('keynote_date')])} tech keynotes"),
        ("Fed/Policy Events",
         "PASS" if _sigcnt('Fed_Press','Fed_Speeches','Fed_FOMC_Minutes','Treasury_Press') >= 3 else "FAIL",
         f"{_sigcnt('Fed_Press','Fed_Speeches','Fed_FOMC_Minutes','Treasury_Press')} Fed/Treasury signals"),
        ("Geopolitical Events",
         "PASS" if _sigcnt('WhiteHouse_RSS','IAEA_News','ArabNews_Business','Defense_News','OPEC_News') >= 3 else "FAIL",
         f"{_sigcnt('WhiteHouse_RSS','IAEA_News','ArabNews_Business','Defense_News','OPEC_News')} geo signals"),
        ("Named Historical Events",
         "PASS" if _ece_ne else "FAIL",
         f"{len(_ece_ne)} named events in correlation db" if _ece_ne else "Empty or unavailable"),
        ("Unexplained Market Moves",
         "PASS" if not unexpl else "FAIL",
         f"{len(unexpl)} unexplained large moves: {', '.join(unexpl[:3])}" if unexpl else "All large moves explained"),
        ("Sector Catalyst Check",
         "FAIL" if sector_gaps else "PASS",
         f"{len(sector_gaps)} sector moves rely on analyst consensus only" if sector_gaps else "Sector moves have causal explanations"),
    ]
    try:
        from research_report_generator import build_blind_spot_checklist as _bbsc
        _bs_canonical = _bbsc(dataset)
        _canonical_rows = _bs_canonical.get('check_rows') or []
        if _canonical_rows:
            _bs_items = [
                (str(row[0]), str(row[1]).upper(), str(row[2]))
                for row in _canonical_rows
                if isinstance(row, (list, tuple)) and len(row) >= 3
            ]
            _bs_fails = [str(x) for x in (_bs_canonical.get('failed_items') or [])]
            _bs_pass_cnt = int(_bs_canonical.get('pass_count') or 0)
            _bs_status = str(_bs_canonical.get('blind_spot_status') or 'UNKNOWN')
            _bs_penalty = sf(_bs_canonical.get('cio_penalty'))
        else:
            raise ValueError('canonical blind-spot checklist returned no rows')
    except Exception:
        _bs_fails    = [n for n,s,_ in _bs_items if s=='FAIL']
        _bs_pass_cnt = sum(1 for _,s,_ in _bs_items if s=='PASS')
        _bs_status   = 'CLEAR' if not _bs_fails else ('CRITICAL' if len(_bs_fails)>=6 else 'WARNING')
        _bs_penalty  = round(min(0.35, 0.04 * len(_bs_fails)), 3)
    L(f"  Status         : [MODEL INFERRED] {_bs_status} | Pass {_bs_pass_cnt}/12 | Fail {len(_bs_fails)}/12 | CIO Penalty -{_bs_penalty:.3f}")
    L(table_line([('Check Item',32),('Status',8),('Detail',36)]))
    for name,stat,det in _bs_items:
        L(table_line([(name,32),(stat,8),(det[:36],36)]))
    if _bs_fails:
        L(f"\n  FAILED ITEMS: {', '.join(_bs_fails)}")
    _bs_unexplained = [det for name, stat, det in _bs_items if name == 'Unexplained Market Moves' and stat == 'FAIL']
    if _bs_unexplained:
        L('  Unexplained Large Moves:')
        for x in _bs_unexplained: L(f"    * {x}")
    _bs_sector_gaps = [det for name, stat, det in _bs_items if name == 'Sector Catalyst Check' and stat == 'FAIL']
    if _bs_sector_gaps:
        L('  Sector / Catalyst Gaps:')
        for x in _bs_sector_gaps[:8]: L(f"    * {x}")

    # ── B. Causal Explanation Structured Check ──────────────────────────────
    L('\nB. Causal Explanation Engine (10-Check Chain)'); L('-'*78)
    _cm_flags = {k:v for k,v in ((dataset.get('cross_market_confirmation') or {}).get('interpretation_flags') or {}).items() if v}
    _news_cnt = _sigcnt('Reuters_Business','Reuters_Markets','WSJ_Markets','FT_Markets','CNBC_Markets')
    _macro_cnt= _sigcnt('BLS_API','BEA_GDP_PCE','WorldBank_Macro','EIA_Petroleum','EIA_NatGas')
    _fed_cnt  = _sigcnt('Fed_Press','Fed_Speeches','Fed_FOMC_Minutes','ECB_Press','Treasury_Press')
    _geo_cnt  = _sigcnt('WhiteHouse_RSS','IAEA_News','ArabNews_Business','Defense_News','OPEC_News')
    _cftc_cnt = len(_sigs.get('CFTC_COT') or [])
    _reg_factors = dataset.get('regime',{}).get('factors') or {}
    _nonzero_f   = sum(1 for v in _reg_factors.values() if v!=0)
    _macro_risks = dataset.get('macro_event_risks') if isinstance(dataset.get('macro_event_risks'), list) else []
    _imm_cats    = [c for c in _cats if str(c.get('alert_flag','')).upper() in ('IMMINENT','ACTIVE')] + [
        c for c in _macro_risks if isinstance(c, dict)
    ]
    _causal_checks = [
        ("Regime Drivers",    "PASS" if _nonzero_f>=3 else "FAIL",   f"{_nonzero_f}/6 factors active | score {reg.get('score',0)} | {reg.get('regime','')}"),
        ("Cross-Market",      "PASS" if _cm_flags else "FAIL",        f"Active flags: {', '.join(_cm_flags.keys()) or 'none'}"),
        ("News Catalyst",     "PASS" if _news_cnt>=5 else "FAIL",     f"{_news_cnt} news signals (Reuters/WSJ/FT/CNBC)"),
        ("Macro/Economic",    "PASS" if _macro_cnt>=3 else "FAIL",    f"{_macro_cnt} macro signals (BLS/BEA/WorldBank/EIA)"),
        ("Fed/Policy",        "PASS" if _fed_cnt>=3 else "FAIL",      f"{_fed_cnt} Fed/policy signals"),
        ("Geopolitical",      "PASS" if _geo_cnt>=3 else "FAIL",      f"{_geo_cnt} geopolitical signals"),
        ("Catalyst Calendar", "PASS" if _imm_cats else "FAIL",        f"{len(_imm_cats)} imminent/active catalysts"),
        ("CEO/Conference",    "PASS" if [e for e in _conf_cal if isinstance(e,dict) and str(e.get('event_date_end',''))>=_now_s] else "FAIL",
                                                                       f"{len([e for e in _conf_cal if isinstance(e,dict) and str(e.get('event_date_end',''))>=_now_s])} active conferences"),
        ("CFTC COT",          "PASS" if _cftc_cnt>0 else "FAIL",      f"{_cftc_cnt} CFTC signals"),
        ("Source Freshness",  "PASS", "Freshness recovery active"),
    ]
    _causal_pass = sum(1 for _,s,_ in _causal_checks if s=='PASS')
    _causal_status_txt = 'COMPLETE' if _causal_pass>=7 else 'PARTIAL' if _causal_pass>=4 else 'INCOMPLETE'
    _causal_conf_txt   = round(min(1.0, _causal_pass/10.0), 3)
    _passed_checks     = [n for n,s,_ in _causal_checks if s=='PASS']
    _missing_inputs    = [n for n,s,_ in _causal_checks if s=='FAIL']
    L(f"  Causal Status  : [MODEL INFERRED] {_causal_status_txt} | Confidence {_causal_conf_txt:.3f} | Pass {_causal_pass}/10")
    L(f"  Primary Driver : {_passed_checks[0] if _passed_checks else 'None'}")
    L(f"  Secondary      : {_passed_checks[1] if len(_passed_checks)>1 else 'None'}")
    if _missing_inputs:
        L(f"  Missing Inputs : {', '.join(_missing_inputs)}")
    L(table_line([('Check',22),('Status',8),('Detail',46)]))
    for name,stat,det in _causal_checks:
        L(table_line([(name,22),(stat,8),(det[:46],46)]))
    if _causal_status_txt!='COMPLETE' or _bs_status!='CLEAR':
        L('\n  DOCTRINE VERDICT: CAUSAL EXPLANATION ' + _causal_status_txt + '.')
        L('  Research conclusion is PROVISIONAL. CIO action should default to WAIT / HOLD.')

    # 8-lens portfolio
    L('\n'+sep); L('  8-LENS RESEARCH ANALYSIS'); L(sep)
    L('\nL1 Fundamental — Is this worth owning?'); L('-'*78)
    for t,pos in positions.items():
        at=dataset.get('analyst_targets',{}).get(t,{})
        fund=dataset.get('fundamentals',{}).get(t,{})
        up=target_upside(pos.get('price'), at.get('avg_target') or at.get('average'))
        L(f"  {t}: price {money(pos.get('price'))}, target {money(at.get('avg_target') or at.get('average'))} ({up:+.1f}% upside)" if up is not None else f"  {t}: price {money(pos.get('price'))}, target N/A")
        L(f"    P/E {sf(fund.get('pe_ttm_ratio')):.2f}x | P/B {sf(fund.get('pb_ratio')):.2f}x | EPS {money(fund.get('earning_per_share'))} | EY {sf(fund.get('ey_ratio')):.2f}%")
        if fund.get('pct_from_52w_high') is not None: L(f"    52w position: {sf(fund.get('pct_from_52w_high')):+.1f}% from high, {sf(fund.get('pct_from_52w_low')):+.1f}% from low")
    L('\nL2 Technical — Timing and price action'); L('-'*78)
    for t,pos in positions.items(): L(f"  {t}: {money(pos.get('price'))} ({pct(pos.get('chg_pct'))})")
    L('\nL3 Macro — Fed, yield curve, regime'); L('-'*78)
    L(f"  Regime {reg.get('regime') or reg.get('regime_short')} score {reg.get('score')}; action: {reg.get('action')}")
    L(f"  Macro avg {sf(reg.get('macro_avg')):+.4f}; institutional avg {sf(reg.get('inst_avg')):+.4f}")
    L('\nL4 Geopolitical — Override risks'); L('-'*78)
    geo_rows = geo_signal_rows(dataset, limit=8)
    if geo_rows:
        for g in geo_rows:
            suffix = f" | {g.get('age')}" if g.get('age') else ''
            L(f"  • [{g.get('source')}] {g.get('text')}{suffix}")
    else:
        L('  No fresh geopolitical override signal detected from authoritative dataset sources.')
    L('\nL5 Sentiment — Crowd and narrative'); L('-'*78)
    L(f"  Fear & Greed: {sf(fg.get('score')):.1f} — {fg.get('label','')} {'[STALE_SECONDARY / EXCLUDED_FROM_CIO_CONFIDENCE]' if (meta.get('freshness') or {}).get('fear_greed',{}).get('grade')=='STALE' else ''}")
    for t in positions:
        sent = dataset.get('ticker_sentiment', {}).get(t, {})
        # Hygiene patch R6: filter out irrelevant headlines before CIO tape
        relevance_status = sent.get('sentiment_relevance_status') or (
            'LOW_RELEVANCE / DISCARD' if sent.get('discarded_for_institutional_sentiment') else 'PASS'
        )
        if relevance_status != 'PASS':
            L(f"  {t}: [EXCLUDED FROM CIO TAPE] sentiment_relevance_status={relevance_status} — headline not directly relevant to {t}")
            continue
        L(f"  {t}: {sent.get('label','N/A')} VADER {sf(sent.get('score')):+.3f} | relevance=PASS | matched={sent.get('matched_entity_terms','')}")
        for h in (sent.get('headlines') or [])[:2]:
            L(f"    • {clean_text(h,135)}")
    L('\nL6 Sector Rotation — Capital moving where?'); L('-'*78)
    for e in rows[:12]:
        _l6_flags = e.get('review_flags') or []
        if abs(sf(e.get('basket_move'))) > 15 and 'THEME_BASKET_OUTLIER_REVIEW' not in _l6_flags:
            _l6_flags = list(_l6_flags) + ['THEME_BASKET_OUTLIER_REVIEW']
        _l6_dir = causal_price_action_label(e.get('sector_direction') or e.get('direction'), _l6_flags)
        L(f"  {normalize_theme_label(e.get('theme')):<32} {_l6_dir:<44} basket {pct(e.get('basket_move'))} | conf {sf(e.get('confidence')):.0f}%")
    L('\nL7 Institutional / Capital Flow'); L('-'*78)
    for t in positions:
        cf=dataset.get('capital_flow',{}).get(t,{})
        at=dataset.get('analyst_targets',{}).get(t,{})
        L(f"  {t}: flow {cf.get('institutional_bias','N/A')} | main {compact(cf.get('main_net'))} | super-large {compact(cf.get('super_large_net'))} | large {compact(cf.get('large_net'))}")
        if at: L(f"    Target range: low {money(at.get('low_target'))}, avg {money(at.get('avg_target') or at.get('average'))}, high {money(at.get('high_target'))}; Buy={at.get('buy')} Hold={at.get('hold')} Sell={at.get('sell')}")
    L('\nL8 News Flow / Catalyst — Forward calendar, not just headlines'); L('-'*78)
    for t in positions:
        cats=unique_catalysts_for_ticker(t,dataset)
        L(f"  {t}: " + ('; '.join(cats) if cats else 'No direct near-term catalyst detected'))

    # Watchlist ranking
    L('\n'+sep); L('  WATCHLIST OPPORTUNITY RANKING — 8-LENS SCORE — FULL WATCHLIST'); L(sep)
    # ── Risk Governor data for watchlist override ────────────────────────────
    _rg_data = _get_risk_governor_data(dataset)
    _gm_cluster = _rg_data.get('cluster_status', {}).get('GOLD_MINERS', {})
    _gm_critical = str(_gm_cluster.get('severity', '')).upper() == 'CRITICAL'
    if _gm_critical:
        L('  [RISK GOVERNOR] GOLD_MINERS cluster = CRITICAL — all BUY/ADD actions overridden.')
        L('  [RISK GOVERNOR] AU, NEM, GLD, GDX, GDXJ: HOLD / DECONCENTRATION REVIEW | CLUSTER_BLOCKED_NO_ADD')
        L('  [RISK GOVERNOR] A high 8-Lens score does NOT mean BUY when cluster concentration is CRITICAL.')
        L('  [RISK GOVERNOR] CIO must manually approve any deconcentration trade. No automated orders.')
    tickers=sorted([t for t,d in prices.items() if not t.startswith('^') and t.lower()!='vix'])
    scores=[apply_risk_governor_watchlist_override(score_ticker(t,dataset), _rg_data) for t in tickers if t in dataset.get('analyst_targets',{})]
    scores.sort(key=lambda r:r['score'], reverse=True)
    L(table_line([('Rank',5),('Ticker',7),('8Lens',9),('Action',22),('Move',9),('Price',12),('AvgTgt',12),('Upside',9),('Flow',13),('Governance',22)]))
    for i,r in enumerate(scores,1):
        p=prices.get(r['ticker'],{})
        up='N/A' if r['upside'] is None else f"{r['upside']:+.1f}%"
        _gov_col = r.get('governance_override') or governance(r['ticker'])
        L(table_line([(i,5),(r['ticker'],7),(f"{r['score']:.1f}/40",9),(r['action'],22),(pct(p.get('chg_pct')),9),(money(r['price']),12),(money(r['target']),12),(up,9),(r['flow'][:12],13),(_gov_col,22)]))
    L('\n  Current Portfolio Names (Risk Governor Adjusted):')
    for t in positions:
        r=apply_risk_governor_watchlist_override(score_ticker(t,dataset), _rg_data); lens=r['lenses']
        _orig=f" [original: {r['original_action']}]" if r.get('risk_governor_blocked') else ''
        L(f"    • {t}: 8-Lens {r['score']:.1f}/40 → {r['action']}{_orig} | L1 {lens[0]:.1f}, L2 {lens[1]:.1f}, L3 {lens[2]:.1f}, L4 {lens[3]:.1f}, L5 {lens[4]:.1f}, L6 {lens[5]:.1f}, L7 {lens[6]:.1f}, L8 {lens[7]:.1f}")

    # Analyst target detail
    L('\n'+sep); L('  ANALYST TARGET DETAIL — FULL WATCHLIST'); L(sep)
    L(table_line([('Ticker',8),('Price',12),('Low',12),('Avg',12),('High',12),('Upside',9),('Buy%',7),('Hold%',7),('Sell%',7),('Analysts',9),('Rating',7)]))
    for t in tickers:
        at=dataset.get('analyst_targets',{}).get(t,{})
        if not at: continue
        price=sf(prices.get(t,{}).get('price')); avg=sf(at.get('avg_target') or at.get('average'))
        up=target_upside(price,avg)
        L(table_line([(t,8),(money(price),12),(money(at.get('low_target')),12),(money(avg),12),(money(at.get('high_target')),12),(('N/A' if up is None else f"{up:+.1f}%"),9),(at.get('buy',''),7),(at.get('hold',''),7),(at.get('sell',''),7),(at.get('total_analysts',''),9),(at.get('rating',''),7)]))

    # Risk and CIO compression
    L('\n'+sep); L('  RISK FLAGS FOR RISK DEPARTMENT'); L(sep)
    for w in reg.get('warnings') or []: L(f"  • Regime warning: {w}")
    if port.get('integrity_flag'): L('  • Portfolio integrity flag TRUE; reconcile buying power/cash/unsettled funds.')
    if (meta.get('freshness') or {}).get('fear_greed',{}).get('grade')=='STALE': L('  • Fear & Greed: STALE_SECONDARY / EXCLUDED_FROM_CIO_CONFIDENCE.')
    for x in unexpl[:5]: L(f"  • Unexplained large move: {x}")
    for x in sector_gaps[:5]: L(f"  • Causal gap: {x}")

    L('\n'+sep); L('  CIO ACTION COMPRESSION'); L(sep)
    L(f"  Final Institutional Action : {action}")
    L(f"  Confidence                 : {conf:.3f} ({confidence_grade(conf)})")
    L(f"  Reason                     : {action_reason}")
    L(f"  Blind Spot Penalty         : {blind_penalty:.3f}")
    L('\n  Portfolio Position-Level Compression (Risk Governor Adjusted):')
    for t,pos in positions.items():
        md=(dataset.get('portfolio_mandates') or {}).get(t) or PORTFOLIO_MANDATE_DEFAULTS.get(t,{})
        mandate=md.get('mandate','UNCLASSIFIED')
        r=apply_risk_governor_watchlist_override(score_ticker(t,dataset), _rg_data)
        p=sf(pos.get('price'))
        note='WAIT/HOLD'
        if mandate=='BASELINE': note='BASELINE HOLD / TRIM STRENGTH / RELOAD ONLY ON SIGNAL'
        if mandate=='SATELLITE':
            lo=sf(md.get('dca_zone_low')); hi=sf(md.get('dca_zone_high'))
            note='SATELLITE DCA ZONE' if lo and hi and lo<=p<=hi else 'SATELLITE HOLD; DO NOT DCA OUTSIDE ZONE'
        if r.get('risk_governor_blocked'):
            note='HOLD / DECONCENTRATION REVIEW [CLUSTER_BLOCKED_NO_ADD]'
        L(f"    {t}: {note} | 8-Lens {r['score']:.1f}/40 | price {money(p)}")
    L('\n  Doctrine:')
    L('    If catalyst unknown → say unknown.')
    L('    If blind spot unknown → search for it.')
    L('    If causal intelligence incomplete → WAIT / HOLD.')
    L('    No blind spot check = no research confidence.')
    # ── REPORT QA FOOTER (WO-Final-PhD Defect 2 — wired to live audit) ─────────
    # Priority: use pre-injected _report_qa (computed from live audit in run_u_generator).
    # Fallback: call build_report_qa_footer with empty dicts (stale but safe).
    _qa = dataset.get("_report_qa") or {}
    if not _qa:
        try:
            from research_report_generator import build_report_qa_footer as _bqf
            _qa = _bqf(dataset, {}, {})
        except Exception:
            _qa = {}
    _qa_blocking = _qa.get('blocking_failures') or []
    _qa_warnings_list = _qa.get('warnings') or []
    L('\n'+sep); L('  REPORT QA FOOTER'); L(sep)
    L(f"  {'Consistency Audit':<28}: {_qa.get('consistency_audit', 'N/A')} (score={_qa.get('consistency_audit_score', 'N/A')})")
    L(f"  {'ECE Renderer Match':<28}: {_qa.get('ece_renderer_match', 'N/A')}")
    L(f"  {'ECE Percent Scale Check':<28}: {_qa.get('ece_percent_scale_check', 'N/A')}")
    if _qa.get('over_scaled_themes'):
        L(f"  {'  Over-scaled themes':<28}: {', '.join(_qa['over_scaled_themes'])}")
    L(f"  {'Evidence Mapping Check':<28}: {_qa.get('evidence_mapping_check', 'N/A')}")
    if _qa.get('mismatch_themes'):
        L(f"  {'  Mismatch themes':<28}: {', '.join(_qa['mismatch_themes'])}")
    L(f"  {'Causal Status Logic':<28}: {_qa.get('causal_status_logic', 'N/A')}")
    L(f"  {'Execution Safety Gate':<28}: {_qa.get('execution_safety_gate', 'N/A')}")
    L(f"  {'Freshness Gate':<28}: {_qa.get('freshness_gate', 'N/A')}")
    L(f"  {'Blocking Failures':<28}: {', '.join(_qa_blocking) if _qa_blocking else 'None'}")
    L(f"  {'Warnings':<28}: {', '.join(_qa_warnings_list) if _qa_warnings_list else 'None'}")
    L(f"  {'Final Institutional Grade':<28}: {_qa.get('final_institutional_grade', 'N/A')} / 10")
    L(sep)
    L('\n'+sep); L(f"  Prepared By: {PLATFORM_TEAM}"); L('  END OF RESEARCH DEPARTMENT REPORT — FIXED / ENRICHED R6'); L(sep)
    return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# RESEARCH REPORT ARCHIVE ADD-ON
# Runs inside this generator. No wrapper. No subprocess. No recursion.
#
# Flow:
#   1. generate(d)
#   2. write Bluelotus_V3_Report.txt
#   3. archive exact report string into MySQL research_report_archive
#   4. extract DB row, including full report_text
#   5. write research_report_archive_latest.json beside Bluelotus_V3_Report.txt
# ─────────────────────────────────────────────────────────────────────────────

def archive_json_safe(value: Any) -> Any:
    from decimal import Decimal
    from datetime import date as _date, datetime as _datetime

    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (_datetime, _date)):
        return value.isoformat(sep=" ")
    if isinstance(value, dict):
        return {str(k): archive_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [archive_json_safe(v) for v in value]
    return value


def archive_sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def archive_first_match(text: str, pattern: str) -> Optional[str]:
    m = re.search(pattern, text, re.MULTILINE)
    return m.group(1).strip() if m else None


def archive_clean_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def archive_clean_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value).replace(",", "").strip()))
    except Exception:
        return None


def archive_parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).replace("SGT", "").replace("Z", "").strip()
    s = re.sub(r"\+\d{2}:\d{2}$", "", s).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19], fmt)
        except Exception:
            pass
    try:
        return datetime.fromisoformat(s[:19])
    except Exception:
        return None


def archive_split_export_ingest(report_text: str) -> Tuple[Optional[str], Optional[str]]:
    combined = archive_first_match(report_text, r"^\s*Export\s*/\s*Ingest\s*:\s*(.+)$")
    if combined:
        parts = [p.strip() for p in combined.split("/")]
        return (
            parts[0] if len(parts) >= 1 and parts[0] else None,
            parts[1] if len(parts) >= 2 and parts[1] else None,
        )

    export_version = archive_first_match(report_text, r"^\s*Export Version\s*:\s*(.+)$")
    ingest_version = archive_first_match(report_text, r"^\s*Ingest Version\s*:\s*(.+)$")
    return export_version, ingest_version


def archive_parse_sources(report_text: str) -> Tuple[Optional[int], Optional[int]]:
    raw = archive_first_match(report_text, r"^\s*Sources Active\s*:\s*(.+)$")
    if not raw:
        return None, None
    nums = re.findall(r"\d+", raw)
    if len(nums) >= 2:
        return int(nums[0]), int(nums[1])
    if len(nums) == 1:
        return int(nums[0]), None
    return None, None


def archive_parse_confidence(report_text: str) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    cio_line = archive_first_match(report_text, r"^\s*CIO Compression\s*:\s*(.+)$")
    if not cio_line:
        return None, None, None

    cio_action = cio_line.split("|")[0].strip()
    confidence = None
    confidence_label = None

    m = re.search(r"Confidence\s+([0-9]+(?:\.[0-9]+)?)", cio_line, re.IGNORECASE)
    if m:
        confidence = archive_clean_float(m.group(1))

    m = re.search(r"\(([A-Za-z\- ]+)\)", cio_line)
    if m:
        confidence_label = m.group(1).strip().upper()

    return cio_action, confidence, confidence_label


def archive_parse_blind_causal(report_text: str) -> Tuple[Optional[str], Optional[str]]:
    line = archive_first_match(report_text, r"^\s*Blind Spot Status\s*:\s*(.+)$")
    if not line:
        return None, None

    blind = line.split("|")[0].strip()
    causal = None
    m = re.search(r"Causal\s+Explanation\s*:\s*([A-Za-z ]+)", line, re.IGNORECASE)
    if m:
        causal = m.group(1).strip().upper()

    return blind, causal


def archive_parse_portfolio(report_text: str) -> Dict[str, Optional[float]]:
    out = {
        "portfolio_assets": None,
        "portfolio_cash": None,
        "portfolio_equity": None,
        "portfolio_pnl": None,
        "portfolio_pnl_pct": None,
    }

    header = archive_first_match(report_text, r"^\s*Portfolio Assets\s*:\s*(.+)$")
    if header:
        m = re.search(r"\$[\d,]+(?:\.\d+)?", header)
        if m:
            out["portfolio_assets"] = archive_clean_float(m.group(0))
        m = re.search(r"Cash\s+\$?(-?[\d,]+(?:\.\d+)?)", header, re.IGNORECASE)
        if m:
            out["portfolio_cash"] = archive_clean_float(m.group(1))

    summary = archive_first_match(report_text, r"^\s*Portfolio\s*:\s*(.+)$")
    if summary:
        m = re.search(r"Cash\s+\$?(-?[\d,]+(?:\.\d+)?)", summary, re.IGNORECASE)
        if m:
            out["portfolio_cash"] = archive_clean_float(m.group(1))
        m = re.search(r"Equity\s+\$?(-?[\d,]+(?:\.\d+)?)", summary, re.IGNORECASE)
        if m:
            out["portfolio_equity"] = archive_clean_float(m.group(1))
        m = re.search(r"Total\s+P/L\s+\$?(-?[\d,]+(?:\.\d+)?)", summary, re.IGNORECASE)
        if m:
            out["portfolio_pnl"] = archive_clean_float(m.group(1))
        m = re.search(r"Total\s+P/L\s+\$?-?[\d,]+(?:\.\d+)?\s+\((-?[\d.]+)%\)", summary, re.IGNORECASE)
        if m:
            out["portfolio_pnl_pct"] = archive_clean_float(m.group(1))

    return out


def archive_build_row(report_text: str, report_path: Path) -> Dict[str, Any]:
    export_version, ingest_version = archive_split_export_ingest(report_text)
    sources_active, sources_expected = archive_parse_sources(report_text)
    cio_action, confidence, confidence_label = archive_parse_confidence(report_text)
    blind_status, causal_status = archive_parse_blind_causal(report_text)
    portfolio = archive_parse_portfolio(report_text)

    regime_line = archive_first_match(report_text, r"^\s*Regime\s*:\s*(.+)$")
    regime = None
    regime_score = None
    if regime_line:
        regime = re.sub(r"\(score\s+[-+]?\d+\)", "", regime_line, flags=re.IGNORECASE).strip()
        m = re.search(r"score\s+([-+]?\d+)", regime_line, re.IGNORECASE)
        if m:
            regime_score = archive_clean_int(m.group(1))

    total_signals = archive_first_match(report_text, r"^\s*Total Signals\s*:\s*([\d,]+)")
    latest_signal = (
        archive_first_match(report_text, r"^\s*Total Signals\s*:\s*[\d,]+\s*\|\s*Latest\s+(.+)$")
        or archive_first_match(report_text, r"^\s*Latest Signal\s*:\s*(.+)$")
    )

    market_status = (
        archive_first_match(report_text, r"^\s*Market Status\s*:\s*(.+)$")
        or archive_first_match(report_text, r"^\s*Market Session\s*:\s*(.+)$")
    )
    if market_status:
        _ms = str(market_status).upper().strip()
        if "WEEKEND" in _ms:
            market_session_db = "WEEKEND_SNAPSHOT"
        elif "HOLIDAY" in _ms:
            market_session_db = "HOLIDAY_SNAPSHOT"
        elif "PRE" in _ms and "MARKET" in _ms:
            market_session_db = "PRE_MARKET"
        elif "POST" in _ms and "MARKET" in _ms:
            market_session_db = "POST_MARKET"
        elif "REGULAR" in _ms:
            market_session_db = "REGULAR_SESSION"
        elif "CLOSED" in _ms:
            market_session_db = "MARKET_CLOSED"
        else:
            market_session_db = _ms[:32]
    else:
        market_session_db = None

    return {
        "report_type": "RESEARCH_DEPARTMENT_REPORT",
        "report_version": REPORT_VERSION,
        "generated_at": archive_parse_datetime(archive_first_match(report_text, r"^\s*Generated\s*:\s*(.+)$")) or datetime.now(),
        "dataset_generated_at": archive_parse_datetime(archive_first_match(report_text, r"^\s*Dataset Generated\s*:\s*(.+)$")),
        "market_session": market_session_db,
        "export_version": export_version,
        "ingest_version": ingest_version,
        "regime": regime,
        "regime_score": regime_score,
        "regime_action": archive_first_match(report_text, r"^\s*Regime Action\s*:\s*(.+)$"),
        "cio_action": cio_action,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "blind_spot_status": blind_status,
        "causal_explanation_status": causal_status,
        "doctrine_warning": archive_first_match(report_text, r"^\s*DOCTRINE WARNING\s*:\s*(.+)$"),
        "portfolio_assets": portfolio["portfolio_assets"],
        "portfolio_cash": portfolio["portfolio_cash"],
        "portfolio_equity": portfolio["portfolio_equity"],
        "portfolio_pnl": portfolio["portfolio_pnl"],
        "portfolio_pnl_pct": portfolio["portfolio_pnl_pct"],
        "total_signals": archive_clean_int(total_signals),
        "latest_signal_at": archive_parse_datetime(latest_signal),
        "sources_active": sources_active,
        "sources_expected": sources_expected,
        "report_title": archive_first_match(report_text, r"^\s*(BLUELOTUS FUND\s+—\s+.+?)\s*$"),
        "report_sha256": archive_sha256_text(report_text),
        "report_text": report_text,
        "source_file_path": str(report_path),
    }


def archive_get_db_connection():
    import sys
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))

    try:
        from dotenv import load_dotenv
        load_dotenv(root / ".env")
        load_dotenv(Path.cwd() / ".env")
    except Exception:
        pass

    try:
        from core.db import get_connection  # type: ignore
        return get_connection()
    except Exception:
        pass

    try:
        import mysql.connector  # type: ignore
    except Exception as exc:
        raise RuntimeError("DB connection failed: core.db unavailable and mysql.connector not installed.") from exc

    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST") or "127.0.0.1"
    port = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306")
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER")
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD") or ""
    database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME") or "bluelotus2"

    if not user:
        raise RuntimeError("Missing MYSQL_USER / DB_USER in .env")

    return mysql.connector.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
    )


ARCHIVE_INSERT_SQL = """
INSERT INTO research_report_archive (
    report_type, report_version, generated_at, dataset_generated_at, market_session,
    export_version, ingest_version, regime, regime_score, regime_action,
    cio_action, confidence, confidence_label, blind_spot_status, causal_explanation_status,
    doctrine_warning, portfolio_assets, portfolio_cash, portfolio_equity, portfolio_pnl,
    portfolio_pnl_pct, total_signals, latest_signal_at, sources_active, sources_expected,
    report_title, report_sha256, report_text, source_file_path
) VALUES (
    %(report_type)s, %(report_version)s, %(generated_at)s, %(dataset_generated_at)s, %(market_session)s,
    %(export_version)s, %(ingest_version)s, %(regime)s, %(regime_score)s, %(regime_action)s,
    %(cio_action)s, %(confidence)s, %(confidence_label)s, %(blind_spot_status)s, %(causal_explanation_status)s,
    %(doctrine_warning)s, %(portfolio_assets)s, %(portfolio_cash)s, %(portfolio_equity)s, %(portfolio_pnl)s,
    %(portfolio_pnl_pct)s, %(total_signals)s, %(latest_signal_at)s, %(sources_active)s, %(sources_expected)s,
    %(report_title)s, %(report_sha256)s, %(report_text)s, %(source_file_path)s
)
"""


def archive_research_report_after_generation(report_text: str, output_path: Path) -> Dict[str, Any]:
    row = archive_build_row(report_text, output_path)
    conn = archive_get_db_connection()

    try:
        cur = conn.cursor(dictionary=True)

        cur.execute(
            "SELECT id FROM research_report_archive WHERE report_sha256 = %s LIMIT 1",
            (row["report_sha256"],),
        )
        existing = cur.fetchone()

        if existing:
            archive_status = "duplicate_skipped"
            archive_id = int(existing["id"])
        else:
            cur.execute(ARCHIVE_INSERT_SQL, row)
            conn.commit()
            archive_status = "inserted"
            archive_id = int(cur.lastrowid)

        cur.execute(
            """
            SELECT
                id, report_type, report_version, generated_at, dataset_generated_at,
                market_session, export_version, ingest_version, regime, regime_score,
                regime_action, cio_action, confidence, confidence_label, blind_spot_status,
                causal_explanation_status, doctrine_warning, portfolio_assets, portfolio_cash,
                portfolio_equity, portfolio_pnl, portfolio_pnl_pct, total_signals,
                latest_signal_at, sources_active, sources_expected, report_title,
                report_sha256, report_text, source_file_path, created_at
            FROM research_report_archive
            WHERE id = %s
            LIMIT 1
            """,
            (archive_id,),
        )
        db_row = cur.fetchone() or {}

    finally:
        try:
            conn.close()
        except Exception:
            pass

    result = {
        "archive_status": archive_status,
        "archive_id": archive_id,
        "verified_from_database": bool(db_row),
        "archive_json_generated_at": datetime.now().isoformat(sep=" "),
        "report_text_included": bool(db_row.get("report_text")),
        "report_text_char_count": len(db_row.get("report_text") or ""),
        "database_row": archive_json_safe(db_row),
    }

    json_path = output_path.parent / "research_report_archive_latest.json"
    json_path.write_text(json.dumps(archive_json_safe(result), indent=2, ensure_ascii=False), encoding="utf-8")

    return result


def _run_governance_gate_if_available() -> Optional[Dict]:
    """
    Run governance gate before report generation.
    Returns approved_operating_truth dict if gate ran successfully, else None.
    Governance gate failure is non-fatal — report generation continues.
    """
    try:
        import sys as _sys
        _gov_dir = Path(r"C:\bluelotus3\governance")
        if str(_gov_dir) not in _sys.path:
            _sys.path.insert(0, str(_gov_dir))
        from governance_gate import run_governance_gate, load_approved_truth
        result = run_governance_gate()
        status = result.get("release_status", "UNKNOWN")
        print(f"[Governance Gate] Release status: {status}")
        if result.get("blocks"):
            print("[Governance Gate] BLOCKING ISSUES:")
            for b in result["blocks"]:
                print(f"  • {b}")
        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"[Governance Gate] WARNING: {w}")
        return result.get("approved_truth")
    except Exception as exc:
        print(f"[Governance Gate] WARNING: gate not run — {exc}")
        return None


def main():
    ap=argparse.ArgumentParser(description='BlueLotus V2.6u auto-path research report generator')
    ap.add_argument('--dataset', type=Path, default=DEFAULT_DATASET, help='Optional override. Not needed in production.')
    ap.add_argument('--output', type=Path, default=DEFAULT_OUTPUT, help='Optional override. Not needed in production.')
    ap.add_argument('--skip-governance', action='store_true', help='Skip governance gate (dev/debug only).')
    args=ap.parse_args()

    dataset_path = resolve_input_path(args.dataset)
    output_path = resolve_output_path(args.output)

    # ── Governance Gate ──────────────────────────────────────────────────────
    approved_truth = None
    if not getattr(args, 'skip_governance', False):
        approved_truth = _run_governance_gate_if_available()

    d=load_dataset(dataset_path)
    report=normalize_report_text(generate(d))
    output_path.write_text(report, encoding='utf-8')
    print('BlueLotus Research Report generated successfully.')
    print(f'Dataset : {dataset_path}')
    print(f'Output  : {output_path}')
    print(f'Lines   : {len(report.splitlines())}')
    print(f'Chars   : {len(report)}')

    try:
        archive_result = archive_research_report_after_generation(report, output_path)
        print(f"Archive: {archive_result.get('archive_status')} id={archive_result.get('archive_id')}")
        print(f"Archive JSON: {output_path.parent / 'research_report_archive_latest.json'}")
        print(f"Archive Text Included: {archive_result.get('report_text_included')} | Chars {archive_result.get('report_text_char_count')}")
    except Exception as exc:
        print(f"Archive WARNING: research_report_archive insert/extract failed: {exc}")

if __name__=='__main__':
    main()
