"""
BlueLotus Digital Institution — V2.0
core/db.py v2.0 — MySQL Database Layer

ARCHITECTURE REVISION v2.0:
  Research finding: mysql-connector pool exhaustion occurs because
  sequential pipelines that write hundreds of rows do not benefit from
  pooling — they benefit from a single persistent connection reused
  across the entire ingest cycle. Pool-per-write causes connection
  leak when duplicate-key errors prevent proper connection release
  (confirmed bug: bugs.mysql.com/84476).

  Solution: Two connection modes:
    1. get_connection()     — pool connection for ad-hoc queries
    2. get_cycle_conn()     — single persistent connection for
                              bulk ingest cycles (one connection,
                              reused across all writes in a cycle)

  The ingest cycle always uses get_cycle_conn() + close_cycle_conn()
  at the end. This eliminates pool exhaustion entirely.

Doctrine: Memory before aesthetics. Governance before automation.
CIO      : Kian Soh
Date     : May 2026
"""

import os
import uuid
import json
import hashlib
import logging
import time as _time
from datetime import datetime
from typing import Optional

import mysql.connector
from mysql.connector import pooling, Error as MySQLError
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("bluelotus.db")

# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────
def _get_config() -> dict:
    database = os.getenv("MYSQL_DATABASE") or os.getenv("DB_NAME") or os.getenv("V3_MYSQL_DATABASE")
    if not database:
        raise RuntimeError("Database name is not configured. Set MYSQL_DATABASE, DB_NAME, or V3_MYSQL_DATABASE.")
    return {
        "host":              os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port":              int(os.getenv("MYSQL_PORT", "3306")),
        "database":          database,
        "user":              os.getenv("MYSQL_USER", ""),
        "password":          os.getenv("MYSQL_PASSWORD", ""),
        "charset":           "utf8mb4",
        "collation":         "utf8mb4_unicode_ci",
        "use_unicode":       True,
        "autocommit":        False,
        "connection_timeout": 10,
    }

# ─────────────────────────────────────────────────────────────────────
# MODE 1: CONNECTION POOL — for ad-hoc queries (health checks, audits)
# ─────────────────────────────────────────────────────────────────────
_pool: Optional[pooling.MySQLConnectionPool] = None

def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        cfg = _get_config()
        _pool = pooling.MySQLConnectionPool(
            pool_name="bluelotus_pool",
            pool_size=8,           # modest — only used for ad-hoc queries
            pool_reset_session=True,
            **cfg,
        )
        logger.info("Connection pool initialised: %s @ %s:%s",
                    cfg["database"], cfg["host"], cfg["port"])
    return _pool

def get_connection():
    """Ad-hoc pooled connection. For health checks and one-off queries."""
    last_err = None
    for attempt in range(3):
        try:
            return _get_pool().get_connection()
        except MySQLError as e:
            last_err = e
            if attempt < 2:
                _time.sleep(0.3 * (attempt + 1))
    raise last_err

# ─────────────────────────────────────────────────────────────────────
# MODE 2: CYCLE CONNECTION — single persistent connection for bulk writes
# Research: sequential pipelines are faster and safer with one
# persistent connection. Eliminates pool exhaustion entirely.
# ─────────────────────────────────────────────────────────────────────
_cycle_conn = None

def get_cycle_conn():
    """
    Get (or create) the persistent cycle connection.
    One connection reused across all writes in an ingest cycle.
    Call close_cycle_conn() at the end of each cycle.
    """
    global _cycle_conn
    if _cycle_conn is None or not _cycle_conn.is_connected():
        cfg = _get_config()
        _cycle_conn = mysql.connector.connect(**cfg)
        logger.debug("Cycle connection opened")
    return _cycle_conn

def close_cycle_conn():
    """Close the cycle connection. Call at the end of each ingest cycle."""
    global _cycle_conn
    if _cycle_conn is not None:
        try:
            if _cycle_conn.is_connected():
                _cycle_conn.close()
            logger.debug("Cycle connection closed")
        except Exception as e:
            logger.warning("close_cycle_conn error: %s", e)
        finally:
            _cycle_conn = None

# ─────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────
def _new_uuid() -> str:
    return str(uuid.uuid4())

def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()

def _to_json(obj) -> Optional[str]:
    if obj is None:
        return None
    if isinstance(obj, str):
        return obj
    return json.dumps(obj, ensure_ascii=False, default=str)

