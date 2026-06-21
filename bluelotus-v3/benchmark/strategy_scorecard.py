from __future__ import annotations

from typing import Dict, Iterable, List


def build_strategy_scorecards(summary_rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    rows = []
    for rank, row in enumerate(summary_rows, start=1):
        rows.append({
            "rank": rank,
            "strategy_id": row.get("strategy_id"),
            "avg_return_proxy": row.get("avg_return_proxy"),
            "avg_drawdown_proxy": row.get("avg_drawdown_proxy"),
            "avg_sharpe_proxy": row.get("avg_sharpe_proxy"),
            "scorecard_status": "PASS" if rank <= 4 else "OBSERVE",
        })
    return rows

