from __future__ import annotations


SPACE_PROXY_TICKERS = ["ASTS", "RKLB", "LUNR", "PL", "RDW", "SPCE", "BKSY", "SATS", "GSAT", "IRDM", "VSAT"]


def related_private_vehicle(ticker: str) -> str:
    if ticker.upper() in SPACE_PROXY_TICKERS:
        return "SpaceX"
    return ""