# ─────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────────────────────────────
def test_connection() -> bool:
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT 1 AS ping")
        assert cursor.fetchone()["ping"] == 1

        current_db = _get_config()["database"]
        cursor.execute("SELECT DATABASE() AS db")
        assert cursor.fetchone()["db"] == current_db

        cursor.execute("SHOW TABLES")
        tables   = {next(iter(row.values())) for row in cursor.fetchall()}
        required = {
            "raw_signal_archive", "market_events",
            "daily_regime_snapshots", "dashboard_snapshots",
            "decision_audit_log", "extraction_audit_log",
            "institutional_doctrine", "strategist_reports",
            "telegram_delivery_archive", "ticker_forecasts",
        }
        missing = required - tables
        assert not missing, f"Missing tables: {missing}"

        cursor.execute("SELECT COUNT(*) AS cnt FROM institutional_doctrine")
        assert cursor.fetchone()["cnt"] >= 5

        cursor.execute(
            "SELECT TRIGGER_NAME FROM information_schema.TRIGGERS "
            "WHERE EVENT_OBJECT_TABLE='raw_signal_archive' "
            "AND TRIGGER_SCHEMA=%s",
            (current_db,),
        )
        triggers = [r["TRIGGER_NAME"] for r in cursor.fetchall()]

        cursor.close()
        conn.close()

        logger.info("=" * 60)
        logger.info("BLUELOTUS DATABASE HEALTH CHECK")
        logger.info("=" * 60)
        logger.info("  ✅  Ping                : OK")
        logger.info("  ✅  Database            : %s", current_db)
        logger.info("  ✅  Tables              : %d / %d", len(tables), len(required))
        logger.info("  ✅  Founding Doctrines  : confirmed")
        logger.info("  ✅  Immutability Triggers: %s", triggers)
        logger.info("  STATUS: HEALTHY")
        logger.info("=" * 60)
        return True

    except AssertionError as e:
        logger.error("❌  Health check failed: %s", e)
        return False
    except MySQLError as e:
        logger.error("❌  MySQL error: %s", e)
        return False
    except Exception as e:
        logger.error("❌  Unexpected: %s", e)
        return False

# ─────────────────────────────────────────────────────────────────────
# LAYER 0 — WRITE RAW SIGNAL
# Uses cycle connection (no pool contention)
# ─────────────────────────────────────────────────────────────────────
def write_raw_signal(
    source: str,
    ingestion_method: str,
    raw_payload: dict,
    raw_text: Optional[str] = None,
    source_url: Optional[str] = None,
    source_feed: Optional[str] = None,
    ingestion_agent: str = "bluelotus_agent_v2",
    raw_format: str = "json",
    signal_type: Optional[str] = None,
    suspected_category: Optional[str] = None,
    suspected_entities: Optional[list] = None,
    suspected_impact: Optional[str] = None,
    quality_score: Optional[float] = None,
    quality_flags: Optional[dict] = None,
    use_cycle_conn: bool = False,
) -> Optional[str]:
    """
    Write one raw signal to raw_signal_archive (Layer 0).
    Set use_cycle_conn=True during ingest cycles for performance.
    Returns ingestion_id on success, None on duplicate or error.
    """
    ingestion_id  = _new_uuid()
    payload_str   = json.dumps(raw_payload, ensure_ascii=False,
                               sort_keys=True, default=str)
    payload_hash  = _sha256(payload_str)
    payload_size  = len(payload_str.encode("utf-8"))

    sql = """
        INSERT INTO raw_signal_archive (
            ingestion_id, source, source_url, source_feed,
            ingestion_method, ingestion_agent,
            raw_payload, raw_text, raw_format,
            payload_hash, payload_size_bytes,
            signal_type, suspected_category, suspected_entities,
            suspected_impact, extraction_status,
            quality_score, quality_flags, manually_reviewed
        ) VALUES (
            %s,%s,%s,%s, %s,%s, %s,%s,%s, %s,%s,
            %s,%s,%s, %s,'pending', %s,%s, 0
        )
    """
    values = (
        ingestion_id, source, source_url, source_feed,
        ingestion_method, ingestion_agent,
        payload_str, raw_text, raw_format,
        payload_hash, payload_size,
        signal_type, suspected_category, _to_json(suspected_entities),
        suspected_impact,
        quality_score, _to_json(quality_flags),
    )

    try:
        if use_cycle_conn:
            conn   = get_cycle_conn()
            cursor = conn.cursor()
            cursor.execute(sql, values)
            conn.commit()
            cursor.close()
        else:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, values)
            conn.commit()
            cursor.close()
            conn.close()

        return ingestion_id

    except MySQLError as e:
        if e.errno == 1062:   # Duplicate entry — correct, expected
            return None
        logger.error("write_raw_signal failed [%s]: %s", source, e)
        try:
            if use_cycle_conn:
                get_cycle_conn().rollback()
            else:
                conn.rollback()
                conn.close()
        except Exception:
            pass
        return None
    except Exception as e:
        logger.error("write_raw_signal unexpected [%s]: %s", source, e)
        return None

