import logging
import os

from crawler.config import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, DEFAULT_LOG_PATH
from crawler.database import create_db, save_to_csv, save_to_db
from crawler.scraper import crawl_all


def setup_logging():
    os.makedirs("logs", exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(DEFAULT_LOG_PATH, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def main():
    setup_logging()
    logging.info("crawler started")

    records = crawl_all()
    logging.info("total records: %d", len(records))

    conn = create_db(DEFAULT_DB_PATH)
    try:
        save_to_db(conn, records)
    finally:
        conn.close()

    save_to_csv(records, DEFAULT_CSV_PATH)

    logging.info("saved db: %s", DEFAULT_DB_PATH)
    logging.info("saved csv: %s", DEFAULT_CSV_PATH)
    logging.info("crawler finished")


if __name__ == "__main__":
    main()
