import json
import sqlite3
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Iterable, List, Set

import pandas as pd


def _record_to_dict(record):
    if is_dataclass(record):
        return asdict(record)
    if hasattr(record, "__dict__"):
        return dict(record.__dict__)
    if isinstance(record, dict):
        return dict(record)
    raise TypeError(f"Unsupported record type: {type(record)!r}")


def _normalize_records(records: Iterable) -> List[dict]:
    normalized = []
    for record in records:
        row = _record_to_dict(record)
        normalized.append({
            "college_ko": row.get("college_ko", ""),
            "college_en": row.get("college_en", ""),
            "department_ko": row.get("department_ko", ""),
            "department_en": row.get("department_en", ""),
            "campus": row.get("campus", ""),
            "name_ko": row.get("name_ko", ""),
            "name_en": row.get("name_en", ""),
            "title_ko": row.get("title_ko", ""),
            "email": row.get("email", ""),
            "phone": row.get("phone", ""),
            "office": row.get("office", ""),
            "detail_url": row.get("detail_url", ""),
            "source_department_url": row.get("source_department_url", ""),
            "collected_at": row.get("collected_at", ""),
        })
    return normalized


def _ensure_parent_dir(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _ensure_faculty_schema(conn: sqlite3.Connection):
    cur = conn.cursor()

    cur.execute("""
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
            detail_url TEXT UNIQUE,
            source_department_url TEXT,
            collected_at TEXT
        )
    """)

    cur.execute("PRAGMA table_info(faculty)")
    existing_columns = {row[1] for row in cur.fetchall()}

    required_columns = {
        "college_ko": "TEXT",
        "college_en": "TEXT",
        "department_ko": "TEXT",
        "department_en": "TEXT",
        "campus": "TEXT",
        "name_ko": "TEXT",
        "name_en": "TEXT",
        "title_ko": "TEXT",
        "email": "TEXT",
        "phone": "TEXT",
        "office": "TEXT",
        "detail_url": "TEXT",
        "source_department_url": "TEXT",
        "collected_at": "TEXT",
    }

    for col, col_type in required_columns.items():
        if col not in existing_columns:
            cur.execute(f"ALTER TABLE faculty ADD COLUMN {col} {col_type}")

    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_faculty_detail_url ON faculty(detail_url)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faculty_department_en ON faculty(department_en)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_faculty_name_ko ON faculty(name_ko)")
    conn.commit()


def create_db(db_path: str) -> sqlite3.Connection:
    _ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
    _ensure_faculty_schema(conn)
    return conn


def save_to_db(conn: sqlite3.Connection, records: Iterable):
    _ensure_faculty_schema(conn)
    rows = _normalize_records(records)
    if not rows:
        return

    cur = conn.cursor()
    for r in rows:
        cur.execute("""
            INSERT OR REPLACE INTO faculty (
                college_ko, college_en, department_ko, department_en, campus,
                name_ko, name_en, title_ko, email, phone, office,
                detail_url, source_department_url, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r["college_ko"],
            r["college_en"],
            r["department_ko"],
            r["department_en"],
            r["campus"],
            r["name_ko"],
            r["name_en"],
            r["title_ko"],
            r["email"],
            r["phone"],
            r["office"],
            r["detail_url"],
            r["source_department_url"],
            r["collected_at"],
        ))
    conn.commit()


def get_existing_detail_urls(conn: sqlite3.Connection) -> Set[str]:
    _ensure_faculty_schema(conn)
    cur = conn.cursor()
    cur.execute("SELECT detail_url FROM faculty WHERE detail_url IS NOT NULL AND detail_url != ''")
    return {row[0] for row in cur.fetchall() if row[0]}


def fetch_all_records(conn: sqlite3.Connection) -> List[dict]:
    _ensure_faculty_schema(conn)
    cur = conn.cursor()
    cur.execute("""
        SELECT
            college_ko, college_en, department_ko, department_en, campus,
            name_ko, name_en, title_ko, email, phone, office,
            detail_url, source_department_url, collected_at
        FROM faculty
        ORDER BY department_ko, name_ko, name_en
    """)
    columns = [
        "college_ko", "college_en", "department_ko", "department_en", "campus",
        "name_ko", "name_en", "title_ko", "email", "phone", "office",
        "detail_url", "source_department_url", "collected_at"
    ]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def save_to_csv(records: Iterable, csv_path: str):
    _ensure_parent_dir(csv_path)
    rows = _normalize_records(records)
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")


def save_to_xlsx(records: Iterable, xlsx_path: str):
    _ensure_parent_dir(xlsx_path)
    rows = _normalize_records(records)
    df = pd.DataFrame(rows)
    df.to_excel(xlsx_path, index=False)


def save_summary_json(records: Iterable, summary_path: str):
    _ensure_parent_dir(summary_path)
    rows = _normalize_records(records)
    summary = {
        "total_records": len(rows),
        "with_email": sum(1 for r in rows if r.get("email")),
        "with_phone": sum(1 for r in rows if r.get("phone")),
        "departments": {},
    }
    for r in rows:
        dept = r.get("department_ko") or r.get("department_en") or "Unknown"
        summary["departments"][dept] = summary["departments"].get(dept, 0) + 1

    Path(summary_path).write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
