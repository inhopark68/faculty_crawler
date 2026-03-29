import logging
from pathlib import Path

from app.crawler import crawl_all_parallel
from app.database import (
    connect_db,
    create_db,
    ensure_faculty_table_schema,
    get_existing_detail_urls,
    save_to_csv,
    save_to_db,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DB_PATH = OUTPUT_DIR / "yonsei_medicine_faculty.db"
CSV_PATH = OUTPUT_DIR / "faculty_export.csv"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    conn = connect_db(DB_PATH)
    try:
        create_db(conn)
        ensure_faculty_table_schema(conn)
        existing_detail_urls = get_existing_detail_urls(conn)
    finally:
        conn.close()

    records = crawl_all_parallel(
        headless=True,
        workers=1,
        existing_detail_urls=existing_detail_urls,
        limit_departments=0,
        recrawl=True,
    )

    save_to_db(records)
    save_to_csv(str(CSV_PATH), records)

    logging.info("done | records=%d | db=%s | csv=%s", len(records), DB_PATH, CSV_PATH)


if __name__ == "__main__":
    main()