"""
fetch_moomoo_intelligence()
━━━━━━━━━━━━━━━━━━━━━━━━━━
Pulls institutional-grade signals from Moomoo OpenD for
portfolio positions + watchlist tickers. Zero extra cost.

Covers:
  L5 Sentiment  — derivative unusual, technical unusual
  L7 Institutional — analyst ratings, consensus, insider trades,
                     institutional holders, 13F changes,
                     Morningstar, financial unusual
"""

import moomoo as ft
import moomoo.common.ft_logger as _ftl
from datetime import datetime, timedelta

_ftl.logger.enable_console_log(False)

OPEND_HOST = "127.0.0.1"
OPEND_PORT = 11111

def _ctx():
    return ft.OpenQuoteContext(host=OPEND_HOST, port=OPEND_PORT)

def _safe(fn, *args, **kwargs):
    """Call a quote method safely, return (ok, data_or_error)."""
    try:
        ret, data = fn(*args, **kwargs)
        if ret == ft.RET_OK:
            return True, data
        return False, str(data)
    except Exception as e:
        return False, str(e)


def fetch_analyst_ratings(tickers):
    """
    L7: Analyst ratings + consensus for given tickers.
    Uses get_research_analyst_consensus for buy/hold/sell counts and label.
    Uses get_research_morningstar_report for fair value and star rating.
    """
    ctx = _ctx()
    results = {}
    try:
        for t in tickers:
            code = f"US.{t}"
            info = {"ticker": t, "ratings": None, "consensus": None,
                    "price_target": None, "morningstar": None}

            # Analyst consensus — returns buy/hold/sell counts + label
            ok, data = _safe(ctx.get_research_analyst_consensus, code)
            if ok and isinstance(data, dict):
                raw_rating = data.get("rating", "")
                # Map numeric code to text label
                _rating_map = {1:"Strong Sell",2:"Sell",3:"Hold",4:"Buy",5:"Strong Buy"}
                try:
                    rating_num = int(float(str(raw_rating)))
                    info["consensus"] = _rating_map.get(rating_num, str(raw_rating))
                    info["consensus_num"] = rating_num
                except (ValueError, TypeError):
                    info["consensus"] = str(raw_rating)
                    info["consensus_num"] = 0
                info["price_target"] = float(data.get("average", 0) or 0)
                # CONFIRMED via analyst_targets.json verification (2026-06-03):
                # get_research_analyst_consensus returns buy/hold/sell as PERCENTAGES
                # (0-100 scale). buy+hold+sell sums to ~100 for all 78 filled tickers.
                # total_analysts is the analyst HEADCOUNT (separate field, often 0).
                # safe_total: use total_analysts if available, otherwise sum of pcts
                # (used only for headcount display, NOT as a division denominator).
                total_analysts = int(data.get("total", 0) or 0)
                buy   = int(data.get("buy",   0) or 0)
                s_buy = int(data.get("strong_buy", 0) or 0)
                hold  = int(data.get("hold",  0) or 0)
                sell  = int(data.get("sell",  0) or 0)
                under = int(data.get("underperform", 0) or 0)
                count_sum = buy + s_buy + hold + sell + under
                # Use total_analysts if returned; fall back to count_sum
                safe_total = total_analysts if total_analysts > 0 else count_sum
                if count_sum > 0:
                    info["ratings"] = {
                        "buy":            buy + s_buy,    # percentage (0-100)
                        "hold":           hold,           # percentage (0-100)
                        "sell":           sell + under,   # percentage (0-100)
                        "total":          safe_total,     # safe denominator
                        "total_analysts": safe_total,     # explicit alias
                    }

            # Morningstar report — correct field names per SDK
            ok, data = _safe(ctx.get_research_morningstar_report, code)
            if ok and isinstance(data, dict):
                info["morningstar"] = {
                    "rating":         str(data.get("star_rating", "")),
                    "fair_value":     float(data.get("fair_value", 0) or 0),
                    "uncertainty":    str(data.get("uncertainty_label", "")),
                    "moat":           str(data.get("economic_moat_label", "")),
                    "financial_health": str(data.get("financial_health_label", "")),
                }

            results[t] = info
    except Exception as e:
        print(f"  [MM Intel] analyst_ratings error: {e}")
    finally:
        ctx.close()
    return results


