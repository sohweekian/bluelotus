from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List


SYMBOLS = ["SPY", "QQQ", "^VIX", "UUP", "GLD", "GDX", "GDXJ", "USO", "TLT", "IEF", "BTC-USD"]


def fetch_market_pulse(timeout: int = 12) -> Dict:
    rows = []
    for symbol in SYMBOLS:
        rows.append(fetch_one(symbol, timeout=timeout))
    return {
        "schema_version": "bluelotus_live_market_pulse_v1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "database_write": False,
        "llm_used": False,
        "indicators": rows,
    }


def fetch_one(symbol: str, timeout: int = 12) -> Dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=1d&interval=1m"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BlueLotus3-NewsReporter/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        result = (data.get("chart", {}).get("result") or [{}])[0]
        meta = result.get("meta", {})
        price = meta.get("regularMarketPrice")
        previous = meta.get("previousClose")
        chg_pct = None
        if price is not None and previous:
            chg_pct = (float(price) - float(previous)) / float(previous) * 100.0
        return {
            "symbol": symbol,
            "price": price,
            "previous_close": previous,
            "change_pct": round(chg_pct, 4) if chg_pct is not None else None,
            "status": "OK",
        }
    except Exception as exc:
        return {"symbol": symbol, "status": "ERROR", "error": str(exc)[:160]}
