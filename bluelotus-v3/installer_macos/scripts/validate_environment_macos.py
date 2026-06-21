#!/usr/bin/env python3
"""
BlueLotus V2 macOS deployment validator.

Checks Python imports, MySQL connectivity, schema coverage, shell runner safety,
macOS path patching, and optional Moomoo OpenD quote connectivity. It does not
call trade unlock, place_order, modify_order, or cancel APIs.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


REQUIRED_IMPORTS = [
    ("mysql.connector", "mysql-connector-python"),
    ("dotenv", "python-dotenv"),
    ("requests", "requests"),
    ("feedparser", "feedparser"),
    ("bs4", "beautifulsoup4"),
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("moomoo", "moomoo-api"),
    ("docx", "python-docx"),
]


def log(status: str, message: str) -> None:
    print(f"[{status}] {message}")


def check_imports() -> list[str]:
    failures: list[str] = []
    for module, package in REQUIRED_IMPORTS:
        try:
            __import__(module)
            log("OK", f"Import {module} ({package})")
        except Exception as exc:
            failures.append(f"Missing import {module}: {exc}")
            log("FAIL", f"Import {module} ({package}) failed: {exc}")
    return failures


def check_files(root: Path) -> list[str]:
    failures: list[str] = []
    required = [
        root / ".env",
        root / "core" / "db.py",
        root / "mid" / "ingest.py",
        root / "mid" / "export_dataset_raw.py",
        root / "mid" / "fetch_portfolio_readonly.py",
        root / "research" / "research_report_generator.py",
        root / "run_bluelotus_v2_once_macos.sh",
        root / "run_bluelotus_v2_hourly_macos.sh",
    ]
    for path in required:
        if path.exists():
            log("OK", f"Required file present: {path}")
        else:
            failures.append(f"Required file missing: {path}")
            log("FAIL", f"Required file missing: {path}")
    return failures


def check_env() -> list[str]:
    failures: list[str] = []
    required = ["MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"]
    for key in required:
        value = os.getenv(key)
        if value and value != "CHANGE_ME":
            log("OK", f"Env key present: {key}")
        else:
            failures.append(f"Env key missing or placeholder: {key}")
            log("FAIL", f"Env key missing or placeholder: {key}")
    for key in ["BLUELOTUS_ROOT", "MOOMOO_OPEND_HOST", "MOOMOO_OPEND_PORT"]:
        if os.getenv(key):
            log("OK", f"Env key present: {key}")
        else:
            log("WARN", f"Env key missing; default will be used: {key}")
    return failures


def check_mysql() -> list[str]:
    failures: list[str] = []
    import mysql.connector

    host = os.getenv("MYSQL_HOST") or os.getenv("DB_HOST") or "127.0.0.1"
    port = int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306")
    database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME") or "bluelotus2"
    user = os.getenv("MYSQL_USER") or os.getenv("DB_USER") or ""
    password = os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD") or ""

    try:
        conn = mysql.connector.connect(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            charset="utf8mb4",
        )
        cur = conn.cursor()
        cur.execute("SELECT VERSION(), @@version_comment, @@version_compile_os")
        version, comment, compile_os = cur.fetchone()
        log("OK", f"MySQL connected: {version} | {comment} | {compile_os}")
        if str(version) != "8.4.9":
            log("WARN", f"Expected MySQL 8.4.9; detected {version}")
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s", (database,))
        table_count = int(cur.fetchone()[0])
        if table_count >= 44:
            log("OK", f"Schema table count: {table_count}")
        else:
            failures.append(f"Only {table_count} tables found; expected at least 44")
            log("FAIL", f"Schema table count: {table_count}; expected at least 44")
        cur.execute("SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=%s", (database,))
        trigger_count = int(cur.fetchone()[0])
        if trigger_count >= 2:
            log("OK", f"Raw archive immutability triggers present: {trigger_count}")
        else:
            log("WARN", f"Only {trigger_count} triggers found; expected 2")
        cur.close()
        conn.close()
    except Exception as exc:
        failures.append(f"MySQL connection/schema check failed: {exc}")
        log("FAIL", f"MySQL check failed: {exc}")
    return failures


def check_runner(root: Path) -> list[str]:
    failures: list[str] = []
    runner = root / "run_bluelotus_v2_once_macos.sh"
    hourly = root / "run_bluelotus_v2_hourly_macos.sh"
    for path in (runner, hourly):
        if not path.exists():
            failures.append(f"Runner missing: {path}")
            log("FAIL", f"Runner missing: {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        forbidden = ["place_order", "setup_working_orders", "cancel_order", "unlock_trade", "modify_order", "moomoo_trader.py"]
        found = [term for term in forbidden if term in text]
        if found:
            failures.append(f"Runner contains forbidden execution terms: {found}")
            log("FAIL", f"Runner contains forbidden execution terms: {found}")
        else:
            log("OK", f"Runner safety scan: {path.name}")
    return failures


def check_path_patch(root: Path) -> list[str]:
    failures: list[str] = []
    active_files = list((root / "mid").glob("*.py")) + list((root / "research").glob("*.py"))
    offenders = []
    for path in active_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "Path(r\"C:\\bluelotus2" in text or "Path(r'C:\\bluelotus2" in text:
            offenders.append(str(path))
    if offenders:
        failures.append(f"Unpatched Windows root references: {offenders[:5]}")
        log("FAIL", f"Unpatched Windows root references: {len(offenders)}")
    else:
        log("OK", "macOS payload path patch present")
    return failures


def check_moomoo() -> list[str]:
    failures: list[str] = []
    try:
        import moomoo as ft
        import moomoo.common.ft_logger as ft_logger

        ft_logger.logger.enable_console_log(False)
        host = os.getenv("MOOMOO_OPEND_HOST") or os.getenv("MOOMOO_HOST") or "127.0.0.1"
        port = int(os.getenv("MOOMOO_OPEND_PORT") or os.getenv("MOOMOO_PORT") or "11111")
        ctx = ft.OpenQuoteContext(host=host, port=port)
        try:
            ret, data = ctx.get_market_snapshot(["US.SPY"])
        finally:
            ctx.close()
        if ret == ft.RET_OK:
            log("OK", f"Moomoo OpenD quote check passed at {host}:{port}")
        else:
            failures.append(f"Moomoo OpenD returned error: {data}")
            log("FAIL", f"Moomoo OpenD returned error: {data}")
    except Exception as exc:
        failures.append(f"Moomoo OpenD check failed: {exc}")
        log("FAIL", f"Moomoo OpenD check failed: {exc}")
    return failures


def main() -> int:
    default_root = Path.home() / "bluelotus2"
    ap = argparse.ArgumentParser(description="Validate BlueLotus V2 macOS deployment.")
    ap.add_argument("--root", default=str(default_root))
    ap.add_argument("--check-moomoo", action="store_true", help="Require Moomoo OpenD quote connectivity.")
    args = ap.parse_args()

    root = Path(args.root).expanduser()
    load_dotenv(root / ".env")

    print("BlueLotus V2 macOS Deployment Validator")
    print(f"Root: {root}")
    print(f"Python: {sys.version.split()[0]}")
    if sys.version_info < (3, 12):
        log("WARN", "Recommended Python is 3.12.x or newer")
    else:
        log("OK", "Python version meets macOS collector baseline")

    failures: list[str] = []
    failures.extend(check_files(root))
    failures.extend(check_env())
    failures.extend(check_imports())
    failures.extend(check_mysql())
    failures.extend(check_runner(root))
    failures.extend(check_path_patch(root))
    if args.check_moomoo:
        failures.extend(check_moomoo())
    else:
        log("WARN", "Moomoo OpenD live check skipped. Run with --check-moomoo after OpenD is running.")

    if failures:
        print("\nValidation result: FAIL")
        for item in failures:
            print(f" - {item}")
        return 1
    print("\nValidation result: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