def fetch_unusual_signals(tickers):
    """
    L5 + L7: Derivative unusual (options flow) + technical unusual signals.
    Returns dict {ticker: {derivative: [...], technical: [...]}}
    """
    ctx = _ctx()
    results = {}
    try:
        for t in tickers:
            code = f"US.{t}"
            info = {"ticker": t, "derivative": [], "technical": [], "financial": []}

            def _parse_unusual(data, max_items=3):
                """Parse unusual signal — content is a JSON string."""
                results = []
                if not isinstance(data, dict): return results
                raw = data.get("content", "")
                if not raw: return results
                import json
                try:
                    items = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(items, list):
                        for item in items[:max_items]:
                            if isinstance(item, dict):
                                results.append({
                                    "signal": str(item.get("title", item.get("signal", "")))[:100],
                                    "detail": str(item.get("content", item.get("detail", "")))[:120],
                                })
                    elif isinstance(items, dict):
                        results.append({
                            "signal": str(items.get("title", raw[:80])),
                            "detail": str(items.get("content", ""))[:120],
                        })
                except Exception:
                    # content is plain text — use as-is
                    if isinstance(raw, str) and len(raw) > 5:
                        results.append({"signal": raw[:100], "detail": ""})
                return results

            # Derivative unusual (options flow)
            ok, data = _safe(ctx.get_derivative_unusual, code,
                             time_range=7, language_id=2)
            if ok:
                info["derivative"] = _parse_unusual(data)

            # Technical unusual
            ok, data = _safe(ctx.get_technical_unusual, code,
                             time_range=7, language_id=2)
            if ok:
                info["technical"] = _parse_unusual(data)

            # Financial unusual
            ok, data = _safe(ctx.get_financial_unusual, code,
                             time_range=7, language_id=2)
            if ok:
                info["financial"] = _parse_unusual(data, max_items=2)

            results[t] = info
    except Exception as e:
        print(f"  [MM Intel] unusual_signals error: {e}")
    finally:
        ctx.close()
    return results


def fetch_insider_trades(tickers):
    """
    L7: Insider buying/selling for given tickers (last 90 days).
    Returns dict {ticker: [trades]}
    """
    ctx = _ctx()
    results = {}
    try:
        for t in tickers:
            code = f"US.{t}"
            ok, data = _safe(ctx.get_insider_trade_list, code, num=5)
            trades = []
            if ok and hasattr(data, "empty") and not data.empty:
                for _, row in data.iterrows():
                    trades.append({
                        "name":        str(row.get("holder_name", "")),
                        "title":       str(row.get("position", "")),
                        "trans_type":  str(row.get("trans_type", "")),
                        "shares":      int(row.get("shares", 0) or 0),
                        "price":       float(row.get("price", 0) or 0),
                        "date":        str(row.get("trans_date", "")),
                    })
            results[t] = trades
    except Exception as e:
        print(f"  [MM Intel] insider_trades error: {e}")
    finally:
        ctx.close()
    return results


def fetch_institutional_holders(tickers):
    """
    L7: Top institutional holders + recent 13F changes.
    Returns dict {ticker: {institutions: [...], changes: [...]}}
    """
    ctx = _ctx()
    results = {}
    today = datetime.now().strftime("%Y-%m-%d")
    q_ago = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
    try:
        for t in tickers:
            code = f"US.{t}"
            info = {"ticker": t, "institutions": [], "changes": []}

            # Top institutional holders
            ok, data = _safe(ctx.get_shareholders_institutional, code, num=5)
            if ok and hasattr(data, "empty") and not data.empty:
                for _, row in data.iterrows():
                    info["institutions"].append({
                        "name":    str(row.get("holder_name", "")),
                        "shares":  int(row.get("quantity", 0) or 0),
                        "pct":     float(row.get("ratio", 0) or 0),
                    })

            # 13F holding changes
            ok, data = _safe(ctx.get_holding_change_list, code,
                             holder_type=ft.StockHolder.INSTITUTE,
                             start=q_ago, end=today)
            if ok and hasattr(data, "empty") and not data.empty:
                for _, row in data.iterrows():
                    info["changes"].append({
                        "name":   str(row.get("holder_name", "")),
                        "change": int(row.get("change_shares", 0) or 0),
                        "date":   str(row.get("report_date", "")),
                    })

            results[t] = info
    except Exception as e:
        print(f"  [MM Intel] institutional_holders error: {e}")
    finally:
        ctx.close()
    return results


