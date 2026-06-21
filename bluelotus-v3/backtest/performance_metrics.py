from __future__ import annotations

from typing import Dict, Iterable, List


def summarize_results(rows: Iterable[Dict[str, object]]) -> List[Dict[str, object]]:
    buckets: Dict[str, Dict[str, float]] = {}
    counts: Dict[str, int] = {}
    for row in rows:
        sid = str(row.get("strategy_id"))
        bucket = buckets.setdefault(sid, {"return_proxy": 0.0, "max_drawdown_proxy": 0.0, "sharpe_proxy": 0.0})
        counts[sid] = counts.get(sid, 0) + 1
        for key in bucket:
            bucket[key] += float(row.get(key) or 0.0)
    out = []
    for sid, values in buckets.items():
        count = max(1, counts.get(sid, 1))
        out.append({
            "strategy_id": sid,
            "avg_return_proxy": round(values["return_proxy"] / count, 6),
            "avg_drawdown_proxy": round(values["max_drawdown_proxy"] / count, 6),
            "avg_sharpe_proxy": round(values["sharpe_proxy"] / count, 6),
        })
    return sorted(out, key=lambda row: row["avg_sharpe_proxy"], reverse=True)

