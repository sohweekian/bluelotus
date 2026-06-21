#!/usr/bin/env python3
"""
BlueLotus V2 Python runtime guard.

Observational by default:
- checks the active Python executable
- checks required package imports
- checks whether the production virtual environment exists
- writes a JSON audit artifact

Use --require-venv when the caller wants missing .venv to become a FAIL.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_IMPORTS = [
    ("anthropic", "anthropic"),
    ("bs4", "beautifulsoup4"),
    ("dateutil", "python-dateutil"),
    ("docx", "python-docx"),
    ("dotenv", "python-dotenv"),
    ("feedparser", "feedparser"),
    ("lxml", "lxml"),
    ("matplotlib", "matplotlib"),
    ("moomoo", "moomoo-api"),
    ("mysql.connector", "mysql-connector-python"),
    ("numpy", "numpy"),
    ("openai", "openai"),
    ("pandas", "pandas"),
    ("PIL", "pillow"),
    ("requests", "requests"),
    ("rich", "rich"),
    ("schedule", "schedule"),
    ("seaborn", "seaborn"),
    ("simplejson", "simplejson"),
    ("tqdm", "tqdm"),
    ("vaderSentiment", "vaderSentiment"),
    ("yaml", "PyYAML"),
]


@dataclass
class Finding:
    status: str
    check: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


class Guard:
    def __init__(self, root: Path, verbose: bool = True) -> None:
        self.root = root
        self.verbose = verbose
        self.findings: list[Finding] = []

    def add(self, status: str, check: str, message: str, **detail: Any) -> None:
        self.findings.append(Finding(status=status, check=check, message=message, detail=detail))
        if self.verbose:
            print(f"[{status}] {check}: {message}")

    def ok(self, check: str, message: str, **detail: Any) -> None:
        self.add("PASS", check, message, **detail)

    def warn(self, check: str, message: str, **detail: Any) -> None:
        self.add("WARN", check, message, **detail)

    def fail(self, check: str, message: str, **detail: Any) -> None:
        self.add("FAIL", check, message, **detail)

    def counts(self) -> dict[str, int]:
        out = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for finding in self.findings:
            out[finding.status] = out.get(finding.status, 0) + 1
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "root": str(self.root),
            "python_executable": sys.executable,
            "python_version": sys.version,
            "counts": self.counts(),
            "findings": [
                {
                    "status": f.status,
                    "check": f.check,
                    "message": f.message,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
        }


def module_version(module: Any) -> str:
    for attr in ("__version__", "VERSION", "version"):
        value = getattr(module, attr, None)
        if value:
            return str(value)
    return "unknown"


def check_runtime(guard: Guard, require_venv: bool) -> None:
    version = sys.version_info
    if version.major == 3 and version.minor >= 13:
        guard.ok("python", f"Python runtime {sys.version.split()[0]}", executable=sys.executable)
    else:
        guard.fail("python", f"Python 3.13+ required; detected {sys.version.split()[0]}", executable=sys.executable)

    expected_venv = guard.root / ".venv" / "Scripts" / "python.exe"
    in_expected_venv = Path(sys.executable).resolve() == expected_venv.resolve() if expected_venv.exists() else False
    if expected_venv.exists() and in_expected_venv:
        guard.ok("venv", "Running from production virtual environment", path=str(expected_venv))
    elif expected_venv.exists():
        guard.warn("venv", "Production virtual environment exists but current process is using another Python", expected=str(expected_venv), actual=sys.executable)
    elif require_venv:
        guard.fail("venv", "Production virtual environment is missing", expected=str(expected_venv))
    else:
        guard.warn("venv", "Production virtual environment is missing; runners will fall back to system python", expected=str(expected_venv))

    windows_apps = "windowsapps" in sys.executable.lower()
    if windows_apps:
        guard.warn("python", "Active Python is a WindowsApps shim/store runtime", executable=sys.executable)
    else:
        guard.ok("python", "Active Python path is explicit", executable=sys.executable)


def check_imports(guard: Guard) -> None:
    failures: list[dict[str, str]] = []
    for module_name, package_name in REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(module_name)
            guard.ok("imports", f"{module_name} import OK", package=package_name, version=module_version(module))
        except Exception as exc:
            failures.append({"module": module_name, "package": package_name, "error": str(exc)})
    if failures:
        guard.fail("imports", "Required imports failed", failures=failures)


def write_report(report: dict[str, Any], output: Path | None, archive: bool, label: str) -> None:
    if not output:
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[PASS] output: Wrote runtime guard JSON: {output}")
    if archive:
        safe_label = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (label or "runtime"))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = output.parent / "runtime_guard_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"runtime_guard_{safe_label}_{stamp}.json"
        archive_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"[PASS] output: Archived runtime guard JSON: {archive_path}")


def run_guard(root: Path, require_venv: bool, verbose: bool = True) -> dict[str, Any]:
    guard = Guard(root, verbose=verbose)
    check_runtime(guard, require_venv=require_venv)
    check_imports(guard)
    return guard.to_json()


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate BlueLotus V2 Python runtime.")
    ap.add_argument("--root", default=r"C:\bluelotus3", help="BlueLotus root directory.")
    ap.add_argument("--require-venv", action="store_true", help="Fail if C:\\bluelotus2\\.venv is missing or not active.")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as non-zero exit.")
    ap.add_argument("--json-output", default="", help="Optional JSON output path.")
    ap.add_argument("--no-json-output", action="store_true", help="Do not write latest JSON output artifact.")
    ap.add_argument("--archive", action="store_true", help="Archive a timestamped runtime report.")
    ap.add_argument("--label", default="runtime", help="Archive label.")
    args = ap.parse_args()

    root = Path(args.root)
    print("BlueLotus V2 Runtime Guard")
    print(f"Root: {root}")
    print(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    print()

    report = run_guard(root, require_venv=args.require_venv)
    counts = report.get("counts", {})
    print()
    print(f"Summary: PASS {counts.get('PASS', 0)} | WARN {counts.get('WARN', 0)} | FAIL {counts.get('FAIL', 0)}")

    output = None
    if not args.no_json_output:
        output = Path(args.json_output) if args.json_output else root / "data" / "audit" / "runtime_guard_latest.json"
    write_report(report, output, archive=args.archive, label=args.label)

    if counts.get("FAIL", 0):
        return 1
    if args.strict and counts.get("WARN", 0):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