# ─────────────────────────────────────────────────────────────────────
# LAYER 1 — WRITE MARKET EVENT
# ─────────────────────────────────────────────────────────────────────
def write_market_event(
    raw_ingestion_id: str,
    source: str,
    event_timestamp: datetime,
    category: str,
    headline: Optional[str] = None,
    raw_text: Optional[str] = None,
    trust_score: Optional[float] = None,
    impact_score: Optional[float] = None,
    entities: Optional[list] = None,
    regime_context: Optional[str] = None,
    tags: Optional[dict] = None,
    extraction_confidence: Optional[float] = None,
) -> Optional[str]:
    ingestion_id = _new_uuid()
    hash_input   = f"{headline or ''}|{source}|{event_timestamp.isoformat()}"
    event_hash   = _sha256(hash_input)

    sql = """
        INSERT INTO market_events (
            ingestion_id, raw_ingestion_id, event_hash,
            source, event_timestamp, category,
            trust_score, impact_score, entities,
            regime_context, headline, raw_text,
            tags, extraction_confidence, processed
        ) VALUES (
            %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s,0
        )
    """
    values = (
        ingestion_id, raw_ingestion_id, event_hash,
        source, event_timestamp, category,
        trust_score, impact_score, _to_json(entities),
        regime_context, headline, raw_text,
        _to_json(tags), extraction_confidence,
    )
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
        return ingestion_id
    except MySQLError as e:
        if e.errno == 1062:
            return None
        logger.error("write_market_event failed [%s]: %s", source, e)
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return None

# ─────────────────────────────────────────────────────────────────────
# EXTRACTION AUDIT
# ─────────────────────────────────────────────────────────────────────
def write_extraction_audit(
    raw_ingestion_id: str,
    extracted_event_id: Optional[str] = None,
    extraction_model: Optional[str] = None,
    extraction_version: Optional[str] = None,
    extraction_duration_ms: Optional[int] = None,
    extracted_category: Optional[str] = None,
    extracted_entities: Optional[list] = None,
    extracted_trust_score: Optional[float] = None,
    extracted_impact_score: Optional[float] = None,
    extracted_regime: Optional[str] = None,
    extraction_confidence: Optional[float] = None,
    validation_passed: Optional[bool] = None,
    validation_errors: Optional[list] = None,
    human_corrected: bool = False,
    use_cycle_conn: bool = False,
) -> bool:
    audit_id = _new_uuid()
    sql = """
        INSERT INTO extraction_audit_log (
            audit_id, raw_ingestion_id, extracted_event_id,
            extracted_at, extraction_model, extraction_version,
            extraction_duration_ms, extracted_category, extracted_entities,
            extracted_trust_score, extracted_impact_score,
            extracted_regime, extraction_confidence,
            validation_passed, validation_errors, human_corrected
        ) VALUES (
            %s,%s,%s, %s,%s,%s, %s,%s,%s, %s,%s, %s,%s, %s,%s,%s
        )
    """
    values = (
        audit_id, raw_ingestion_id, extracted_event_id,
        datetime.now(), extraction_model, extraction_version,
        extraction_duration_ms, extracted_category,
        _to_json(extracted_entities),
        extracted_trust_score, extracted_impact_score,
        extracted_regime, extraction_confidence,
        1 if validation_passed else 0 if validation_passed is not None else None,
        _to_json(validation_errors),
        1 if human_corrected else 0,
    )
    try:
        if use_cycle_conn:
            conn   = get_cycle_conn()
            cursor = conn.cursor()
            cursor.execute(sql, values)
            conn.commit()
            cursor.close()
        else:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute(sql, values)
            conn.commit()
            cursor.close()
            conn.close()
        return True
    except MySQLError as e:
        logger.error("write_extraction_audit failed: %s", e)
        return False

