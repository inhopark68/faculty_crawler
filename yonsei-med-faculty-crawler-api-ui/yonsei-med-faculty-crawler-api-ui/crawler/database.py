import csv
import os
import sqlite3
from dataclasses import asdict
from typing import List, Set

import pandas as pd

from .models import FacultyRecord


def ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


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
            source_department_url TEXT,
            collected_at TEXT
        )
    """)
    conn.commit()
    return conn


def get_connection(db_path: str):
    return sqlite3.connect(db_path, check_same_thread=False)


def get_existing_detail_urls(conn) -> Set[str]:
    cur = conn.cursor()
    cur.execute("SELECT detail_url FROM faculty WHERE detail_url IS NOT NULL AND detail_url != ''")
    return {row[0] for row in cur.fetchall() if row[0]}


def save_to_db(conn, records: List[FacultyRecord]):
    cur = conn.cursor()
    for r in records:
        cur.execute("""
            INSERT OR REPLACE INTO faculty (
                college_ko, college_en, department_ko, department_en, campus,
                name_ko, name_en, title_ko, email, phone, office,
                detail_url, source_department_url, collected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            r.college_ko, r.college_en, r.department_ko, r.department_en, r.campus,
            r.name_ko, r.name_en, r.title_ko, r.email, r.phone, r.office,
            r.detail_url, r.source_department_url, r.collected_at
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


def save_to_xlsx(records: List[FacultyRecord], xlsx_path: str):
    ensure_parent_dir(xlsx_path)
    rows = [asdict(r) for r in records]
    if not rows:
        return
    df = pd.DataFrame(rows)
    df.to_excel(xlsx_path, index=False)
    try:
        from openpyxl import load_workbook
        wb = load_workbook(xlsx_path)
        ws = wb.active
        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                value = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(value))
            ws.column_dimensions[col_letter].width = min(max_len + 2, 50)
        wb.save(xlsx_path)
    except Exception:
        pass
