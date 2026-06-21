from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from llm_clients.config_loader import env_required, load_dotenv, load_yaml_from_env, project_root, resolve_project_path


def load_pipeline_config() -> Dict[str, Any]:
    load_dotenv()
    return load_yaml_from_env("V3_PIPELINE_CONFIG_PATH")


def run_pipeline_once(dry_run: bool = False) -> Dict[str, Any]:
    config = load_pipeline_config()
    pipeline = config.get("pipeline", {})
    steps = config.get("steps", [])
    root = project_root()
    python_exe = python_command(root)
    continue_on_error = pipeline.get("continue_on_step_error") is True
    started = sgt_now()
    results: List[Dict[str, Any]] = []
    print_banner(f"{pipeline.get('display_name', 'V3 Pipeline')} started: {started}")
    for index, step in enumerate(steps, start=1):
        result = run_step(root, python_exe, step, index, pipeline, dry_run=dry_run)
        results.append(result)
        if not result.get("accepted") and not continue_on_error:
            break
    completed = sgt_now()
    failures = [item for item in results if not item.get("accepted")]
    summary = {
        "ok": not failures,
        "started_at_sgt": started,
        "completed_at_sgt": completed,
        "steps": len(results),
        "failures": failures,
        "dry_run": dry_run,
    }
    print_banner(f"{pipeline.get('display_name', 'V3 Pipeline')} completed: {completed}")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary


def run_step(
    root: Path,
    python_exe: str,
    step: Dict[str, Any],
    index: int,
    pipeline: Dict[str, Any],
    dry_run: bool = False,
) -> Dict[str, Any]:
    working_dir = resolve_project_path(str(step.get("working_dir", ".")), root)
    args = [str(item) for item in step.get("args", [])] if isinstance(step.get("args", []), list) else []
    if step.get("module"):
        command = [python_exe, "-m", str(step["module"]), *args]
        label = str(step["module"])
    else:
        script = working_dir / str(step["script"])
        command = [python_exe, str(script), *args]
        label = str(step["script"])
    timeout_seconds = int(step.get("timeout_seconds", pipeline.get("default_step_timeout_seconds", 300)))
    allowed_returncodes = step.get("allowed_returncodes", [0])
    if not isinstance(allowed_returncodes, list):
        allowed_returncodes = [0]
    allowed_returncodes = [int(code) for code in allowed_returncodes]
    print(flush=True)
    print(f"[V3 RUN {index}] {label} {' '.join(args)}", flush=True)
    if dry_run:
        print(f"[V3 DRY RUN] cwd={working_dir}", flush=True)
        return {"step": label, "returncode": 0, "accepted": True, "dry_run": True}
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUNBUFFERED", "1")
    env["BLUELOTUS_PROJECT_ROOT"] = str(root)
    try:
        completed = subprocess.run(
            command,
            cwd=str(working_dir),
            env=env,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        print(f"[V3 TIMEOUT] {label} exceeded {timeout_seconds}s", flush=True)
        return {
            "step": label,
            "returncode": 124,
            "accepted": False,
            "dry_run": False,
            "timeout_seconds": timeout_seconds,
        }
    accepted = completed.returncode in allowed_returncodes
    if completed.returncode != 0 and accepted:
        print(f"[V3 ACCEPTED] {label} returned configured verdict code {completed.returncode}", flush=True)
    elif completed.returncode != 0:
        print(f"[V3 ERROR] {label} returned exit code {completed.returncode}", flush=True)
    return {
        "step": label,
        "returncode": completed.returncode,
        "accepted": accepted,
        "dry_run": False,
        "timeout_seconds": timeout_seconds,
    }


def python_command(root: Path) -> str:
    candidate = root / ".venv" / "Scripts" / "python.exe"
    return str(candidate) if candidate.exists() else sys.executable


def run_loop(dry_run: bool = False) -> int:
    config = load_pipeline_config()
    pipeline = config.get("pipeline", {})
    wait_seconds = int(pipeline.get("wait_seconds", 0))
    wait_minutes = int(pipeline.get("wait_minutes", 0))
    while True:
        run_pipeline_once(dry_run=dry_run)
        if dry_run:
            return 0
        print(f"Waiting {wait_minutes} minutes before next V3 intelligence pipeline run...")
        time.sleep(wait_seconds)


def print_banner(text: str) -> None:
    print(flush=True)
    print("=" * 60, flush=True)
    print(text, flush=True)
    print("=" * 60, flush=True)


def sgt_now() -> str:
    return datetime.now(ZoneInfo("Asia/Singapore")).isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.once:
        result = run_pipeline_once(dry_run=args.dry_run)
        return 0 if result.get("ok") else 1
    return run_loop(dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
