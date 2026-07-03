from __future__ import annotations


TACTICAL_ENGINE_TICKERS = ["ASTS", "PL", "RKLB", "LUNR", "QBTS", "QUBT"]


def reload_allowed(regime_broken: bool, over_cap: bool, thesis_intact: bool) -> bool:
    return bool(thesis_intact and not regime_broken and not over_cap)
