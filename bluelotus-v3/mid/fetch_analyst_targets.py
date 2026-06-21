"""
BlueLotus Fund - Analyst Targets Fetcher
Fetches analyst consensus targets from Moomoo OpenD
Batches: 10 tickers per batch, 10 second pause between batches
  Watchlist: len(WATCHLIST) tickers — matches ingest_u.py WATCHLIST_83
Save to: C:/PortfolioAgent/fetch_analyst_targets.py
Run:     python fetch_analyst_targets.py
"""

import json, sys, os, time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ticker_universe import get_universe

# WO-RD-20260607-003 v1.3 — expanded to match WATCHLIST_83 in ingest_u.py
# All tickers receive identical analyst target fetching
# Note: ETFs (GLD, SLV, TLT, IBIT, QTUM) and some small-caps may return
#       no analyst data — handled gracefully by fetch_batch()
WATCHLIST = get_universe()

BATCH_SIZE   = 10   # 10 tickers per batch
BATCH_PAUSE  = 10   # 10 seconds between batches
TICKER_PAUSE = 0.20 # 0.2 seconds between individual ticker calls


def fetch_batch(ctx, tickers, offset, total):
    import moomoo as ft
    results = {}
    for i, ticker in enumerate(tickers):
        code = "US." + ticker
        try:
            ret, data = ctx.get_research_analyst_consensus(code)
            if ret == ft.RET_OK and data:
                avg            = float(data.get("average", 0) or 0)
                total_analysts = int(data.get("total",   0) or 0)
                results[ticker] = {
                    "average":    round(avg, 2),
                    "highest":    round(float(data.get("highest", 0) or 0), 2),
                    "lowest":     round(float(data.get("lowest",  0) or 0), 2),
                    "rating":     str(data.get("rating", "")),
                    "buy":        int(data.get("buy",        0) or 0),
                    "hold":       int(data.get("hold",       0) or 0),
                    "sell":       int(data.get("sell",       0) or 0),
                    "strong_buy": int(data.get("strong_buy", 0) or 0),
                    "total":      total_analysts,
                    "source":     "Moomoo OpenD get_research_analyst_consensus",
                }
                print(f"  [{offset+i+1:02d}/{total}] {ticker:<6} avg=${avg:.2f} | {total_analysts} analysts")
            else:
                results[ticker] = {"average": 0, "error": "no data returned", "source": "Moomoo OpenD"}
                print(f"  [{offset+i+1:02d}/{total}] {ticker:<6} no data")
            time.sleep(TICKER_PAUSE)
        except Exception as e:
            results[ticker] = {"average": 0, "error": str(e), "source": "Moomoo OpenD"}
            print(f"  [{offset+i+1:02d}/{total}] {ticker:<6} error: {e}")
    return results


def fetch_analyst_targets(tickers):
    import moomoo as ft
    all_results = {}
    total       = len(tickers)
    batches     = [tickers[i:i+BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

    print(f"Total: {total} tickers | {len(batches)} batches x {BATCH_SIZE} per batch | {BATCH_PAUSE}s pause between batches")
    print(f"Estimated time: ~{int(len(batches)*((BATCH_SIZE*TICKER_PAUSE)+BATCH_PAUSE)//60)}m {int(len(batches)*((BATCH_SIZE*TICKER_PAUSE)+BATCH_PAUSE)%60)}s\n")

    for b_idx, batch in enumerate(batches):
        print(f"--- Batch {b_idx+1}/{len(batches)}: {', '.join(batch)} ---")
        try:
            ctx = ft.OpenQuoteContext(host="127.0.0.1", port=11111)
            offset  = b_idx * BATCH_SIZE
            results = fetch_batch(ctx, batch, offset, total)
            all_results.update(results)
            ctx.close()
            filled_batch = sum(1 for d in results.values() if d.get("average", 0) > 0)
            print(f"Batch {b_idx+1} done: {filled_batch}/{len(batch)} filled")
        except Exception as e:
            print(f"Batch {b_idx+1} connection error: {e}")
            for ticker in batch:
                all_results[ticker] = {"average": 0, "error": str(e), "source": "Moomoo OpenD"}

        if b_idx < len(batches) - 1:
            print(f"Pausing {BATCH_PAUSE}s...\n")
            time.sleep(BATCH_PAUSE)

    return all_results


if __name__ == "__main__":
    fetch_time = datetime.now()
    print(f"BlueLotus Analyst Target Fetcher — {fetch_time.strftime('%Y-%m-%d %H:%M:%S SGT')}\n")

    targets = fetch_analyst_targets(WATCHLIST)

    filled = sum(1 for d in targets.values() if d.get("average", 0) > 0)
    output = {
        "fetch_timestamp_sgt": fetch_time.strftime("%Y-%m-%d %H:%M:%S SGT"),
        "source":              "Moomoo OpenD 127.0.0.1:11111 get_research_analyst_consensus",
        "ticker_count":        len(targets),
        "filled_count":        filled,
        "batch_size":          BATCH_SIZE,
        "batch_pause_seconds": BATCH_PAUSE,
        "targets":             targets,
    }

    # Save to project root (C:\bluelotus3\analyst_targets.json)
    # ingest.py Layer 4 looks for analyst_targets.json in the project root,
    # not in mid\ — see ingest.py line 1839 path resolution logic
    _script_dir  = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(_script_dir)  # up one level from mid/
    out_path = os.path.join(_project_root, "analyst_targets.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*55}")
    print(f"✅ Saved: {out_path}")
    print(f"   Timestamp: {fetch_time.strftime('%Y-%m-%d %H:%M:%S SGT')}")
    print(f"   Tickers:   {len(targets)}")
    print(f"   Filled:    {filled}/{len(targets)}")
    print(f"{'='*55}")
    print(f"\nUpload analyst_targets.json to claude.ai conversation.")

