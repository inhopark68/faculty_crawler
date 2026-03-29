import csv
import logging
import sqlite3
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable, Set

from .models import FacultyRecord

DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "output" / "yonsei_medicine_faculty.db"


def connect_db(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def _get_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row[1] for row in rows}


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_sql: str):
    cols = _get_columns(conn, table_name)
    if column_name not in cols:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")
        conn.commit()
        logging.info("added missing column: %s.%s", table_name, column_name)


def init_db(conn=None):
    should_close = False

    if conn is None:
        conn = connect_db()
        should_close = True

    try:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS faculty (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            college_ko TEXT,
            college_en TEXT,
            department_ko TEXT,
            department_en TEXT,
            campus TEXT,
            name_ko TEXT,
            name_en TEXT,
            title_ko TEXT,
            email TEXT,
            phone TEXT,
            office TEXT,
            detail_url TEXT NOT NULL UNIQUE,
            source_department_url TEXT
        )
        """)
        conn.commit()

        ensure_faculty_table_schema(conn)
    finally:
        if should_close:
            conn.close()


def create_db(conn=None):
    init_db(conn)


def ensure_faculty_table_schema(conn=None):
    should_close = False

    if conn is None:
        conn = connect_db()
        should_close = True

    try:
        _ensure_column(conn, "faculty", "updated_at", "DATETIME")
        _ensure_column(conn, "faculty", "collected_at", "DATETIME")
        _ensure_column(conn, "faculty", "college_ko", "TEXT")
        _ensure_column(conn, "faculty", "college_en", "TEXT")
        _ensure_column(conn, "faculty", "department_ko", "TEXT")
        _ensure_column(conn, "faculty", "department_en", "TEXT")
        _ensure_column(conn, "faculty", "campus", "TEXT")
        _ensure_column(conn, "faculty", "name_ko", "TEXT")
        _ensure_column(conn, "faculty", "name_en", "TEXT")
        _ensure_column(conn, "faculty", "title_ko", "TEXT")
        _ensure_column(conn, "faculty", "email", "TEXT")
        _ensure_column(conn, "faculty", "phone", "TEXT")
        _ensure_column(conn, "faculty", "office", "TEXT")
        _ensure_column(conn, "faculty", "detail_url", "TEXT")
        _ensure_column(conn, "faculty", "source_department_url", "TEXT")

        # ORCID / external enrichment
        _ensure_column(conn, "faculty", "orcid_id", "TEXT")
        _ensure_column(conn, "faculty", "orcid_url", "TEXT")
        _ensure_column(conn, "faculty", "external_source_url", "TEXT")

        conn.execute("""
        UPDATE faculty
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL OR TRIM(updated_at) = ''
        """)
        conn.execute("""
        UPDATE faculty
        SET collected_at = CURRENT_TIMESTAMP
        WHERE collected_at IS NULL OR TRIM(collected_at) = ''
        """)
        conn.commit()
    finally:
        if should_close:
            conn.close()


def get_existing_detail_urls(conn=None) -> Set[str]:
    should_close = False

    if conn is None:
        conn = connect_db()
        should_close = True

    try:
        rows = conn.execute("""
            SELECT detail_url
            FROM faculty
            WHERE detail_url IS NOT NULL AND TRIM(detail_url) != ''
        """).fetchall()
        return {row[0] for row in rows}
    finally:
        if should_close:
            conn.close()


def load_existing_detail_urls(conn=None) -> Set[str]:
    return get_existing_detail_urls(conn)


def compare_and_log_changes(conn: sqlite3.Connection, record: FacultyRecord):
    row = conn.execute("""
        SELECT
            name_ko, name_en, title_ko, email, phone, office,
            department_ko, department_en, orcid_id, orcid_url,
            external_source_url
        FROM faculty
        WHERE detail_url = ?
    """, (record.detail_url,)).fetchone()

    if not row:
        logging.info("[NEW] %s | %s", getattr(record, "name_ko", ""), getattr(record, "detail_url", ""))
        return

    old = {
        "name_ko": row[0] or "",
        "name_en": row[1] or "",
        "title_ko": row[2] or "",
        "email": row[3] or "",
        "phone": row[4] or "",
        "office": row[5] or "",
        "department_ko": row[6] or "",
        "department_en": row[7] or "",
        "orcid_id": row[8] or "",
        "orcid_url": row[9] or "",
        "external_source_url": row[10] or "",
    }
    new = {
        "name_ko": getattr(record, "name_ko", "") or "",
        "name_en": getattr(record, "name_en", "") or "",
        "title_ko": getattr(record, "title_ko", "") or "",
        "email": getattr(record, "email", "") or "",
        "phone": getattr(record, "phone", "") or "",
        "office": getattr(record, "office", "") or "",
        "department_ko": getattr(record, "department_ko", "") or "",
        "department_en": getattr(record, "department_en", "") or "",
        "orcid_id": getattr(record, "orcid_id", "") or "",
        "orcid_url": getattr(record, "orcid_url", "") or "",
        "external_source_url": getattr(record, "external_source_url", "") or "",
    }

    changed = []
    for key in old:
        if old[key] != new[key]:
            changed.append(f"{key}: '{old[key]}' -> '{new[key]}'")

    if changed:
        logging.info(
            "[UPDATED] %s | %s | %s",
            getattr(record, "name_ko", ""),
            getattr(record, "detail_url", ""),
            " | ".join(changed),
        )


def upsert_records_sqlite(conn: sqlite3.Connection, records: Iterable[FacultyRecord]):
    ensure_faculty_table_schema(conn)

    sql = """
    INSERT INTO faculty (
        college_ko,
        college_en,
        department_ko,
        department_en,
        campus,
        name_ko,
        name_en,
        title_ko,
        email,
        phone,
        office,
        detail_url,
        source_department_url,
        orcid_id,
        orcid_url,
        external_source_url,
        collected_at,
        updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    ON CONFLICT(detail_url) DO UPDATE SET
        college_ko=excluded.college_ko,
        college_en=excluded.college_en,
        department_ko=excluded.department_ko,
        department_en=excluded.department_en,
        campus=excluded.campus,
        name_ko=excluded.name_ko,
        name_en=excluded.name_en,
        title_ko=excluded.title_ko,
        email=excluded.email,
        phone=excluded.phone,
        office=excluded.office,
        source_department_url=excluded.source_department_url,
        orcid_id=excluded.orcid_id,
        orcid_url=excluded.orcid_url,
        external_source_url=excluded.external_source_url,
        updated_at=CURRENT_TIMESTAMP
    """

    rows = []
    for r in records:
        detail_url = getattr(r, "detail_url", "")
        if not detail_url:
            continue
        rows.append((
            getattr(r, "college_ko", ""),
            getattr(r, "college_en", ""),
            getattr(r, "department_ko", ""),
            getattr(r, "department_en", ""),
            getattr(r, "campus", ""),
            getattr(r, "name_ko", ""),
            getattr(r, "name_en", ""),
            getattr(r, "title_ko", ""),
            getattr(r, "email", ""),
            getattr(r, "phone", ""),
            getattr(r, "office", ""),
            detail_url,
            getattr(r, "source_department_url", ""),
            getattr(r, "orcid_id", ""),
            getattr(r, "orcid_url", ""),
            getattr(r, "external_source_url", ""),
        ))

    conn.executemany(sql, rows)
    conn.commit()
    logging.info("upsert completed: %d rows", len(rows))


def save_records(conn: sqlite3.Connection, records: Iterable[FacultyRecord]):
    return upsert_records_sqlite(conn, records)


def save_to_db(records, conn=None):
    should_close = False

    if conn is None:
        conn = connect_db()
        should_close = True

    try:
        upsert_records_sqlite(conn, records)
    finally:
        if should_close:
            conn.close()


def _record_to_dict(record):
    if is_dataclass(record):
        row = asdict(record)
    else:
        row = {
            "college_ko": getattr(record, "college_ko", ""),
            "college_en": getattr(record, "college_en", ""),
            "department_ko": getattr(record, "department_ko", ""),
            "department_en": getattr(record, "department_en", ""),
            "campus": getattr(record, "campus", ""),
            "name_ko": getattr(record, "name_ko", ""),
            "name_en": getattr(record, "name_en", ""),
            "title_ko": getattr(record, "title_ko", ""),
            "email": getattr(record, "email", ""),
            "phone": getattr(record, "phone", ""),
            "office": getattr(record, "office", ""),
            "detail_url": getattr(record, "detail_url", ""),
            "source_department_url": getattr(record, "source_department_url", ""),
            "orcid_id": getattr(record, "orcid_id", ""),
            "orcid_url": getattr(record, "orcid_url", ""),
            "external_source_url": getattr(record, "external_source_url", ""),
        }
    row.setdefault("orcid_id", getattr(record, "orcid_id", ""))
    row.setdefault("orcid_url", getattr(record, "orcid_url", ""))
    row.setdefault("external_source_url", getattr(record, "external_source_url", ""))
    return row


def save_to_csv(csv_path: str, records: Iterable[FacultyRecord]):
    rows = [_record_to_dict(r) for r in records]
    if not rows:
        return

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    logging.info("csv saved: %s", csv_path)
