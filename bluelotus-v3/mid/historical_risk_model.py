#!/usr/bin/env python3
"""
BlueLotus MID -- history-based portfolio risk model.

Inputs:
- portfolio_readonly_* tables, preferred
- historical_prices table
- data/frontend/dataset_raw.json for constraints and classifications

Outputs:
- risk_model_runs table
- portfolio_optimizer_runs table
- data/risk/risk_model_latest.json
- data/risk/portfolio_targets_latest.json
- raw_signal_archive source Historical_Risk_Model

This is a research and risk telemetry layer only. It generates target weights
and constraint observations, not executable orders.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


PROJECT_ROOT = Path(r"C:\bluelotus3")
DATASET_PATH = PROJECT_ROOT / "data" / "frontend" / "dataset_raw.json"
RISK_OUTPUT = PROJECT_ROOT / "data" / "risk" / "risk_model_latest.json"
TARGET_OUTPUT = PROJECT_ROOT / "data" / "risk" / "portfolio_targets_latest.json"
TRADING_DAYS = 252


def n(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).replace(",", "").replace("N/A", "").replace("--", "").strip()
        if text == "":
            return default
        out = float(text)
        return out if math.isfinite(out) else default
    except Exception:
        return default


def json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat(sep=" ")
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [json_safe(v) for v in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def json_dumps(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, default=str)


def sha_short(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def load_dataset() -> Dict[str, Any]:
    if not DATASET_PATH.exists():
        return {}
    try:
        return json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def ensure_tables() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from mid.institutional_upgrade_tables import create_tables

    create_tables()


def get_connection():
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import get_connection as _get_connection

    load_dotenv(PROJECT_ROOT / ".env")
    return _get_connection()


def parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return value


def latest_portfolio_from_tables(cur: Any) -> Dict[str, Any]:
    cur.execute(
        """
        SELECT *
        FROM portfolio_readonly_snapshots
        ORDER BY cycle_ts DESC, id DESC
        LIMIT 1
        """
    )
    snap = cur.fetchone()
    if not snap:
        return {}
    snapshot_id = snap["snapshot_id"]
    cur.execute(
        """
        SELECT *
        FROM portfolio_readonly_positions
        WHERE snapshot_id = %s
        ORDER BY market_value DESC, ticker ASC
        """,
        (snapshot_id,),
    )
    pos_rows = cur.fetchall()
    positions = {}
    for row in pos_rows:
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        positions[ticker] = {
            "ticker": ticker,
            "qty": n(row.get("qty")),
            "avg_cost": n(row.get("average_cost")),
            "price": n(row.get("price")),
            "mkt_val": n(row.get("market_value")),
            "cost_basis": n(row.get("cost_basis")),
            "unrealized": n(row.get("unrealized_pnl")),
            "unrealized_p": n(row.get("unrealized_pnl_pct")),
            "chg_pct": n(row.get("day_change_pct")),
        }
    return {
        "snapshot_id": snapshot_id,
        "cycle_ts": snap.get("cycle_ts"),
        "source": "portfolio_readonly_tables",
        "total_assets": n(snap.get("total_assets")),
        "market_val": n(snap.get("market_value")),
        "cash": n(snap.get("cash")),
        "buying_power": n(snap.get("buying_power")),
        "total_cost": n(snap.get("total_cost")),
        "total_pnl": n(snap.get("total_pnl")),
        "total_pnl_pct": n(snap.get("total_pnl_pct")),
        "integrity_flag": bool(snap.get("integrity_flag")),
        "integrity_flag_reason": snap.get("integrity_reason"),
        "positions": positions,
    }


def latest_portfolio_fallback(dataset: Dict[str, Any]) -> Dict[str, Any]:
    portfolio = dataset.get("portfolio") if isinstance(dataset.get("portfolio"), dict) else {}
    if not portfolio:
        return {}
    return {
        "snapshot_id": None,
        "cycle_ts": portfolio.get("cycle_ts"),
        "source": "dataset_portfolio_fallback",
        "total_assets": n(portfolio.get("total_assets")),
        "market_val": n(portfolio.get("market_val") or portfolio.get("total_value")),
        "cash": n(portfolio.get("cash")),
        "buying_power": n(portfolio.get("buying_power")),
        "total_cost": n(portfolio.get("total_cost")),
        "total_pnl": n(portfolio.get("total_pnl")),
        "total_pnl_pct": n(portfolio.get("total_pnl_pct")),
        "integrity_flag": bool(portfolio.get("integrity_flag")),
        "integrity_flag_reason": portfolio.get("integrity_flag_reason"),
        "positions": portfolio.get("positions") if isinstance(portfolio.get("positions"), dict) else {},
    }


def load_history(cur: Any, tickers: Iterable[str], lookback_days: int) -> Dict[str, Dict[str, float]]:
    tickers = sorted({str(t).upper() for t in tickers if t})
    if not tickers:
        return {}
    start = (datetime.now() - timedelta(days=lookback_days + 10)).strftime("%Y-%m-%d")
    placeholders = ",".join(["%s"] * len(tickers))
    cur.execute(
        f"""
        SELECT ticker, bar_date, close_price
        FROM historical_prices
        WHERE ticker IN ({placeholders})
          AND bar_date >= %s
          AND ktype = 'K_DAY'
        ORDER BY ticker ASC, bar_date ASC
        """,
        tuple(tickers) + (start,),
    )
    hist: Dict[str, Dict[str, float]] = {t: {} for t in tickers}
    for row in cur.fetchall():
        t = str(row.get("ticker") or "").upper()
        d = str(row.get("bar_date"))[:10]
        c = n(row.get("close_price"))
        if t and d and c > 0:
            hist.setdefault(t, {})[d] = c
    return hist


def returns_from_prices(prices: Dict[str, float]) -> Dict[str, float]:
    dates = sorted(prices)
    out: Dict[str, float] = {}
    prev = None
    for d in dates:
        price = prices[d]
        if prev and prev > 0 and price > 0:
            out[d] = price / prev - 1.0
        prev = price
    return out


def mean(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


def stdev(vals: List[float]) -> float:
    if len(vals) < 2:
        return 0.0
    m = mean(vals)
    return math.sqrt(sum((v - m) ** 2 for v in vals) / (len(vals) - 1))


def quantile(vals: List[float], q: float) -> float:
    if not vals:
        return 0.0
    data = sorted(vals)
    if len(data) == 1:
        return data[0]
    pos = (len(data) - 1) * q
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return data[lo]
    return data[lo] + (data[hi] - data[lo]) * (pos - lo)


def max_drawdown_from_returns(returns: Dict[str, float]) -> float:
    peak = 1.0
    value = 1.0
    max_dd = 0.0
    for d in sorted(returns):
        value *= 1.0 + returns[d]
        if value > peak:
            peak = value
        if peak > 0:
            max_dd = min(max_dd, value / peak - 1.0)
    return max_dd


def beta_to(series: Dict[str, float], benchmark: Dict[str, float]) -> Optional[float]:
    dates = sorted(set(series) & set(benchmark))
    if len(dates) < 10:
        return None
    xs = [benchmark[d] for d in dates]
    ys = [series[d] for d in dates]
    mx, my = mean(xs), mean(ys)
    var_x = sum((x - mx) ** 2 for x in xs)
    if var_x == 0:
        return None
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(dates)))
    return cov / var_x


def correlation(a: Dict[str, float], b: Dict[str, float]) -> Optional[float]:
    dates = sorted(set(a) & set(b))
    if len(dates) < 10:
        return None
    xs = [a[d] for d in dates]
    ys = [b[d] for d in dates]
    sx, sy = stdev(xs), stdev(ys)
    if sx == 0 or sy == 0:
        return None
    mx, my = mean(xs), mean(ys)
    cov = sum((xs[i] - mx) * (ys[i] - my) for i in range(len(dates))) / (len(dates) - 1)
    return cov / (sx * sy)


def portfolio_returns(returns: Dict[str, Dict[str, float]], weights: Dict[str, float]) -> Dict[str, float]:
    all_dates = sorted({d for ticker in weights for d in returns.get(ticker, {})})
    out: Dict[str, float] = {}
    for d in all_dates:
        total_weight = 0.0
        ret = 0.0
        for ticker, weight in weights.items():
            r = returns.get(ticker, {}).get(d)
            if r is None:
                continue
            total_weight += weight
            ret += weight * r
        if total_weight >= 0.50:
            out[d] = ret / total_weight
    return out


def exposure_maps(dataset: Dict[str, Any], weights: Dict[str, float]) -> Tuple[Dict[str, float], Dict[str, float]]:
    security = dataset.get("security_master") if isinstance(dataset.get("security_master"), dict) else {}
    sector: Dict[str, float] = {}
    asset_type: Dict[str, float] = {}
    for ticker, weight in weights.items():
        row = security.get(ticker) if isinstance(security.get(ticker), dict) else {}
        sector_name = str(row.get("sector") or "UNKNOWN")
        asset_name = str(row.get("asset_type") or "UNKNOWN")
        sector[sector_name] = sector.get(sector_name, 0.0) + weight
        asset_type[asset_name] = asset_type.get(asset_name, 0.0) + weight
    return sector, asset_type


def build_risk_model(dataset: Dict[str, Any], portfolio: Dict[str, Any], hist: Dict[str, Dict[str, float]], lookback_days: int) -> Dict[str, Any]:
    positions = portfolio.get("positions") if isinstance(portfolio.get("positions"), dict) else {}
    portfolio_value = n(portfolio.get("total_assets") or portfolio.get("market_val"))
    cash = n(portfolio.get("cash"))
    weights = {}
    for ticker, pos in positions.items():
        value = n((pos or {}).get("mkt_val") or (pos or {}).get("market_value"))
        if portfolio_value > 0 and value > 0:
            weights[str(ticker).upper()] = value / portfolio_value
    cash_weight = cash / portfolio_value if portfolio_value else 0.0

    ticker_returns = {ticker: returns_from_prices(prices) for ticker, prices in hist.items()}
    port_rets = portfolio_returns(ticker_returns, weights)
    ret_vals = list(port_rets.values())
    var95_pct = max(0.0, -quantile(ret_vals, 0.05))
    var99_pct = max(0.0, -quantile(ret_vals, 0.01))
    tail = [r for r in ret_vals if r <= quantile(ret_vals, 0.05)]
    es95_pct = max(0.0, -mean(tail)) if tail else 0.0
    vol_ann = stdev(ret_vals) * math.sqrt(TRADING_DAYS) if ret_vals else 0.0
    max_dd = max_drawdown_from_returns(port_rets)
    spy_beta = beta_to(port_rets, ticker_returns.get("SPY", {}))

    position_rows = []
    for ticker, pos in sorted(positions.items()):
        t = str(ticker).upper()
        r = ticker_returns.get(t, {})
        vals = list(r.values())
        price_dates = sorted(hist.get(t, {}))
        px = hist.get(t, {}).get(price_dates[-1]) if price_dates else n((pos or {}).get("price"))
        value = n((pos or {}).get("mkt_val") or (pos or {}).get("market_value"))
        p_var95 = max(0.0, -quantile(vals, 0.05))
        p_var99 = max(0.0, -quantile(vals, 0.01))
        position_rows.append({
            "ticker": t,
            "market_value": round(value, 2),
            "weight": round(weights.get(t, 0.0), 6),
            "last_close": round(px, 4) if px else None,
            "history_points": len(hist.get(t, {})),
            "return_points": len(vals),
            "first_date": price_dates[0] if price_dates else None,
            "last_date": price_dates[-1] if price_dates else None,
            "volatility_annualized": round(stdev(vals) * math.sqrt(TRADING_DAYS), 6) if vals else None,
            "historical_var_95_pct": round(p_var95, 6),
            "historical_var_95_dollars": round(value * p_var95, 2),
            "historical_var_99_pct": round(p_var99, 6),
            "historical_var_99_dollars": round(value * p_var99, 2),
            "max_drawdown": round(max_drawdown_from_returns(r), 6),
            "beta_to_spy": round(beta_to(r, ticker_returns.get("SPY", {})), 6) if beta_to(r, ticker_returns.get("SPY", {})) is not None else None,
            "beta_to_qqq": round(beta_to(r, ticker_returns.get("QQQ", {})), 6) if beta_to(r, ticker_returns.get("QQQ", {})) is not None else None,
        })

    sector_exp, asset_exp = exposure_maps(dataset, weights)
    factor_betas = {}
    for factor in ["SPY", "QQQ", "IWM", "TLT", "GLD", "UUP", "HYG", "XLK", "XLF"]:
        b = beta_to(port_rets, ticker_returns.get(factor, {}))
        if b is not None:
            factor_betas[factor] = round(b, 6)

    top_tickers = [r["ticker"] for r in sorted(position_rows, key=lambda x: x["market_value"], reverse=True)[:12]]
    corr = {}
    for i, a in enumerate(top_tickers):
        corr[a] = {}
        for b in top_tickers:
            c = correlation(ticker_returns.get(a, {}), ticker_returns.get(b, {}))
            corr[a][b] = round(c, 4) if c is not None else None

    constraints = dataset.get("portfolio_constraints") if isinstance(dataset.get("portfolio_constraints"), dict) else {}
    max_single = n(constraints.get("max_single_name_weight"), 0.30)
    min_cash = n(constraints.get("min_cash_weight"), 0.05)
    max_theme = n(constraints.get("max_theme_weight"), 0.45)
    breaches = []
    for row in position_rows:
        if row["weight"] > max_single:
            breaches.append({
                "type": "max_single_name_weight",
                "ticker": row["ticker"],
                "value": row["weight"],
                "limit": max_single,
            })
    if cash_weight < min_cash:
        breaches.append({"type": "min_cash_weight", "value": cash_weight, "limit": min_cash})
    for sector, weight in sector_exp.items():
        if weight > max_theme:
            breaches.append({"type": "max_theme_weight", "sector": sector, "value": weight, "limit": max_theme})

    dates = sorted(port_rets)
    return {
        "version": "v1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": "historical_risk_model.py",
        "method": "Moomoo historical daily close returns; historical VaR/CVaR; factor beta by covariance",
        "portfolio_source": portfolio.get("source"),
        "portfolio_snapshot_id": portfolio.get("snapshot_id"),
        "lookback_days": lookback_days,
        "price_start": dates[0] if dates else None,
        "price_end": dates[-1] if dates else None,
        "return_observations": len(ret_vals),
        "portfolio_value": round(portfolio_value, 2),
        "cash": round(cash, 2),
        "cash_weight": round(cash_weight, 6),
        "invested_weight": round(sum(weights.values()), 6),
        "historical_var": {
            "confidence_95": {
                "daily_pct": round(var95_pct, 6),
                "daily_dollars": round(portfolio_value * var95_pct, 2),
            },
            "confidence_99": {
                "daily_pct": round(var99_pct, 6),
                "daily_dollars": round(portfolio_value * var99_pct, 2),
            },
            "expected_shortfall_95": {
                "daily_pct": round(es95_pct, 6),
                "daily_dollars": round(portfolio_value * es95_pct, 2),
            },
        },
        "volatility_annualized": round(vol_ann, 6),
        "max_drawdown": round(max_dd, 6),
        "beta_to_spy": round(spy_beta, 6) if spy_beta is not None else None,
        "factor_exposures": {
            "factor_betas": factor_betas,
            "sector_exposure": {k: round(v, 6) for k, v in sorted(sector_exp.items())},
            "asset_type_exposure": {k: round(v, 6) for k, v in sorted(asset_exp.items())},
        },
        "constraint_breaches": breaches,
        "positions": position_rows,
        "correlation_matrix_top_positions": corr,
        "execution_protocol": {
            "research_only": True,
            "orders_generated": False,
            "execution_authority": "CIO_ONLY",
        },
    }


def build_portfolio_targets(dataset: Dict[str, Any], portfolio: Dict[str, Any], risk_model: Dict[str, Any]) -> Dict[str, Any]:
    constraints = dataset.get("portfolio_constraints") if isinstance(dataset.get("portfolio_constraints"), dict) else {}
    max_single = n(constraints.get("max_single_name_weight"), 0.30)
    min_cash = n(constraints.get("min_cash_weight"), 0.05)
    portfolio_value = n(portfolio.get("total_assets") or portfolio.get("market_val"))
    cash_weight = n(risk_model.get("cash_weight"))
    positions = risk_model.get("positions") if isinstance(risk_model.get("positions"), list) else []

    current_weights = {row["ticker"]: n(row.get("weight")) for row in positions}
    target_weights = dict(current_weights)
    target_cash = cash_weight
    actions = []

    for ticker, weight in list(target_weights.items()):
        if weight > max_single:
            excess = weight - max_single
            target_weights[ticker] = max_single
            target_cash += excess
            actions.append({
                "ticker": ticker,
                "action_type": "risk_cap_research_only",
                "current_weight": round(weight, 6),
                "target_weight": round(max_single, 6),
                "reason": "Above max_single_name_weight constraint.",
                "order_instruction": "NONE",
            })

    if target_cash < min_cash and target_weights:
        needed = min_cash - target_cash
        reducible = {t: w for t, w in target_weights.items() if w > 0.02}
        total_reducible = sum(reducible.values())
        if total_reducible > 0:
            for ticker, weight in reducible.items():
                reduction = needed * (weight / total_reducible)
                target_weights[ticker] = max(0.0, weight - reduction)
            target_cash += needed
            actions.append({
                "ticker": "CASH",
                "action_type": "cash_floor_research_only",
                "current_weight": round(cash_weight, 6),
                "target_weight": round(target_cash, 6),
                "reason": "Portfolio cash is below min_cash_weight.",
                "order_instruction": "NONE",
            })

    # Normalize if cap/cash changes pushed total over 1 due to imperfect broker accounting.
    total = target_cash + sum(target_weights.values())
    if total > 0:
        scale = min(1.0, 1.0 / total) if total > 1.0 else 1.0
        target_weights = {t: w * scale for t, w in target_weights.items()}
        target_cash *= scale

    rows = []
    for ticker in sorted(target_weights):
        cur_w = current_weights.get(ticker, 0.0)
        tgt_w = target_weights[ticker]
        rows.append({
            "ticker": ticker,
            "current_weight": round(cur_w, 6),
            "target_weight": round(tgt_w, 6),
            "delta_weight": round(tgt_w - cur_w, 6),
            "current_value": round(cur_w * portfolio_value, 2),
            "target_value": round(tgt_w * portfolio_value, 2),
            "research_only": True,
        })

    run_id = f"PTO-{datetime.now().strftime('%Y%m%d%H%M%S')}-{sha_short(json_dumps(rows))}"
    return {
        "version": "v1.0",
        "run_id": run_id,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": "research_only",
        "objective": "constraint-aware target weights for CIO review; no order generation",
        "portfolio_snapshot_id": portfolio.get("snapshot_id"),
        "portfolio_value": round(portfolio_value, 2),
        "constraints": constraints,
        "current_weights": {
            **{k: round(v, 6) for k, v in sorted(current_weights.items())},
            "CASH": round(cash_weight, 6),
        },
        "target_weights": {
            **{k: round(v, 6) for k, v in sorted(target_weights.items())},
            "CASH": round(target_cash, 6),
        },
        "targets_by_ticker": rows,
        "actions": actions,
        "execution_protocol": {
            "orders_generated": False,
            "fills_expected": False,
            "trade_lifecycle": "CIO owns execution outside this software layer",
            "order_instruction": "NONE",
        },
    }


def write_database(risk_model: Dict[str, Any], targets: Dict[str, Any]) -> str:
    conn = get_connection()
    run_id = f"RISK-{datetime.now().strftime('%Y%m%d%H%M%S')}-{sha_short(json_dumps(risk_model))}"
    try:
        cur = conn.cursor()
        hv = risk_model.get("historical_var") or {}
        v95 = ((hv.get("confidence_95") or {}).get("daily_dollars"))
        v99 = ((hv.get("confidence_99") or {}).get("daily_dollars"))
        es95 = ((hv.get("expected_shortfall_95") or {}).get("daily_dollars"))
        cur.execute(
            """
            INSERT INTO risk_model_runs (
                run_id, generated_at, source_snapshot_id, price_start, price_end,
                lookback_days, position_count, portfolio_value,
                historical_var_95, historical_var_99, expected_shortfall_95,
                volatility_annualized, max_drawdown, beta_to_spy,
                metrics_json, positions_json, factor_exposures_json,
                correlation_json, breaches_json
            ) VALUES (
                %s,%s,%s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s,
                CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),
                CAST(%s AS JSON),CAST(%s AS JSON)
            )
            """,
            (
                run_id,
                risk_model["generated_at"],
                risk_model.get("portfolio_snapshot_id"),
                risk_model.get("price_start"),
                risk_model.get("price_end"),
                risk_model.get("lookback_days"),
                len(risk_model.get("positions") or []),
                risk_model.get("portfolio_value"),
                v95,
                v99,
                es95,
                risk_model.get("volatility_annualized"),
                risk_model.get("max_drawdown"),
                risk_model.get("beta_to_spy"),
                json_dumps(risk_model),
                json_dumps(risk_model.get("positions") or []),
                json_dumps(risk_model.get("factor_exposures") or {}),
                json_dumps(risk_model.get("correlation_matrix_top_positions") or {}),
                json_dumps(risk_model.get("constraint_breaches") or []),
            ),
        )
        cur.execute(
            """
            INSERT INTO portfolio_optimizer_runs (
                run_id, generated_at, source_snapshot_id, status, objective,
                current_weights_json, target_weights_json, constraints_json,
                actions_json, notes
            ) VALUES (
                %s,%s,%s,%s,%s, CAST(%s AS JSON),CAST(%s AS JSON),CAST(%s AS JSON),
                CAST(%s AS JSON),%s
            )
            """,
            (
                targets["run_id"],
                targets["generated_at"],
                targets.get("portfolio_snapshot_id"),
                targets["status"],
                targets["objective"],
                json_dumps(targets.get("current_weights") or {}),
                json_dumps(targets.get("target_weights") or {}),
                json_dumps(targets.get("constraints") or {}),
                json_dumps(targets.get("actions") or []),
                "Research-only target weights. No orders generated.",
            ),
        )
        conn.commit()
        cur.close()
        return run_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def write_outputs(risk_model: Dict[str, Any], targets: Dict[str, Any]) -> None:
    RISK_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    RISK_OUTPUT.write_text(json.dumps(json_safe(risk_model), ensure_ascii=False, indent=2), encoding="utf-8")
    TARGET_OUTPUT.write_text(json.dumps(json_safe(targets), ensure_ascii=False, indent=2), encoding="utf-8")


def write_raw_signal(risk_model: Dict[str, Any]) -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    from dotenv import load_dotenv
    from core.db import write_raw_signal

    load_dotenv(PROJECT_ROOT / ".env")
    hv = risk_model.get("historical_var") or {}
    v95 = (hv.get("confidence_95") or {}).get("daily_dollars")
    v99 = (hv.get("confidence_99") or {}).get("daily_dollars")
    summary = (
        f"Historical risk model: VaR95 ${n(v95):,.2f} | VaR99 ${n(v99):,.2f} | "
        f"vol {n(risk_model.get('volatility_annualized')):.2%} | "
        f"breaches {len(risk_model.get('constraint_breaches') or [])}"
    )
    write_raw_signal(
        source="Historical_Risk_Model",
        ingestion_method="historical_prices_portfolio_var",
        raw_payload=json_safe(risk_model),
        raw_text=summary,
        signal_type="risk",
        suspected_category="PORTFOLIO_RISK_MODEL",
        suspected_entities=[r.get("ticker") for r in risk_model.get("positions") or []],
        suspected_impact="medium",
        quality_score=1.0 if risk_model.get("return_observations", 0) >= 20 else 0.6,
        quality_flags={
            "orders_generated": False,
            "research_only": True,
            "return_observations": risk_model.get("return_observations"),
        },
    )


def run(lookback_days: int) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    ensure_tables()
    dataset = load_dataset()
    conn = get_connection()
    try:
        cur = conn.cursor(dictionary=True)
        portfolio = latest_portfolio_from_tables(cur) or latest_portfolio_fallback(dataset)
        if not portfolio:
            raise RuntimeError("No portfolio snapshot available for risk model.")
        tickers = sorted(set((portfolio.get("positions") or {}).keys()) | {"SPY", "QQQ", "IWM", "TLT", "GLD", "UUP", "HYG", "XLK", "XLF"})
        hist = load_history(cur, tickers, lookback_days)
        cur.close()
    finally:
        conn.close()

    risk_model = build_risk_model(dataset, portfolio, hist, lookback_days)
    targets = build_portfolio_targets(dataset, portfolio, risk_model)
    run_id = write_database(risk_model, targets)
    risk_model["run_id"] = run_id
    write_outputs(risk_model, targets)
    write_raw_signal(risk_model)
    return risk_model, targets, run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Build BlueLotus historical risk model")
    parser.add_argument("--lookback-days", type=int, default=180)
    args = parser.parse_args()

    risk_model, targets, run_id = run(args.lookback_days)
    hv = risk_model.get("historical_var") or {}
    print("BlueLotus historical risk model generated.")
    print(f"Run ID: {run_id}")
    print(f"Observations: {risk_model.get('return_observations')} | Positions: {len(risk_model.get('positions') or [])}")
    print(f"VaR95: ${(hv.get('confidence_95') or {}).get('daily_dollars', 0):,.2f}")
    print(f"Target layer: {targets.get('status')} | orders_generated=False")


if __name__ == "__main__":
    main()

