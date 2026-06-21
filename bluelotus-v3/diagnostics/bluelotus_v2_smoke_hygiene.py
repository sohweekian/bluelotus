#!/usr/bin/env python3
"""
BlueLotus V2 smoke and hygiene diagnostics.

This script is intentionally observational:
- no pipeline execution
- no broker order calls
- no database writes
- no trade unlock, place, modify, or cancel calls

It validates the Windows V2 production tree, MySQL schema, key artifacts,
installer privacy, and read-only broker doctrine.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import json
import os
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


REQUIRED_FILES = [
    "core/db.py",
    "core/db_writers.py",
    "mid/ingest.py",
    "mid/export_dataset_raw.py",
    "mid/fetch_portfolio_readonly.py",
    "mid/fetch_execution_records_readonly.py",
    "mid/fetch_cross_market_confirmation.py",
    "mid/historical_risk_model.py",
    "mid/institutional_quant_pipeline.py",
    "research/research_report_generator.py",
    "research/bluelotus_superforecast_engine.py",
    "diagnostics/bluelotus_runtime_guard.py",
    "diagnostics/Repair-BlueLotusV2Runtime.ps1",
    "diagnostics/dataset_contract_v2.py",
    "run_bluelotus_v2_pipeline_simple_hourly_no_research_agent.bat",
    "run_bluelotus_v2_runtime_guard.bat",
    "repair_bluelotus_v2_runtime.bat",
    "run_bluelotus_v2_dataset_contract.bat",
]

REQUIRED_DIRS = [
    "core",
    "mid",
    "research",
    "data/frontend",
    "data/audit",
    "data/risk",
    "data/portfolio",
    "installer",
    "documentation",
]

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

REQUIRED_ENV_KEYS = [
    "MYSQL_HOST",
    "MYSQL_PORT",
    "MYSQL_DATABASE",
    "MYSQL_USER",
    "MYSQL_PASSWORD",
]

OPTIONAL_ENV_KEYS = [
    "FINNHUB_API_KEY",
    "FRED_API_KEY",
    "EIA_API_KEY",
    "BEA_API_KEY",
    "BLS_API_KEY",
    "ANTHROPIC_API_KEY",
    "XAI_API_KEY",
]

REQUIRED_DB_TABLES = [
    "raw_signal_archive",
    "extraction_audit_log",
    "portfolio_readonly_snapshots",
    "portfolio_readonly_positions",
    "historical_prices",
    "risk_model_runs",
    "portfolio_optimizer_runs",
    "cio_decision_journal",
    "cio_cognition_journal",
    "cio_thesis_reviews",
    "execution_readonly_snapshots",
    "execution_readonly_orders",
    "execution_readonly_deals",
    "execution_readonly_fees",
    "thesis_lifecycle",
    "monitoring_alerts",
    "data_lineage_events",
    "institutional_dataset_snapshots",
    "institutional_quant_runs",
    "institutional_quant_process_results",
    "ticker_forecasts",
    "forecast_resolutions",
    "research_report_archive",
]

REQUIRED_DATASET_BLOCKS = [
    "meta",
    "source_health",
    "regime",
    "portfolio",
    "live_prices",
    "analyst_targets",
    "fundamentals",
    "capital_flow",
    "treasury_yields",
    "cross_market_confirmation",
    "security_master",
    "data_quality_sla",
    "portfolio_readonly",
    "historical_price_coverage",
    "risk_model",
    "portfolio_targets",
    "thesis_lifecycle",
    "monitoring",
    "audit",
    "dataset_snapshot_archive",
    "freshness_recovery",
    "historical_backfill",
    "cio_decisions",
    "cio_cognition",
    "orders",
    "fills",
    "execution",
    "trade_lifecycle",
    "transaction_cost_analysis",
    "corporate_actions",
    "institutional_quant",
    "research_forecasting",
    "signals",
    "signals_latest",
]

REPORT_MARKERS = [
    "EXECUTIVE SUMMARY",
    "DATASET INTEGRITY",
    "INSTITUTIONAL QUANT",
    "SUPERFORECAST",
    "CROSS-MARKET CONFIRMATION",
    "FORMAL RISK MODEL",
    "CIO COGNITION LEDGER",
]

FORBIDDEN_CALL_NAMES = {
    "unlock_trade",
    "place_order",
    "modify_order",
    "cancel_order",
    "cancel_all_order",
    "change_order",
    "setup_working_orders",
}

BAD_ZIP_PATTERNS = [
    ".pyc",
    "__pycache__",
    "moomoo_trader.py",
    "research_report.txt",
    "research_report_archive_latest.json",
    "research_report_delivery_latest.json",
    "research_forecasts.json",
    ".xlsx",
    ".docx",
]


@dataclass
class Finding:
    status: str
    check: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


class Diagnostics:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.findings: list[Finding] = []

    def add(self, status: str, check: str, message: str, **detail: Any) -> None:
        self.findings.append(Finding(status=status, check=check, message=message, detail=detail))
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


def load_dotenv_if_available(root: Path) -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(root / ".env")
    except Exception:
        pass


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    for candidate in (text, text.split(".")[0]):
        try:
            return datetime.fromisoformat(candidate.replace(" ", "T")).replace(tzinfo=None)
        except Exception:
            continue
    return None


def is_active_python(path: Path, root: Path) -> bool:
    rel = path.relative_to(root)
    parts = {p.lower() for p in rel.parts}
    if parts & {"archive", "temp", "build", "dist", "__pycache__", ".venv", "installer", "installer_macos"}:
        return False
    if path.name == "moomoo_trader.py":
        return False
    return path.suffix == ".py"


def iter_active_python(root: Path) -> Iterable[Path]:
    for folder in ("core", "mid", "research", "news"):
        base = root / folder
        if base.exists():
            yield from (p for p in base.rglob("*.py") if is_active_python(p, root))
    extra = root / "moomoo_intelligence.py"
    if extra.exists():
        yield extra


def check_filesystem(diag: Diagnostics) -> None:
    for rel in REQUIRED_DIRS:
        path = diag.root / rel
        if path.is_dir():
            diag.ok("filesystem", f"Directory present: {rel}")
        else:
            diag.fail("filesystem", f"Directory missing: {rel}")
    for rel in REQUIRED_FILES:
        path = diag.root / rel
        if path.is_file():
            diag.ok("filesystem", f"File present: {rel}", size=path.stat().st_size)
        else:
            diag.fail("filesystem", f"File missing: {rel}")


def check_python_imports(diag: Diagnostics) -> None:
    version = sys.version_info
    if version.major == 3 and version.minor >= 13:
        diag.ok("python", f"Python runtime {sys.version.split()[0]}")
    else:
        diag.warn("python", f"Production reference uses Python 3.13.x; detected {sys.version.split()[0]}")
    for module, package in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module)
            diag.ok("imports", f"{module} import OK", package=package)
        except Exception as exc:
            diag.fail("imports", f"{module} import failed", package=package, error=str(exc))


def check_env(diag: Diagnostics) -> None:
    env_path = diag.root / ".env"
    if env_path.exists():
        diag.ok("env", ".env file present", size=env_path.stat().st_size)
    else:
        diag.fail("env", ".env file missing")
    for key in REQUIRED_ENV_KEYS:
        value = os.getenv(key)
        if value and value != "CHANGE_ME":
            diag.ok("env", f"Required key present: {key}")
        else:
            diag.fail("env", f"Required key missing or placeholder: {key}")
    for key in OPTIONAL_ENV_KEYS:
        value = os.getenv(key)
        if value:
            diag.ok("env", f"Optional key present: {key}")
        else:
            diag.warn("env", f"Optional key not set: {key}")
    if os.getenv("MOOMOO_OPEND_HOST") or os.getenv("MOOMOO_HOST"):
        diag.ok("env", "Moomoo host key present", key="MOOMOO_OPEND_HOST/MOOMOO_HOST")
    else:
        diag.warn("env", "Moomoo host key not set; default 127.0.0.1 will be used")
    if os.getenv("MOOMOO_OPEND_PORT") or os.getenv("MOOMOO_PORT"):
        diag.ok("env", "Moomoo port key present", key="MOOMOO_OPEND_PORT/MOOMOO_PORT")
    else:
        diag.warn("env", "Moomoo port key not set; default 11111 will be used")


def check_runtime_guard(diag: Diagnostics) -> None:
    guard_path = diag.root / "diagnostics" / "bluelotus_runtime_guard.py"
    if not guard_path.exists():
        diag.fail("runtime_guard", "Runtime guard missing", path=str(guard_path))
        return
    try:
        spec = importlib.util.spec_from_file_location("bluelotus_runtime_guard", guard_path)
        if not spec or not spec.loader:
            diag.fail("runtime_guard", "Could not load runtime guard", path=str(guard_path))
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        report = module.run_guard(diag.root, require_venv=False, verbose=False)
        output = diag.root / "data" / "audit" / "runtime_guard_latest.json"
        module.write_report(report, output, archive=False, label="smoke")
    except Exception as exc:
        diag.fail("runtime_guard", "Runtime guard failed to run", error=str(exc))
        return

    counts = report.get("counts", {})
    fail_count = int(counts.get("FAIL", 0) or 0)
    warn_count = int(counts.get("WARN", 0) or 0)
    fail_findings = [f for f in report.get("findings", []) if f.get("status") == "FAIL"]
    warn_findings = [f for f in report.get("findings", []) if f.get("status") == "WARN"]
    if fail_count:
        diag.fail("runtime_guard", "Python runtime guard has FAIL findings", counts=counts, failed_findings=fail_findings[:10])
    elif warn_count:
        diag.warn("runtime_guard", "Python runtime guard passed with warnings", counts=counts, warning_findings=warn_findings[:10])
    else:
        diag.ok("runtime_guard", "Python runtime guard passed", counts=counts)


def check_mysql(diag: Diagnostics) -> None:
    try:
        import mysql.connector
    except Exception as exc:
        diag.fail("mysql", "mysql.connector unavailable", error=str(exc))
        return

    cfg = {
        "host": os.getenv("MYSQL_HOST") or os.getenv("DB_HOST") or "127.0.0.1",
        "port": int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306"),
        "database": os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME") or "bluelotus2",
        "user": os.getenv("MYSQL_USER") or os.getenv("DB_USER") or "",
        "password": os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD") or "",
        "charset": "utf8mb4",
    }
    try:
        conn = mysql.connector.connect(**cfg)
    except Exception as exc:
        diag.fail("mysql", "Connection failed", host=cfg["host"], port=cfg["port"], database=cfg["database"], error=str(exc))
        return

    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT VERSION() AS version, @@version_comment AS comment, @@version_compile_os AS compile_os")
        version = cur.fetchone()
        if str(version["version"]) == "8.4.9":
            diag.ok("mysql", "MySQL version matches production reference", **version)
        else:
            diag.warn("mysql", "MySQL version differs from production reference 8.4.9", **version)

        cur.execute(
            "SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE'",
            (cfg["database"],),
        )
        tables = {row["TABLE_NAME"] for row in cur.fetchall()}
        if len(tables) >= 44:
            diag.ok("mysql", f"Schema table count OK: {len(tables)}")
        else:
            diag.fail("mysql", f"Schema table count low: {len(tables)}", expected_min=44)
        missing = sorted(set(REQUIRED_DB_TABLES) - tables)
        if missing:
            diag.fail("mysql", "Required DB tables missing", missing=missing)
        else:
            diag.ok("mysql", "Required DB tables present", count=len(REQUIRED_DB_TABLES))

        cur.execute(
            "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=%s",
            (cfg["database"],),
        )
        triggers = {row["TRIGGER_NAME"] for row in cur.fetchall()}
        required_triggers = {"enforce_raw_immutability", "enforce_raw_no_delete"}
        if required_triggers <= triggers:
            diag.ok("mysql", "Raw archive immutability triggers present", triggers=sorted(required_triggers))
        else:
            diag.fail("mysql", "Raw archive immutability triggers missing", missing=sorted(required_triggers - triggers))

        cur.execute("SELECT COUNT(*) AS cnt, MAX(received_at) AS latest FROM raw_signal_archive")
        raw = cur.fetchone()
        if raw and int(raw["cnt"] or 0) > 0:
            diag.ok("mysql", "raw_signal_archive contains data", rows=int(raw["cnt"]), latest=str(raw["latest"]))
        else:
            diag.warn("mysql", "raw_signal_archive is empty")

        cur.execute("SELECT COUNT(*) AS cnt FROM research_report_archive")
        reports = cur.fetchone()
        if reports and int(reports["cnt"] or 0) > 0:
            diag.ok("mysql", "research_report_archive contains records", rows=int(reports["cnt"]))
        else:
            diag.warn("mysql", "research_report_archive has no records")
        cur.close()
    except Exception as exc:
        diag.fail("mysql", "Metadata query failed", error=str(exc))
    finally:
        conn.close()


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def check_dataset(diag: Diagnostics) -> None:
    path = diag.root / "data" / "frontend" / "dataset_raw.json"
    if not path.exists():
        diag.fail("dataset", "dataset_raw.json missing", path=str(path))
        return
    try:
        dataset = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        diag.fail("dataset", "dataset_raw.json parse failed", error=str(exc))
        return
    diag.ok("dataset", "dataset_raw.json parses", size=path.stat().st_size)

    missing = [key for key in REQUIRED_DATASET_BLOCKS if key not in dataset]
    if missing:
        diag.fail("dataset", "Required dataset blocks missing", missing=missing)
    else:
        diag.ok("dataset", "Required dataset blocks present", count=len(REQUIRED_DATASET_BLOCKS))

    meta = dataset.get("meta") or {}
    generated = meta.get("generated_at") or meta.get("dataset_generated_at") or dataset.get("generated_at")
    generated_dt = parse_datetime(generated)
    if generated_dt:
        age_min = max(0.0, (datetime.now() - generated_dt).total_seconds() / 60.0)
        if age_min <= 180:
            diag.ok("dataset", f"Dataset freshness OK: {age_min:.1f} minutes", generated_at=str(generated))
        else:
            diag.warn("dataset", f"Dataset age is high: {age_min:.1f} minutes", generated_at=str(generated))
    else:
        diag.warn("dataset", "Dataset generated_at timestamp not parsed", generated_at=str(generated))

    live_prices = dataset.get("live_prices") or {}
    if isinstance(live_prices, dict) and len(live_prices) >= 180:
        diag.ok("dataset", "live_prices coverage OK", count=len(live_prices))
    else:
        diag.warn("dataset", "live_prices coverage low", count=len(live_prices) if isinstance(live_prices, dict) else None)

    security_master = dataset.get("security_master") or {}
    unknown_sectors = 0
    if isinstance(security_master, dict):
        for key, row in security_master.items():
            if str(key).startswith("_"):
                continue
            if isinstance(row, dict) and str(row.get("sector", "")).upper() in {"", "UNKNOWN", "N/A"}:
                unknown_sectors += 1
    if unknown_sectors == 0 and security_master:
        diag.ok("dataset", "security_master sector coverage OK", count=len(security_master))
    else:
        diag.warn("dataset", "security_master has unknown sectors", unknown_sectors=unknown_sectors, count=len(security_master))

    cio_decisions = dataset.get("cio_decisions") or {}
    orders_generated = cio_decisions.get("orders_generated")
    if orders_generated in (0, "0", None):
        diag.ok("dataset", "CIO-only execution doctrine preserved in dataset", orders_generated=orders_generated)
    else:
        diag.fail("dataset", "Dataset reports generated orders", orders_generated=orders_generated)


def check_dataset_contract(diag: Diagnostics) -> None:
    contract_path = diag.root / "diagnostics" / "dataset_contract_v2.py"
    dataset_path = diag.root / "data" / "frontend" / "dataset_raw.json"
    if not contract_path.exists():
        diag.fail("dataset_contract", "Dataset contract validator missing", path=str(contract_path))
        return
    try:
        spec = importlib.util.spec_from_file_location("dataset_contract_v2", contract_path)
        if not spec or not spec.loader:
            diag.fail("dataset_contract", "Could not load dataset contract validator", path=str(contract_path))
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        report = module.validate_dataset(dataset_path, verbose=False)
        output = diag.root / "data" / "audit" / "dataset_contract_latest.json"
        module.write_report(report, output, archive=False, label="smoke")
    except Exception as exc:
        diag.fail("dataset_contract", "Dataset contract validator failed to run", error=str(exc))
        return

    counts = report.get("counts", {})
    fail_count = int(counts.get("FAIL", 0) or 0)
    warn_count = int(counts.get("WARN", 0) or 0)
    fail_findings = [f for f in report.get("findings", []) if f.get("status") == "FAIL"]
    warn_findings = [f for f in report.get("findings", []) if f.get("status") == "WARN"]
    if fail_count:
        diag.fail(
            "dataset_contract",
            "dataset_raw.json contract has FAIL findings",
            counts=counts,
            failed_findings=fail_findings[:10],
        )
    elif warn_count:
        diag.warn(
            "dataset_contract",
            "dataset_raw.json contract passed with warnings",
            counts=counts,
            warning_findings=warn_findings[:10],
        )
    else:
        diag.ok("dataset_contract", "dataset_raw.json contract passed", counts=counts)


def check_reports(diag: Diagnostics) -> None:
    report = diag.root / "research" / "research_report.txt"
    if not report.exists():
        diag.fail("reports", "research_report.txt missing")
    else:
        text = report.read_text(encoding="utf-8", errors="ignore")
        if len(text) > 10_000:
            diag.ok("reports", "research_report.txt size OK", size=len(text))
        else:
            diag.warn("reports", "research_report.txt is small", size=len(text))
        missing_markers = [m for m in REPORT_MARKERS if m not in text]
        if missing_markers:
            diag.warn("reports", "Report section markers missing", missing=missing_markers)
        else:
            diag.ok("reports", "Report section markers present", count=len(REPORT_MARKERS))

    for rel, min_size in [
        ("research/BlueLotus_V2_R6_CIO_Operating_Report.xlsx", 10_000),
        ("research/BlueLotus_V2_R6_CIO_Word_Report.docx", 5_000),
        ("research/research_report_delivery_latest.json", 500),
        ("research/research_report_archive_latest.json", 500),
    ]:
        path = diag.root / rel
        if not path.exists():
            diag.warn("reports", f"Artifact missing: {rel}")
        elif path.stat().st_size >= min_size:
            diag.ok("reports", f"Artifact size OK: {rel}", size=path.stat().st_size)
        else:
            diag.warn("reports", f"Artifact is small: {rel}", size=path.stat().st_size)


def check_source_syntax_and_safety(diag: Diagnostics) -> None:
    syntax_errors: list[dict[str, Any]] = []
    forbidden_calls: list[dict[str, Any]] = []
    files = list(iter_active_python(diag.root))
    for path in files:
        rel = str(path.relative_to(diag.root))
        try:
            source = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(source, filename=str(path))
        except Exception as exc:
            syntax_errors.append({"file": rel, "error": str(exc)})
            continue
        for node in ast.walk(tree):
            call_name = None
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    call_name = node.func.attr
                elif isinstance(node.func, ast.Name):
                    call_name = node.func.id
            if call_name in FORBIDDEN_CALL_NAMES:
                forbidden_calls.append({"file": rel, "call": call_name, "line": getattr(node, "lineno", None)})
    if syntax_errors:
        diag.fail("source", "Active Python syntax errors found", errors=syntax_errors[:10], count=len(syntax_errors))
    else:
        diag.ok("source", "Active Python files parse successfully", count=len(files))
    if forbidden_calls:
        diag.fail("broker_safety", "Forbidden broker execution calls found in active code", calls=forbidden_calls[:20], count=len(forbidden_calls))
    else:
        diag.ok("broker_safety", "No forbidden broker execution calls in active code", scanned_files=len(files))

    runner = diag.root / "run_bluelotus_v2_pipeline_simple_hourly_no_research_agent.bat"
    if runner.exists():
        text = runner.read_text(encoding="utf-8", errors="ignore").lower()
        forbidden_in_runner = [name for name in FORBIDDEN_CALL_NAMES | {"moomoo_trader.py"} if name.lower() in text]
        if forbidden_in_runner:
            diag.fail("broker_safety", "Forbidden terms found in production runner", terms=forbidden_in_runner)
        elif "fetch_portfolio_readonly.py" in text:
            diag.ok("broker_safety", "Production runner uses read-only portfolio fetcher")
        else:
            diag.warn("broker_safety", "Production runner does not mention read-only portfolio fetcher")


def check_installer_hygiene(diag: Diagnostics) -> None:
    dist = diag.root / "installer" / "dist"
    if not dist.exists():
        diag.warn("installer", "Installer dist folder missing")
        return
    zips = sorted(dist.glob("BlueLotusV2_Windows_Install_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not zips:
        diag.warn("installer", "No Windows installer ZIP found")
        return
    latest = zips[0]
    bad_entries: list[str] = []
    required_entries = [
        "payload/bluelotus2/diagnostics/bluelotus_runtime_guard.py",
        "payload/bluelotus2/diagnostics/Repair-BlueLotusV2Runtime.ps1",
        "payload/bluelotus2/diagnostics/README_RUNTIME_GUARD.md",
        "payload/bluelotus2/run_bluelotus_v2_runtime_guard.bat",
        "payload/bluelotus2/repair_bluelotus_v2_runtime.bat",
        "payload/bluelotus2/diagnostics/dataset_contract_v2.py",
        "payload/bluelotus2/diagnostics/README_DATASET_CONTRACT.md",
        "payload/bluelotus2/mid/fetch_execution_records_readonly.py",
        "payload/bluelotus2/mid/record_cio_cognition.py",
        "payload/bluelotus2/run_bluelotus_v2_dataset_contract.bat",
    ]
    normalized_entries: set[str] = set()
    try:
        with zipfile.ZipFile(latest) as zf:
            for name in zf.namelist():
                lowered = name.lower()
                normalized = lowered.replace("\\", "/").rstrip("/")
                normalized_entries.add(normalized)
                basename = normalized.rsplit("/", 1)[-1]
                if basename == ".env":
                    bad_entries.append(name)
                elif any(pattern.lower() in lowered for pattern in BAD_ZIP_PATTERNS):
                    bad_entries.append(name)
            entries = len(zf.namelist())
    except Exception as exc:
        diag.fail("installer", "Installer ZIP could not be read", path=str(latest), error=str(exc))
        return
    missing_required_entries = [
        required
        for required in required_entries
        if not any(entry.endswith(required.lower()) for entry in normalized_entries)
    ]
    if bad_entries:
        diag.fail("installer", "Installer ZIP contains private or unsafe entries", path=str(latest), bad_entries=bad_entries[:20], count=len(bad_entries))
    elif missing_required_entries:
        diag.fail("installer", "Installer ZIP is missing required diagnostic contract files", path=str(latest), missing=missing_required_entries)
    else:
        diag.ok("installer", "Windows installer ZIP hygiene OK", path=str(latest), entries=entries, size=latest.stat().st_size)


def check_documentation(diag: Diagnostics) -> None:
    docs = {
        "documentation/BlueLotus_V2_Architecture_Documentation.md": ["Full Pipeline Flow", "Database Block Diagrams", "Sample End Outputs"],
        "documentation/BlueLotus_V2_Database_Schema_Reference.md": ["Total tables discovered: `50`", "Database Block Diagrams"],
        "documentation/BlueLotus_V2_File_Inventory.md": ["Total files documented"],
    }
    for rel, markers in docs.items():
        path = diag.root / rel
        if not path.exists():
            diag.warn("documentation", f"Documentation file missing: {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        missing = [m for m in markers if m not in text]
        if missing:
            diag.warn("documentation", f"Documentation markers missing: {rel}", missing=missing)
        else:
            diag.ok("documentation", f"Documentation markers present: {rel}")


def check_moomoo_quote(diag: Diagnostics) -> None:
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
            diag.ok("moomoo", "OpenD quote snapshot check passed", host=host, port=port)
        else:
            diag.fail("moomoo", "OpenD quote snapshot returned error", host=host, port=port, error=str(data))
    except Exception as exc:
        diag.fail("moomoo", "OpenD quote snapshot check failed", error=str(exc))


def write_json_report(diag: Diagnostics, output: Path | None, archive: bool = False, label: str = "") -> None:
    if not output:
        return
    payload = diag.to_json()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"[PASS] output: Wrote diagnostic JSON: {output}")
    if archive:
        safe_label = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in (label or "diagnostic"))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_dir = output.parent / "smoke_hygiene_archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_path = archive_dir / f"smoke_hygiene_{safe_label}_{stamp}.json"
        archive_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        print(f"[PASS] output: Archived diagnostic JSON: {archive_path}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Run BlueLotus V2 smoke and hygiene diagnostics.")
    ap.add_argument("--root", default=r"C:\bluelotus3", help="BlueLotus root directory.")
    ap.add_argument("--check-moomoo", action="store_true", help="Run read-only Moomoo OpenD quote check.")
    ap.add_argument("--strict", action="store_true", help="Treat warnings as non-zero exit.")
    ap.add_argument("--json-output", default="", help="Optional diagnostic JSON output path.")
    ap.add_argument("--no-json-output", action="store_true", help="Do not write diagnostic JSON artifact.")
    ap.add_argument("--archive", action="store_true", help="Also write a timestamped copy under data/audit/smoke_hygiene_archive.")
    ap.add_argument("--label", default="diagnostic", help="Archive label, for example preflight or postflight.")
    args = ap.parse_args()

    root = Path(args.root)
    diag = Diagnostics(root)
    load_dotenv_if_available(root)

    print("BlueLotus V2 Smoke / Hygiene Diagnostics")
    print(f"Root: {root}")
    print(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    print()

    check_filesystem(diag)
    check_python_imports(diag)
    check_env(diag)
    check_runtime_guard(diag)
    check_mysql(diag)
    check_dataset(diag)
    check_dataset_contract(diag)
    check_reports(diag)
    check_source_syntax_and_safety(diag)
    check_installer_hygiene(diag)
    check_documentation(diag)
    if args.check_moomoo:
        check_moomoo_quote(diag)
    else:
        diag.warn("moomoo", "Moomoo OpenD live quote check skipped; use --check-moomoo to enable")

    counts = diag.counts()
    print()
    print(f"Summary: PASS {counts.get('PASS', 0)} | WARN {counts.get('WARN', 0)} | FAIL {counts.get('FAIL', 0)}")

    output = None
    if not args.no_json_output:
        output = Path(args.json_output) if args.json_output else root / "data" / "audit" / "smoke_hygiene_latest.json"
    write_json_report(diag, output, archive=args.archive, label=args.label)

    if counts.get("FAIL", 0):
        return 1
    if args.strict and counts.get("WARN", 0):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

