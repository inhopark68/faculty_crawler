import csv
import os
import sqlite3
from dataclasses import asdict
from typing import List

from .models import FacultyRecord


def ensure_parent_dir(path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)


def create_db(db_path: str):
    ensure_parent_dir(db_path)
    conn = sqlite3.connect(db_path)
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
            source_department_url TEXT
        )
    """)
    conn.commit()
    return conn


def save_to_db(conn, records: List[FacultyRecord]):
    cur = conn.cursor()
    for r in records:
        cur.execute("""
            INSERT OR REPLACE INTO faculty (
                college_ko, college_en, department_ko, department_en, campus,
                name_ko, name_en, title_ko, email, phone, office,
                detail_url, source_department_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.college_ko, r.college_en, r.department_ko, r.department_en, r.campus,
            r.name_ko, r.name_en, r.title_ko, r.email, r.phone, r.office,
            r.detail_url, r.source_department_url
        ))
    conn.commit()


def save_to_csv(records: List[FacultyRecord], csv_path: str):
    ensure_parent_dir(csv_path)

    rows = [asdict(r) for r in records]
    if not rows:
        return

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
