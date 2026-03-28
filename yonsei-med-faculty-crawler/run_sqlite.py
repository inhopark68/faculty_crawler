import argparse
import logging
import sqlite3
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from crawler.scraper_parallel_debug import crawl_all_parallel


def build_parser():
    parser = argparse.ArgumentParser(
        description="Yonsei medicine faculty crawler runner (SQLite version)"
    )
    parser.add_argument(
        "--headless",
        type=str,
        default="true",
        help="Run Chrome in headless mode: true/false (default: true)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of parallel workers (default: 1)",
    )
    parser.add_argument(
        "--limit-departments",
        type=int,
        default=3,
        help="Limit number of departments for test runs. Use 0 for all. (default: 3)",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="output/faculty.db",
        help="SQLite DB path (default: output/faculty.db)",
    )
    return parser


def parse_bool(value: str) -> bool:
    value = str(value).strip().lower()
    if value in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def record_to_dict(record: Any) -> Dict[str, Any]:
    if is_dataclass(record):
        return asdict(record)
    if hasattr(record, "__dict__"):
        return dict(record.__dict__)
    raise TypeError(f"Unsupported record type: {type(record)!r}")


def init_db(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS faculty_records (
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
            detail_url TEXT,
            source_department_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_faculty_records_detail
        ON faculty_records(detail_url)
        """
    )


def write_sqlite(records: Iterable[Any], db_path: str):
    rows: List[Dict[str, Any]] = [record_to_dict(r) for r in records]

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(path)
    try:
        init_db(conn)

        if not rows:
            logging.warning("No records to insert. Empty DB schema created: %s", path)
            conn.commit()
            return

        insert_sql = """
            INSERT OR REPLACE INTO faculty_records (
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
                source_department_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        values = [
            (
                row.get("college_ko"),
                row.get("college_en"),
                row.get("department_ko"),
                row.get("department_en"),
                row.get("campus"),
                row.get("name_ko"),
                row.get("name_en"),
                row.get("title_ko"),
                row.get("email"),
                row.get("phone"),
                row.get("office"),
                row.get("detail_url"),
                row.get("source_department_url"),
            )
            for row in rows
        ]

        conn.executemany(insert_sql, values)
        conn.commit()

        count = conn.execute("SELECT COUNT(*) FROM faculty_records").fetchone()[0]
        logging.info("SQLite saved: %s | rows=%d", path.resolve(), count)
    finally:
        conn.close()


def main():
    parser = build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    headless = parse_bool(args.headless)

    logging.info("parallel crawler started")
    logging.info(
        "headless=%s | workers=%d | limit_departments=%d | db=%s",
        headless,
        args.workers,
        args.limit_departments,
        args.db,
    )

    records = crawl_all_parallel(
        headless=headless,
        workers=max(1, args.workers),
        limit_departments=max(0, args.limit_departments),
    )

    logging.info("crawl finished | records=%d", len(records))
    write_sqlite(records, args.db)


if __name__ == "__main__":
    main()