def fetch_moomoo_intelligence(tickers):
    """
    Master function: pulls all Moomoo institutional intelligence
    for given tickers. Runs all 4 sub-fetches and returns unified dict.

    Returns:
    {
      "analyst":      {ticker: {ratings, consensus, price_target}},
      "unusual":      {ticker: {derivative, technical}},
      "insider":      {ticker: [trades]},
      "institutional":{ticker: {institutions, changes}},
      "summary":      [formatted signal strings for bulletin]
    }
    """
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching Moomoo institutional intelligence...")

    analyst       = fetch_analyst_ratings(tickers)
    unusual       = fetch_unusual_signals(tickers)
    insider       = fetch_insider_trades(tickers)
    institutional = fetch_institutional_holders(tickers)

    # Build summary signal list for bulletin injection
    summary = []

    for t in tickers:
        # Analyst signal — consensus label + price target
        a = analyst.get(t, {})
        if a.get("consensus"):
            pt = f" | Analyst Price Target: ${a['price_target']:.2f}" if a.get("price_target") and a["price_target"] > 0 else ""
            summary.append(f"[WALL ST. ANALYSTS] {t}: Wall St. Consensus: {a['consensus']}{pt}")
        if a.get("ratings"):
            r = a["ratings"]
            # CONFIRMED: buy/hold/sell are already PERCENTAGES (0-100 scale).
            # analyst_targets.json verification: buy+hold+sell sums to ~100
            # for all 78 filled tickers. total is the analyst headcount (separate).
            # Print directly — no division needed.
            _total = r.get("total", 0)
            _headcount = f" ({_total} analysts)" if _total > 0 else ""
            summary.append(
                f"[ANALYST RATINGS] {t}: Buy={r['buy']}% Hold={r['hold']}% "
                f"Sell={r['sell']}%{_headcount}"
            )
        if a.get("morningstar") and a["morningstar"].get("fair_value"):
            ms = a["morningstar"]
            unc  = f" | Uncertainty: {ms['uncertainty']}" if ms.get("uncertainty") else ""
            moat = f" | Moat: {ms['moat']}" if ms.get("moat") else ""
            health = f" | Health: {ms['financial_health']}" if ms.get("financial_health") else ""
            summary.append(f"[MORNINGSTAR] {t}: ⭐{ms['rating']}/5 Stars | Fair Value: ${ms['fair_value']:.2f}{unc}{moat}{health}")
            # Divergence alert — when Morningstar disagrees with analyst consensus.
            # buy is already a percentage (0-100) — compare directly, no division.
            consensus_num = a.get("consensus_num", 0)
            ratings = a.get("ratings", {})
            buy_pct = ratings.get("buy", 0) if ratings else 0
            if ms["fair_value"] > 0 and buy_pct >= 70 and ms["rating"] in ["1","2"]:
                summary.append(
                    f"[WARNING DIVERGENCE] {t}: {buy_pct}% analysts say Buy but "
                    f"Morningstar rates only {ms['rating']}/5 stars -- independent valuation caution"
                )

        # Unusual signals
        u = unusual.get(t, {})
        for d in u.get("derivative", [])[:1]:
            if d.get("signal"):
                # BUG-013 FIX: store full untruncated text -- let Research/Publishing truncate for display
                summary.append(f"[OPTIONS FLOW] {t}: {d['signal']}")
        for tech in u.get("technical", [])[:1]:
            if tech.get("signal"):
                summary.append(f"[TECHNICAL] {t}: {tech['signal']}")
        for fin in u.get("financial", [])[:1]:
            if fin.get("signal"):
                summary.append(f"[FINANCIAL] {t}: {fin['signal']}")

        # Insider signal
        trades = insider.get(t, [])
        for tr in trades[:1]:
            if tr.get("name"):
                summary.append(
                    f"[INSIDER] {t}: {tr['name']} ({tr['title']}) "
                    f"{tr['trans_type']} {tr['shares']:,}sh @ ${tr['price']:.2f} on {tr['date']}"
                )

        # Institutional changes
        inst = institutional.get(t, {})
        for chg in inst.get("changes", [])[:1]:
            if chg.get("name") and chg.get("change"):
                direction = "▲ ADD" if chg["change"] > 0 else "▼ REDUCE"
                summary.append(
                    f"[13F] {t}: {chg['name']} {direction} "
                    f"{abs(chg['change']):,}sh ({chg['date']})"
                )

    # BUG-007 FIX: deduplicate summary list — same signal can appear twice
    # if fetch runs while previous cycle signals are still in memory
    seen = set()
    deduped = []
    for line in summary:
        key = line.strip()[:200]  # deterministic dedup key
        if key not in seen:
            seen.add(key)
            deduped.append(line)
    removed = len(summary) - len(deduped)
    if removed > 0:
        print(f"  Moomoo Intel: deduped {removed} duplicate signal(s)")
    summary = deduped

    total_signals = len(summary)
    print(f"  Moomoo Intel: {total_signals} signals across {len(tickers)} tickers")

    return {
        "analyst":       analyst,
        "unusual":       unusual,
        "insider":       insider,
        "institutional": institutional,
        "summary":       summary,
    }
