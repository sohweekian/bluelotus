"""
BlueLotus MID — Tech Publication Ticker Mapping Probe
probe_ticker_mapping.py

PURPOSE:
  P2-06 verification probe. Reads the last 200 articles from
  tech_publication_signals table, applies the proposed COMPANY_TICKER_MAP
  lookup, and reports:

    1. How many articles currently have tickers_mentioned = []  (N/A)
    2. How many would gain a ticker from the name map
    3. Sample matches for manual verification (10 articles)
    4. False-positive check — show context around each match

  No writes. Read-only. Safe to run at any time.

  After verifying the probe output, the same COMPANY_TICKER_MAP
  is transplanted into fetch_tech_publications.py _extract_tickers()
  as Tier 4.

SOURCE:
  DB table : tech_publication_signals
  Columns  : id, source, headline, summary, tickers_mentioned, fetched_at
  Confirmed from: create_gap_tables.py lines 460-490

  No external API calls. No Moomoo. No network.
  Pure DB read + deterministic string matching.

Run:
  cd C:\\bluelotus2
  python mid\\probe_ticker_mapping.py

Output:
  Console : full analysis
  File    : C:\\bluelotus2\\data\\probe_ticker_mapping_result.json
"""

import json
import os
import re
import sys
from datetime import datetime

_script_dir   = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
sys.path.insert(0, _project_root)
sys.path.insert(0, _script_dir)
from ticker_universe import COMPANY_TICKER_ALIAS_DICT, get_universe

OUTPUT_PATH = os.path.join(_project_root, "data", "probe_ticker_mapping_result.json")

# ─────────────────────────────────────────────────────────────────────────────
# COMPANY_TICKER_MAP — per WO-RD-20260604-002 P2-06 specification
# Keys: lowercase company name variants
# Values: watchlist ticker symbol
# Source: WO spec lines 771-805; confirmed against WATCHLIST_83 in
#         fetch_tech_publications.py lines 249-262
# ─────────────────────────────────────────────────────────────────────────────
COMPANY_TICKER_MAP = COMPANY_TICKER_ALIAS_DICT

# Watchlist — confirmed from fetch_tech_publications.py lines 249-262
WATCHLIST_83 = set(get_universe())


def _apply_name_map(text: str, existing_tickers: list) -> list:
    """
    Apply COMPANY_TICKER_MAP to text (case-insensitive).
    Returns list of NEW tickers found (not already in existing_tickers).
    Only returns tickers that are in WATCHLIST_83.
    """
    text_lower    = text.lower()
    existing_set  = {t.upper() for t in (existing_tickers or [])}
    new_tickers   = []
    matched_names = []

    for company_name, ticker in COMPANY_TICKER_MAP.items():
        if ticker not in WATCHLIST_83:
            continue
        if ticker in existing_set:
            continue
        # Word-boundary match to avoid "arm" matching "army", "farm" etc.
        pattern = r'(?<![a-z])' + re.escape(company_name) + r'(?![a-z])'
        if re.search(pattern, text_lower):
            if ticker not in new_tickers:
                new_tickers.append(ticker)
                matched_names.append(company_name)

    return new_tickers, matched_names


