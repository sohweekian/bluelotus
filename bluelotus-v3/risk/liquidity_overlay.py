from __future__ import annotations

from typing import Dict, Any


def build_liquidity_overlay(positions: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    microcap = []
    for ticker, row in positions.items():
        text = f"{ticker} {row.get('thesis', '')} {row.get('sector', '')}".upper()
        if ticker in {"QUBT", "QBTS", "LUNR", "BKSY", "PL", "ASTS", "RKLB"} or "HIGH BETA" in text:
            microcap.append(ticker)
    status = "LIQUIDITY_REVIEW" if microcap else "PASS"
    return {
        "position_risk_telemetry_status": status,
        "liquidity_watch_tickers": sorted(set(microcap)),
    }

