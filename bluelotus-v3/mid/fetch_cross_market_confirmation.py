#!/usr/bin/env python3
"""
BlueLotus MID -- Cross-Market Confirmation fetcher.

Moomoo read-only:
- Uses OpenQuoteContext.get_market_snapshot()
- Does not import or use trade contexts
- Does not create, modify, cancel, or route orders

Outputs:
- mid/cross_market_confirmation.json
- data/regime/cross_market_confirmation_latest.json
- raw_signal_archive source Cross_Market_Confirmation
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
OPEND_HOST = os.getenv("MOOMOO_OPEND_HOST", "127.0.0.1")
OPEND_PORT = int(os.getenv("MOOMOO_OPEND_PORT", "11111"))

GROUPS = {
    "market_index_confirmation": ["SPY", "QQQ", "IWM", "RSP"],
    "volatility_panic_confirmation": ["VXX", "UVXY"],
    "dollar_rates_pressure": ["UUP", "TLT", "IEF", "SHY"],
    "gold_miner_confirmation": ["GLD", "SLV", "GDX", "GDXJ", "AU", "NEM"],
    "sector_etf_rotation": ["XLK", "XLF", "XLE", "XLU", "XLP", "XLI", "XLY", "XLV", "XLB", "XLC"],
    "credit_liquidity_stress": ["HYG", "JNK", "LQD", "AGG"],
    "commodity_confirmation": ["XME", "USO", "DBC", "CPER", "URA", "QTUM", "IAU", "SIL", "SILJ", "UNG", "DBA"],
    "factor_rotation_confirmation": ["VUG", "VTV", "MTUM", "QUAL", "USMV", "VLUE"],
    "global_risk_confirmation": ["EFA", "EEM", "FXI", "KWEB", "EWJ", "EWZ", "INDA"],
    "bond_credit_extension": ["MBB", "TIP", "BIL"],
}

UNAVAILABLE_MOOMOO_ONLY = {
    "^VIX": "CBOE index symbol not exposed through Moomoo US equity snapshot; VXX/UVXY used as panic proxies.",
    "^TNX": "Treasury index symbol not exposed through Moomoo US equity snapshot; TLT/IEF/SHY used as rates proxies.",
    "DXY": "Dollar index not exposed through Moomoo US equity snapshot; UUP used as dollar proxy.",
}


def n(value: Any, default: float = 0.0) -> float:
    try:
        out = float(str(value).replace("N/A", "0").replace("--", "0") or 0)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def market_session() -> str:
    now_utc = datetime.now(timezone.utc)
    now_et = now_utc + timedelta(hours=-4)
    hour = now_et.hour + now_et.minute / 60.0
    if 9.5 <= hour < 16.0:
        return "REGULAR"
    if 4.0 <= hour < 9.5:
        return "PRE_MARKET"
    if 16.0 <= hour < 20.0:
        return "POST_MARKET"
    return "CLOSED"


def snapshot_row(row: Any, session: str) -> Dict[str, Any]:
    last = n(row.get("last_price"))
    prev = n(row.get("prev_close_price")) or last
    pre_px = n(row.get("pre_price"))
    after_px = n(row.get("after_price"))
    pre_chg = n(row.get("pre_change_rate"))
    after_chg = n(row.get("after_change_rate"))
    volume = int(n(row.get("volume")))

    if session == "PRE_MARKET" and pre_px > 0:
        price, chg, source = pre_px, pre_chg, "pre_market"
    elif session == "POST_MARKET" and after_px > 0:
        price, chg, source = after_px, after_chg, "post_market"
    else:
        price = last if last > 0 else prev
        chg = ((last - prev) / prev * 100.0) if prev else 0.0
        source = "regular_close" if session == "CLOSED" else "regular"

    return {
        "price": round(price, 4),
        "chg_pct": round(chg, 4),
        "volume": volume,
        "regular_close": round(last, 4) if last else None,
        "prev_close": round(prev, 4) if prev else None,
        "pre_price": round(pre_px, 4) if pre_px else None,
        "after_price": round(after_px, 4) if after_px else None,
        "price_source": source,
        "session": session,
    }


def fetch_moomoo_snapshots(tickers: List[str]) -> Tuple[Dict[str, Any], Dict[str, str]]:
    import moomoo as ft
    import moomoo.common.ft_logger as ft_logger

    ft_logger.logger.enable_console_log(False)
    session = market_session()
    codes = [f"US.{t}" for t in tickers]
    ctx = ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)
    try:
        ret, data = ctx.get_market_snapshot(codes)
    finally:
        ctx.close()

    snapshots: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    if ret != ft.RET_OK or data is None:
        return snapshots, {t: str(data) for t in tickers}

    returned = set()
    for _, row in data.iterrows():
        ticker = str(row.get("code", "")).replace("US.", "").upper()
        if not ticker:
            continue
        returned.add(ticker)
        snapshots[ticker] = snapshot_row(row, session)
    for ticker in tickers:
        if ticker not in returned:
            errors[ticker] = "Moomoo returned no snapshot row"
    return snapshots, errors


def avg_change(snapshots: Dict[str, Any], tickers: List[str]) -> float:
    vals = [n((snapshots.get(t) or {}).get("chg_pct")) for t in tickers if t in snapshots]
    return sum(vals) / len(vals) if vals else 0.0


def build_scores(snapshots: Dict[str, Any]) -> Dict[str, float]:
    market = avg_change(snapshots, ["SPY", "QQQ", "IWM", "RSP"])
    risk_assets = avg_change(snapshots, ["SPY", "QQQ", "IWM", "HYG"])
    defensive = avg_change(snapshots, ["TLT", "IEF", "UUP", "VXX"])
    gold = avg_change(snapshots, ["GLD", "SLV"])
    miners = avg_change(snapshots, ["GDX", "GDXJ", "AU", "NEM"])
    credit = avg_change(snapshots, ["HYG", "JNK", "LQD"])
    sector_risk = avg_change(snapshots, ["XLK", "XLY", "XLI"]) - avg_change(snapshots, ["XLU", "XLP", "XLV"])
    factor_growth_value = avg_change(snapshots, ["VUG", "MTUM"]) - avg_change(snapshots, ["VTV", "USMV"])
    global_risk = avg_change(snapshots, ["EFA", "EEM", "FXI", "KWEB", "EWJ", "EWZ", "INDA"])
    commodity_stress = avg_change(snapshots, ["GLD", "SLV", "DBC", "USO", "CPER", "URA", "UNG", "DBA"]) - market
    bond_quality = avg_change(snapshots, ["AGG", "MBB", "BIL", "TIP"]) - avg_change(snapshots, ["HYG", "JNK"])
    return {
        "market_breadth_confirmation_score": round(market, 4),
        "risk_appetite_score": round(risk_assets - defensive, 4),
        "dollar_pressure_score": round(n((snapshots.get("UUP") or {}).get("chg_pct")), 4),
        "yield_pressure_score": round(-avg_change(snapshots, ["TLT", "IEF", "SHY"]), 4),
        "gold_thesis_confirmation_score": round(gold - market, 4),
        "gold_miner_relative_strength_score": round(miners - gold, 4),
        "sector_etf_rotation_score": round(sector_risk, 4),
        "credit_stress_score": round(-credit, 4),
        "factor_growth_vs_value_score": round(factor_growth_value, 4),
        "global_risk_confirmation_score": round(global_risk, 4),
        "commodity_stress_confirmation_score": round(commodity_stress, 4),
        "bond_quality_vs_credit_score": round(bond_quality, 4),
    }


def build_flags(snapshots: Dict[str, Any], scores: Dict[str, float]) -> Dict[str, Any]:
    spy = n((snapshots.get("SPY") or {}).get("chg_pct"))
    qqq = n((snapshots.get("QQQ") or {}).get("chg_pct"))
    iwm = n((snapshots.get("IWM") or {}).get("chg_pct"))
    xlk = n((snapshots.get("XLK") or {}).get("chg_pct"))
    xlf = n((snapshots.get("XLF") or {}).get("chg_pct"))
    gld = n((snapshots.get("GLD") or {}).get("chg_pct"))
    miners = avg_change(snapshots, ["GDX", "GDXJ", "AU", "NEM"])
    qtum = n((snapshots.get("QTUM") or {}).get("chg_pct"))
    vug = n((snapshots.get("VUG") or {}).get("chg_pct"))
    vtv = n((snapshots.get("VTV") or {}).get("chg_pct"))
    eem = n((snapshots.get("EEM") or {}).get("chg_pct"))
    kweb = n((snapshots.get("KWEB") or {}).get("chg_pct"))
    hyg = n((snapshots.get("HYG") or {}).get("chg_pct"))
    lqd = n((snapshots.get("LQD") or {}).get("chg_pct"))
    return {
        "broad_market_risk_off": spy <= -1.0 and qqq <= -1.0 and iwm <= -1.0,
        "tech_led_selloff": qqq <= spy - 0.5 and xlk <= spy - 0.5,
        "small_cap_risk_off": iwm <= spy - 0.75,
        "dollar_pressure_active": scores["dollar_pressure_score"] >= 0.30,
        "yield_pressure_active": scores["yield_pressure_score"] >= 0.40,
        "credit_stress_active": scores["credit_stress_score"] >= 0.50,
        "gold_thesis_confirmed": gld > 0 and miners > 0 and spy < 0,
        "gold_thesis_tactical_pressure": gld > 0 and miners < 0,
        "miner_panic_liquidation": gld > -0.5 and miners <= -2.0,
        "bank_thesis_confirmed": xlf >= spy + 0.5,
        "ai_thesis_failure": qqq <= -1.0 and xlk <= -1.2,
        "quantum_panic_liquidation": qtum <= -2.0,
        "growth_factor_under_pressure": vug <= vtv - 0.50,
        "quality_defensive_rotation": scores["bond_quality_vs_credit_score"] >= 0.50 or lqd >= hyg + 0.50,
        "global_ex_us_risk_off": scores["global_risk_confirmation_score"] <= -1.0,
        "china_internet_stress": kweb <= -2.0,
        "em_risk_off_confirmation": eem <= spy - 0.50,
        "commodity_safe_haven_stress": scores["commodity_stress_confirmation_score"] >= 0.75,
    }


def build_package() -> Dict[str, Any]:
    tickers = sorted({t for group in GROUPS.values() for t in group})
    snapshots, errors = fetch_moomoo_snapshots(tickers)
    scores = build_scores(snapshots)
    flags = build_flags(snapshots, scores)
    grouped = {
        group: {ticker: snapshots.get(ticker, {"unavailable": True, "reason": errors.get(ticker, "not returned")}) for ticker in tickers}
        for group, tickers in GROUPS.items()
    }
    grouped["volatility_panic_confirmation"]["^VIX"] = {"unavailable": True, "reason": UNAVAILABLE_MOOMOO_ONLY["^VIX"], "proxy": ["VXX", "UVXY"]}
    grouped["dollar_rates_pressure"]["^TNX"] = {"unavailable": True, "reason": UNAVAILABLE_MOOMOO_ONLY["^TNX"], "proxy": ["TLT", "IEF", "SHY"]}
    grouped["dollar_rates_pressure"]["DXY"] = {"unavailable": True, "reason": UNAVAILABLE_MOOMOO_ONLY["DXY"], "proxy": ["UUP"]}

    coverage = len(snapshots) / len(tickers) if tickers else 0.0
    return {
        "cycle_ts": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "source": "CrossMarket_Confirmation_Engine",
        "source_detail": "Moomoo OpenD get_market_snapshot; unavailable index symbols represented by Moomoo-tradable ETF proxies",
        "market_session": market_session(),
        "ticker_count": len(tickers),
        "filled_count": len(snapshots),
        "coverage_ratio": round(coverage, 4),
        **grouped,
        "derived_scores": scores,
        "interpretation_flags": flags,
        "unavailable_symbols": UNAVAILABLE_MOOMOO_ONLY,
        "fetch_errors": errors,
    }


def write_outputs(package: Dict[str, Any]) -> None:
    mid_path = PROJECT_ROOT / "mid" / "cross_market_confirmation.json"
    data_path = PROJECT_ROOT / "data" / "regime" / "cross_market_confirmation_latest.json"
    for path in (mid_path, data_path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(package, indent=2, ensure_ascii=False), encoding="utf-8")


def write_raw_signal(package: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import write_raw_signal

    load_dotenv(PROJECT_ROOT / ".env")
    summary = (
        f"Cross-market confirmation: coverage {package.get('filled_count')}/{package.get('ticker_count')} | "
        f"risk_appetite {package['derived_scores'].get('risk_appetite_score')} | "
        f"flags {package.get('interpretation_flags')}"
    )
    write_raw_signal(
        source="Cross_Market_Confirmation",
        ingestion_method="moomoo_opend_get_market_snapshot",
        raw_payload=package,
        raw_text=summary,
        signal_type="macro",
        suspected_category="CROSS_MARKET_CONFIRMATION",
        suspected_entities=list(package.get("interpretation_flags", {}).keys()),
        quality_score=float(package.get("coverage_ratio") or 0),
    )


def main() -> None:
    package = build_package()
    write_outputs(package)
    write_raw_signal(package)
    print("BlueLotus Cross-Market Confirmation generated.")
    print(f"Coverage: {package['filled_count']}/{package['ticker_count']} ({package['coverage_ratio']:.1%})")
    print(f"Risk appetite score: {package['derived_scores']['risk_appetite_score']:+.4f}")
    print(f"Flags: {package['interpretation_flags']}")


if __name__ == "__main__":
    main()