def run_probe():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S SGT")
    print()
    print("=" * 65)
    print("  BlueLotus MID — Tech Pub Ticker Mapping Probe")
    print("  P2-06: COMPANY_TICKER_MAP coverage verification")
    print(f"  {ts}")
    print("=" * 65)

    # ─────────────────────────────────────────────────────────────────
    # STEP 1: Read latest 200 articles from DB
    # Columns: id, source, headline, summary, tickers_mentioned, fetched_at
    # Confirmed from create_gap_tables.py lines 460-490
    # ─────────────────────────────────────────────────────────────────
    print()
    print("STEP 1: Reading last 200 articles from tech_publication_signals...")

    try:
        from core.db import get_connection
        conn = get_connection()
        cur  = conn.cursor(dictionary=True)
        cur.execute("""
            SELECT id, source, headline, summary,
                   tickers_mentioned, fetched_at
            FROM tech_publication_signals
            ORDER BY fetched_at DESC
            LIMIT 200
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        print(f"  OK — {len(rows)} articles loaded")
    except Exception as e:
        print(f"  ERROR: {type(e).__name__}: {e}")
        return None

    # ─────────────────────────────────────────────────────────────────
    # STEP 2: Apply COMPANY_TICKER_MAP and collect results
    # ─────────────────────────────────────────────────────────────────
    print()
    print("STEP 2: Applying COMPANY_TICKER_MAP...")

    total          = len(rows)
    currently_na   = 0   # articles with no tickers
    would_gain     = 0   # articles that gain >= 1 ticker from name map
    already_tagged = 0   # articles already have tickers

    sample_matches    = []   # articles that gain tickers — for verification
    false_pos_risks   = []   # short company names that need manual check

    results = []

    for row in rows:
        headline = row.get("headline") or ""
        summary  = row.get("summary")  or ""
        full_text = f"{headline} {summary[:300]}"  # title + first 300 chars

        # Parse existing tickers
        raw_tickers = row.get("tickers_mentioned")
        if isinstance(raw_tickers, str):
            try:
                existing = json.loads(raw_tickers)
            except Exception:
                existing = []
        elif isinstance(raw_tickers, list):
            existing = raw_tickers
        else:
            existing = []

        if not existing:
            currently_na += 1

        # Apply name map
        new_tickers, matched_names = _apply_name_map(full_text, existing)

        gained = len(new_tickers) > 0
        if gained:
            would_gain += 1

        if existing:
            already_tagged += 1

        result = {
            "id":              row.get("id"),
            "source":          row.get("source"),
            "headline":        headline[:100],
            "existing":        existing,
            "new_from_map":    new_tickers,
            "matched_names":   matched_names,
            "combined":        sorted(set(existing + new_tickers)),
        }
        results.append(result)

        # Collect samples — articles that gain a ticker
        if gained and len(sample_matches) < 10:
            sample_matches.append({
                "source":        row.get("source"),
                "headline":      headline[:120],
                "was":           existing or ["N/A"],
                "gains":         new_tickers,
                "matched_names": matched_names,
                "context":       full_text[:200],
            })

    # ─────────────────────────────────────────────────────────────────
    # STEP 3: Print results
    # ─────────────────────────────────────────────────────────────────
    print()
    print("=" * 65)
    print("  RESULTS")
    print("=" * 65)
    print(f"  Total articles checked   : {total}")
    print(f"  Currently N/A (no ticker): {currently_na}  ({round(currently_na/total*100)}%)")
    print(f"  Already have tickers     : {already_tagged}  ({round(already_tagged/total*100)}%)")
    print(f"  Would GAIN ticker(s)     : {would_gain}  ({round(would_gain/total*100)}%)")
    print(f"  N/A reduction            : {min(would_gain, currently_na)}/{currently_na} articles fixed")

    na_reduction_pct = round(min(would_gain, currently_na) / currently_na * 100) if currently_na else 0
    target_met = na_reduction_pct >= 50
    print(f"  WO target (>=50% N/A fix): {'✅ MET' if target_met else '❌ NOT MET'} ({na_reduction_pct}%)")

    print()
    print("  Sample matches (first 10 articles gaining a ticker):")
    print("  " + "-" * 60)
    for i, s in enumerate(sample_matches, 1):
        print(f"  {i:2d}. [{s['source']}]")
        print(f"      Headline : {s['headline']}")
        print(f"      Was      : {s['was']}")
        print(f"      Gains    : {s['gains']}  (matched: {s['matched_names']})")
        print(f"      Context  : {s['context'][:120]}...")
        print()

    # ─────────────────────────────────────────────────────────────────
    # STEP 4: Per-source breakdown
    # ─────────────────────────────────────────────────────────────────
    print()
    print("  Per-source breakdown:")
    from collections import defaultdict
    by_source = defaultdict(lambda: {"total":0,"na":0,"gains":0})
    for r in results:
        src = r.get("source","?")
        by_source[src]["total"] += 1
        if not r["existing"]:
            by_source[src]["na"] += 1
        if r["new_from_map"]:
            by_source[src]["gains"] += 1

    for src, counts in sorted(by_source.items()):
        t = counts["total"]
        n = counts["na"]
        g = counts["gains"]
        print(f"    {src:<30}: total={t:3d}  N/A={n:3d}  would_gain={g:3d}")

    # ─────────────────────────────────────────────────────────────────
    # STEP 5: Save JSON
    # ─────────────────────────────────────────────────────────────────
    output = {
        "probe":            "probe_ticker_mapping.py",
        "timestamp_sgt":    ts,
        "total_articles":   total,
        "currently_na":     currently_na,
        "would_gain":       would_gain,
        "na_reduction_pct": na_reduction_pct,
        "target_met":       target_met,
        "sample_matches":   sample_matches,
        "all_results":      results,
    }
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    size_kb = os.path.getsize(OUTPUT_PATH) / 1024
    print()
    print(f"  ✅ Saved: {OUTPUT_PATH}  ({size_kb:.1f} KB)")
    print()
    print("=" * 65)
    print("  NEXT STEP:")
    print("  Review sample_matches above for false positives.")
    print("  If matches look correct, MID Engineering will transplant")
    print("  COMPANY_TICKER_MAP into fetch_tech_publications.py")
    print("  _extract_tickers() as Tier 4.")
    print("=" * 65)
    print()

    return output


if __name__ == "__main__":
    run_probe()
