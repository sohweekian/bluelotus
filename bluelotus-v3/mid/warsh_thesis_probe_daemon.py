#!/usr/bin/env python3
"""
warsh_thesis_probe_daemon.py — BlueLotus Hawkish Warsh Thesis Probe v1.0
=========================================================================
Independent 10-minute probe.  No MySQL.  No pipeline dependency.

  • Calls build_warsh_thesis() from warsh_thesis_engine.py
  • Pushes data/warsh_thesis_live.json to GitHub Pages every 10 min

Run:
    python mid/warsh_thesis_probe_daemon.py

Stop:
    Ctrl-C
"""

from __future__ import annotations

import base64
import json
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

# ── Paths & env ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GITHUB_TOKEN    = os.getenv("GITHUB_TOKEN", "")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "sohweekian")
GITHUB_REPO     = os.getenv("GITHUB_PAGES_REPO", "bluelotus")
GITHUB_BRANCH   = os.getenv("GITHUB_BRANCH", "main")

WARSH_JSON_PATH = "data/warsh_thesis_live.json"

# ── Constants ────────────────────────────────────────────────────────────────
PROBE_SEC = 600   # 10 min

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(BASE_DIR / "logs" / "warsh_thesis.log", encoding="utf-8"),
    ],
)
log = logging.getLogger("warsh_probe")


# ── Engine import ─────────────────────────────────────────────────────────────

def _import_engine():
    """Import build_warsh_thesis from warsh_thesis_engine (same directory)."""
    import importlib.util
    engine_path = Path(__file__).parent / "warsh_thesis_engine.py"
    spec = importlib.util.spec_from_file_location("warsh_thesis_engine", engine_path)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.build_warsh_thesis


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _utc_to_sgt(dt_utc: datetime) -> str:
    return (dt_utc + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M")


# ── GitHub push ───────────────────────────────────────────────────────────────

def _gh_headers() -> Dict[str, str]:
    return {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }


def push_to_github(json_str: str) -> bool:
    if not GITHUB_TOKEN:
        log.warning("GITHUB_TOKEN not set — skipping push")
        return False
    api_url = (
        f"https://api.github.com/repos/{GITHUB_USERNAME}/{GITHUB_REPO}"
        f"/contents/{WARSH_JSON_PATH}"
    )
    sha: Optional[str] = None
    try:
        r = requests.get(api_url, headers=_gh_headers(),
                         params={"ref": GITHUB_BRANCH}, timeout=15)
        if r.status_code == 200:
            sha = r.json().get("sha")
    except Exception:
        pass
    payload: Dict[str, Any] = {
        "message": f"warsh probe {datetime.now().strftime('%H:%M')}",
        "content": base64.b64encode(json_str.encode("utf-8")).decode("ascii"),
        "branch":  GITHUB_BRANCH,
    }
    if sha:
        payload["sha"] = sha
    try:
        r = requests.put(api_url, headers=_gh_headers(), json=payload, timeout=30)
        ok = r.status_code in {200, 201}
        log.info("GitHub push: %s (%d)", "OK" if ok else "FAIL", r.status_code)
        if not ok:
            log.warning("GitHub push body: %s", r.text[:200])
        return ok
    except Exception as exc:
        log.warning("GitHub push error: %s", exc)
        return False


# ── Probe cycle ───────────────────────────────────────────────────────────────

def run_probe(build_warsh_thesis) -> None:
    """One full Warsh thesis probe cycle."""
    now_utc = _utcnow()
    now_sgt = _utc_to_sgt(now_utc)

    log.info("Running Warsh thesis engine…")
    result = build_warsh_thesis()

    # Stamp generated_at in SGT for display consistency
    result["generated_at"] = now_sgt + " SGT"

    # Write local copy
    _OUTPUT_DIR = BASE_DIR / "data" / "warsh_thesis"
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    local_path = _OUTPUT_DIR / "warsh_thesis_live.json"
    local_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    log.info("Local: %s", local_path)

    # Push to GitHub Pages
    json_str = json.dumps(result, ensure_ascii=False, default=str)
    push_to_github(json_str)

    # Summary log
    log.info(
        "Warsh thesis: status=%s score=%s/100 fed_tone=%s cio_action=%s",
        result.get("status", "?"),
        result.get("score", "?"),
        (result.get("fed_tone") or {}).get("status", "?"),
        result.get("cio_action", "?"),
    )


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    (BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)

    # Import engine once at startup
    try:
        build_warsh_thesis = _import_engine()
    except Exception as exc:
        log.error("Failed to import warsh_thesis_engine: %s", exc)
        sys.exit(1)

    log.info("=" * 60)
    log.info("BlueLotus Hawkish Warsh Thesis Probe v1.0  [starting]")
    log.info("  Probe interval  : %d min", PROBE_SEC // 60)
    log.info("  Output path     : %s", WARSH_JSON_PATH)
    log.info("  GitHub repo     : %s/%s (branch: %s)",
             GITHUB_USERNAME, GITHUB_REPO, GITHUB_BRANCH)
    log.info("=" * 60)

    cycle = 0
    while True:
        cycle += 1
        log.info("── Cycle %d  %s ───────────────────────────────────────",
                 cycle, datetime.now().strftime("%H:%M:%S"))
        try:
            build_warsh_thesis = _import_engine()
            run_probe(build_warsh_thesis)
        except Exception as exc:
            log.error("Cycle %d crashed: %s", cycle, exc, exc_info=True)
        log.info("Cycle %d done — sleeping %d min\n", cycle, PROBE_SEC // 60)
        time.sleep(PROBE_SEC)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Stopped by user (Ctrl-C).")
        sys.exit(0)
