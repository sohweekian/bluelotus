#!/usr/bin/env python3
"""
BlueLotus V2 database initializer for Windows deployments.

Creates the bluelotus2 database, optionally creates the application user, and
applies the schema-only SQL dump. This script does not import broker modules
and does not touch Moomoo.
"""

from __future__ import annotations

import argparse
import getpass
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List

import mysql.connector
from dotenv import load_dotenv


def q_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]+", name or ""):
        raise ValueError(f"Unsafe MySQL identifier: {name!r}")
    return f"`{name}`"


def split_sql(sql_text: str) -> List[str]:
    delimiter = ";"
    statements: List[str] = []
    buf: List[str] = []
    for raw_line in sql_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            if buf:
                buf.append(line)
            continue
        if stripped.upper().startswith("DELIMITER "):
            delimiter = stripped.split(None, 1)[1]
            continue
        buf.append(line)
        joined = "\n".join(buf).strip()
        if joined.endswith(delimiter):
            statement = joined[: -len(delimiter)].strip()
            if statement:
                statements.append(statement)
            buf = []
    tail = "\n".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements


def execute_many(cur, statements: Iterable[str]) -> int:
    count = 0
    for stmt in statements:
        cleaned = "\n".join(
            line for line in stmt.splitlines()
            if not line.strip().startswith("--")
        ).strip()
        if not cleaned:
            continue
        cur.execute(cleaned)
        count += 1
    return count


def connect(host: str, port: int, user: str, password: str, database: str | None = None):
    kwargs = {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "charset": "utf8mb4",
        "autocommit": False,
    }
    if database:
        kwargs["database"] = database
    return mysql.connector.connect(**kwargs)


def main() -> int:
    ap = argparse.ArgumentParser(description="Initialize BlueLotus V2 MySQL database.")
    ap.add_argument("--root", default=r"C:\bluelotus3", help="Installed BlueLotus root.")
    ap.add_argument("--schema", default="", help="Schema SQL path.")
    ap.add_argument("--host", default="", help="MySQL host.")
    ap.add_argument("--port", type=int, default=0, help="MySQL port.")
    ap.add_argument("--database", default="", help="Database name.")
    ap.add_argument("--admin-user", default="", help="Admin/root MySQL user.")
    ap.add_argument("--admin-password", default="", help="Admin/root MySQL password.")
    ap.add_argument("--app-user", default="", help="Application MySQL user.")
    ap.add_argument("--app-password", default="", help="Application MySQL password.")
    ap.add_argument("--app-host", default="localhost", help="Application user host.")
    ap.add_argument("--skip-user-create", action="store_true", help="Do not create/grant app user.")
    ap.add_argument("--apply-as-app-user", action="store_true", help="Apply schema using app user after grants.")
    args = ap.parse_args()

    root = Path(args.root)
    load_dotenv(root / ".env")

    host = args.host or os.getenv("MYSQL_HOST") or os.getenv("DB_HOST") or "127.0.0.1"
    port = args.port or int(os.getenv("MYSQL_PORT") or os.getenv("DB_PORT") or "3306")
    database = args.database or os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME") or "bluelotus2"
    app_user = args.app_user or os.getenv("MYSQL_USER") or os.getenv("DB_USER") or "bluelotus_app"
    app_password = args.app_password or os.getenv("MYSQL_PASSWORD") or os.getenv("DB_PASSWORD") or ""
    schema = Path(args.schema) if args.schema else Path(__file__).resolve().parents[1] / "schema" / "bluelotus2_schema_mysql_8_4_9.sql"

    if not schema.exists():
        print(f"[FAIL] Schema file not found: {schema}")
        return 2

    admin_user = args.admin_user
    admin_password = args.admin_password
    if not admin_user:
        admin_user = input("MySQL admin user [root]: ").strip() or "root"
    if not admin_password:
        admin_password = getpass.getpass("MySQL admin password: ")

    print(f"[INFO] Connecting to MySQL {host}:{port} as {admin_user}")
    admin_conn = connect(host, port, admin_user, admin_password)
    try:
        cur = admin_conn.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS {q_ident(database)} "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        if not args.skip_user_create:
            if not app_password:
                app_password = getpass.getpass(f"Password for app user {app_user}: ")
            cur.execute(
                "CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s",
                (app_user, args.app_host, app_password),
            )
            cur.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, "
                f"REFERENCES, TRIGGER, EXECUTE ON {q_ident(database)}.* TO %s@%s",
                (app_user, args.app_host),
            )
            cur.execute("FLUSH PRIVILEGES")
        admin_conn.commit()
        cur.close()
    except Exception:
        admin_conn.rollback()
        raise
    finally:
        admin_conn.close()

    apply_user = app_user if args.apply_as_app_user else admin_user
    apply_password = app_password if args.apply_as_app_user else admin_password
    print(f"[INFO] Applying schema to {database} as {apply_user}")
    sql_text = schema.read_text(encoding="utf-8-sig")
    statements = split_sql(sql_text)
    conn = connect(host, port, apply_user, apply_password, database)
    try:
        cur = conn.cursor()
        count = execute_many(cur, statements)
        conn.commit()
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=%s",
            (database,),
        )
        table_count = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.triggers WHERE trigger_schema=%s",
            (database,),
        )
        trigger_count = cur.fetchone()[0]
        cur.close()
        print(f"[OK] Schema statements executed: {count}")
        print(f"[OK] Tables present: {table_count}")
        print(f"[OK] Triggers present: {trigger_count}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    print("[OK] BlueLotus V2 database initialization complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

