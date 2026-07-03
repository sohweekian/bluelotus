from __future__ import annotations

from typing import Any, Dict

from .pipeline_manifest import stage_shell


def run_stage(dataset: Dict[str, Any]) -> Dict[str, Any]:
    stage = stage_shell("Universe Selection", ["portfolio", "live_prices"], ["universe_tickers"])
    tickers = set()
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    positions = portfolio.get("positions")
    if isinstance(positions, dict):
        tickers.update(str(k).replace("US.", "").upper() for k in positions)
    elif isinstance(positions, list):
        tickers.update(str(row.get("ticker") or row.get("symbol") or row.get("code") or "").replace("US.", "").upper() for row in positions if isinstance(row, dict))
    live = dataset.get("live_prices") if isinstance(dataset.get("live_prices"), dict) else {}
    tickers.update(str(k).replace("US.", "").upper() for k in live)
    stage["universe_tickers"] = sorted(t for t in tickers if t)
    stage["ticker_count"] = len(stage["universe_tickers"])
    return stage

