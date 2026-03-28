from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Query
import sqlite3

DB_PATH = Path(__file__).resolve().parents[1] / "output" / "yonsei_medicine_faculty.db"

app = FastAPI(title="Yonsei Medicine Faculty API", version="1.0.0")


def get_conn():
    return sqlite3.connect(DB_PATH)


@app.get("/health")
def health():
    exists = DB_PATH.exists()
    return {"ok": True, "db_exists": exists, "db_path": str(DB_PATH)}


@app.get("/faculty")
def list_faculty(
    department: Optional[str] = Query(default=None),
    name: Optional[str] = Query(default=None),
    email: Optional[str] = Query(default=None),
    has_email: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    sql = """
    SELECT
        college_ko, college_en, department_ko, department_en, campus,
        name_ko, name_en, title_ko, email, phone, office,
        detail_url, source_department_url, collected_at
    FROM faculty
    WHERE 1=1
    """
    params = []

    if department:
        sql += " AND (department_ko LIKE ? OR department_en LIKE ?)"
        params.extend([f"%{department}%", f"%{department}%"])

    if name:
        sql += " AND (name_ko LIKE ? OR name_en LIKE ?)"
        params.extend([f"%{name}%", f"%{name}%"])

    if email:
        sql += " AND email LIKE ?"
        params.append(f"%{email}%")

    if has_email is True:
        sql += " AND email IS NOT NULL AND TRIM(email) != ''"
    elif has_email is False:
        sql += " AND (email IS NULL OR TRIM(email) = '')"

    sql += " ORDER BY department_ko, name_ko, name_en LIMIT ?"
    params.append(limit)

    conn = get_conn()
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(sql, params).fetchall()
        return {
            "count": len(rows),
            "items": [dict(row) for row in rows],
        }
    finally:
        conn.close()


@app.get("/faculty/departments")
def list_departments():
    conn = get_conn()
    try:
        rows = conn.execute(
            """
            SELECT department_ko, department_en, COUNT(*) AS cnt
            FROM faculty
            GROUP BY department_ko, department_en
            ORDER BY department_ko
            """
        ).fetchall()
        return {
            "count": len(rows),
            "items": [
                {"department_ko": r[0], "department_en": r[1], "count": r[2]}
                for r in rows
            ],
        }
    finally:
        conn.close()
