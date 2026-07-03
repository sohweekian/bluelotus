#!/usr/bin/env python3
"""
run_all_thesis_widgets.py — BlueLotus V3 Thesis Widget Orchestrator
=====================================================================
Launches all enabled thesis widgets as independent subprocesses.
Each widget runs in its own process — modular, isolated, independently restartable.

NO HARDCODING DOCTRINE:
  Widget registry is driven by WIDGET_REGISTRY below and config YAML files.
  To add a new widget: add it to WIDGET_REGISTRY only.

Usage:
    python thesis_widgets\\run_all_thesis_widgets.py          # start all
    python thesis_widgets\\run_all_thesis_widgets.py --list   # list registered widgets
    python thesis_widgets\\run_all_thesis_widgets.py --once   # run one cycle each, no daemons
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON   = str(BASE_DIR.parent / "bluelotus2" / ".venv" / "Scripts" / "python.exe")

# ── Widget Registry ───────────────────────────────────────────────────────────
# To register a new widget: add an entry here (id, script path, enabled flag).
# Never hardcode anything else — script logic and config live in the widget's
# own files.

WIDGET_REGISTRY = [
    {
        "id":      "AI_INFRASTRUCTURE_POWER_THESIS",
        "label":   "AI Infrastructure / Power Bottleneck",
        "script":  "thesis_widgets/ai_infrastructure_power.py",
        "enabled": True,
    },
    {
        "id":      "GLOBAL_LEVERAGE_UNWIND_THESIS",
        "label":   "Global Leverage Unwind",
        "script":  "thesis_widgets/global_leverage_unwind.py",
        "enabled": True,
    },
    # Future widgets registered here:
    # {"id": "GOLD_SAFE_HAVEN_THESIS",    "script": "thesis_widgets/gold_safe_haven.py",    "enabled": False},
    # {"id": "WARSH_FED_THESIS",          "script": "thesis_widgets/warsh_fed.py",           "enabled": False},
    # {"id": "BOJ_CARRY_THESIS",          "script": "thesis_widgets/boj_carry.py",           "enabled": False},
    # {"id": "PETRO_DOLLAR_THESIS",       "script": "thesis_widgets/petro_dollar.py",        "enabled": False},
    # {"id": "STICKY_INFLATION_THESIS",   "script": "thesis_widgets/sticky_inflation.py",    "enabled": False},
]


def list_widgets() -> None:
    print(f"\nBlueLotus V3 — Thesis Widget Registry ({len(WIDGET_REGISTRY)} registered)\n")
    for w in WIDGET_REGISTRY:
        status = "ENABLED " if w["enabled"] else "DISABLED"
        print(f"  [{status}]  {w['id']:<45}  {w['script']}")
    print()


def run_all(once: bool = False) -> None:
    enabled = [w for w in WIDGET_REGISTRY if w["enabled"]]
    if not enabled:
        print("No enabled widgets in registry. Edit run_all_thesis_widgets.py.")
        sys.exit(0)

    print(f"\nStarting {len(enabled)} thesis widget(s)...\n")

    procs = []
    for w in enabled:
        script_path = BASE_DIR / w["script"]
        if not script_path.exists():
            print(f"  [SKIP] {w['id']} — script not found: {script_path}")
            continue

        cmd = [PYTHON, str(script_path)]
        if once:
            cmd.append("--once")

        proc = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )
        procs.append((w["id"], proc))
        print(f"  [STARTED]  {w['id']}  PID={proc.pid}")

    if once:
        print("\nWaiting for single-cycle runs to complete...")
        for widget_id, proc in procs:
            proc.wait()
            rc = proc.returncode
            status = "OK" if rc == 0 else f"FAILED (rc={rc})"
            print(f"  {widget_id}: {status}")
    else:
        print(f"\nAll {len(procs)} widget(s) running as daemons.")
        print("Each widget logs to C:\\bluelotus3\\logs\\<widget_name>.log")
        print("Press Ctrl-C to exit this monitor (daemons continue running).\n")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            print("\nMonitor exited. Daemon processes continue running independently.")


def main() -> None:
    parser = argparse.ArgumentParser(description="BlueLotus V3 Thesis Widget Runner")
    parser.add_argument("--list", action="store_true", help="List registered widgets")
    parser.add_argument("--once", action="store_true",
                        help="Run one cycle per widget then exit")
    args = parser.parse_args()

    if args.list:
        list_widgets()
        return

    run_all(once=args.once)


if __name__ == "__main__":
    main()