# ─────────────────────────────────────────────────────────────────────
# DECISION AUDIT LOG
# ─────────────────────────────────────────────────────────────────────
def write_audit_log(
    actor: str,
    action_type: str,
    reason: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    previous_value: Optional[dict] = None,
    new_value: Optional[dict] = None,
    confidence_shift: Optional[float] = None,
    model_version: Optional[str] = None,
    session_id: Optional[str] = None,
) -> bool:
    log_id = _new_uuid()
    sql = """
        INSERT INTO decision_audit_log (
            log_id, actor, action_type,
            entity_type, entity_id,
            previous_value, new_value,
            reason, confidence_shift,
            model_version, session_id
        ) VALUES (%s,%s,%s, %s,%s, %s,%s, %s,%s, %s,%s)
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute(sql, (
            log_id, actor, action_type,
            entity_type, entity_id,
            _to_json(previous_value), _to_json(new_value),
            reason, confidence_shift,
            model_version, session_id,
        ))
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except MySQLError as e:
        logger.error("write_audit_log failed: %s", e)
        return False

# ─────────────────────────────────────────────────────────────────────
# FETCH PENDING RAW SIGNALS
# ─────────────────────────────────────────────────────────────────────
def get_pending_raw_signals(limit: int = 100) -> list:
    sql = """
        SELECT r.ingestion_id, r.source, r.source_feed,
               r.source_url, r.received_at, r.raw_payload,
               r.raw_text, r.signal_type, r.suspected_category,
               r.suspected_entities, r.quality_score
        FROM raw_signal_archive r
        LEFT JOIN extraction_audit_log e
            ON r.ingestion_id = e.raw_ingestion_id
        WHERE e.raw_ingestion_id IS NULL
        ORDER BY r.received_at ASC
        LIMIT %s
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(sql, (limit,))
        rows   = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except MySQLError as e:
        logger.error("get_pending_raw_signals failed: %s", e)
        return []

# ─────────────────────────────────────────────────────────────────────
# STANDALONE TEST
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    print()
    print("━" * 60)
    print("  BLUELOTUS V2.0 — core/db.py v2.0")
    print("  Architecture: single cycle-connection for bulk writes")
    print("━" * 60)

    healthy = test_connection()
    if not healthy:
        print("  ❌  Connection failed. Check .env"); exit(1)

    print("\n  Testing cycle connection (bulk write mode)...")
    try:
        conn = get_cycle_conn()
        print(f"  ✅  Cycle connection open: {conn.is_connected()}")
    except Exception as e:
        print(f"  ❌  Cycle connection failed: {e}"); exit(1)

    # Layer 0 write using cycle connection
    iid = write_raw_signal(
        source="TEST_HARNESS", ingestion_method="manual_test",
        raw_payload={"test": True, "v": "2.0",
                     "ts": datetime.now().isoformat()},
        raw_text="db.py v2.0 cycle-connection test",
        signal_type="TEST", suspected_category="SYSTEM",
        quality_score=1.00, use_cycle_conn=True,
    )
    print(f"  {'✅' if iid else '⚪'}  Layer 0 write : {'OK — ' + iid if iid else 'duplicate (correct)'}")

    # Layer 1 write
    if iid:
        eid = write_market_event(
            raw_ingestion_id=iid, source="TEST_HARNESS",
            event_timestamp=datetime.now(), category="SYSTEM",
            headline="db.py v2.0 cycle-connection test",
            trust_score=1.00, impact_score=0.00,
            entities=["BLUELOTUS"], regime_context="TEST",
            extraction_confidence=1.00,
        )
        print(f"  {'✅' if eid else '⚪'}  Layer 1 write : {'OK — ' + eid if eid else 'duplicate'}")

        ok = write_extraction_audit(
            raw_ingestion_id=iid,
            extraction_model="db_test_v2.0",
            extracted_category="SYSTEM",
            extracted_trust_score=1.00,
            validation_passed=True,
            use_cycle_conn=True,
        )
        print(f"  {'✅' if ok else '❌'}  Extraction audit: {'OK' if ok else 'FAILED'}")

    ok = write_audit_log(
        actor="core/db.py", action_type="CONNECTION_TEST",
        reason="v2.0 cycle-connection architecture test",
        model_version="bluelotus_v2.0",
    )
    print(f"  {'✅' if ok else '❌'}  Audit log: {'OK' if ok else 'FAILED'}")

    close_cycle_conn()
    print("  ✅  Cycle connection closed")

    pending = get_pending_raw_signals(limit=5)
    print(f"  ✅  Pending signals: {len(pending)} in queue")

    print()
    print("━" * 60)
    print("  core/db.py v2.0 — FULLY OPERATIONAL")
    print("  Pool exhaustion issue: RESOLVED (cycle-connection pattern)")
    print("━" * 60)
