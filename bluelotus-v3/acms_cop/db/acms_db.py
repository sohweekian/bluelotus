from __future__ import annotations

from typing import Any, Dict

from db.v3_db_config import load_v3_db_config, mysql_connect_kwargs, safe_identifier


def get_connection(database: str | None = None, include_database: bool = True):
    import mysql.connector

    cfg = load_v3_db_config(include_database=include_database)
    kwargs = mysql_connect_kwargs(cfg)
    if database:
        kwargs["database"] = safe_identifier(database)
    return mysql.connector.connect(**kwargs)


def create_database_if_missing(database: str) -> None:
    cfg = load_v3_db_config(include_database=False)
    db_name = safe_identifier(database)
    if db_name.lower() == cfg.database.lower() and not db_name:
        raise ValueError("Database name is required.")
    conn = get_connection(include_database=False)
    try:
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
        cursor.close()
    finally:
        conn.close()


def insert_row(cursor: Any, table: str, row: Dict[str, Any]) -> int:
    columns = list(row.keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_sql = ", ".join(f"`{col}`" for col in columns)
    sql = f"INSERT INTO `{safe_identifier(table)}` ({col_sql}) VALUES ({placeholders})"
    cursor.execute(sql, [row[col] for col in columns])
    return int(cursor.lastrowid or 0)

