import logging

from .crawler import crawl_all_parallel
from .database import (
    DEFAULT_DB_PATH,
    compare_and_log_changes,
    connect_db,
    get_existing_detail_urls,
    init_db,
    upsert_records_sqlite,
)

DEFAULT_WORKERS = 1


def sync_faculty(
    db_path: str = DEFAULT_DB_PATH,
    workers: int = DEFAULT_WORKERS,
    recrawl: bool = True,
    headless: bool = True,
    limit_departments: int = 0,
    retries: int = 2,
    wait_timeout: int = 20,
    enable_external_enrichment: bool = True,
):
    conn = connect_db(db_path)
    try:
        init_db(conn)

        existing_detail_urls = get_existing_detail_urls(conn)

        logging.info(
            "sync start | db_path=%s | workers=%s | recrawl=%s | limit_departments=%s | retries=%s | wait_timeout=%s | external_enrichment=%s",
            db_path,
            workers,
            recrawl,
            limit_departments,
            retries,
            wait_timeout,
            enable_external_enrichment,
        )

        records = crawl_all_parallel(
            headless=headless,
            workers=workers,
            existing_detail_urls=existing_detail_urls,
            recrawl=recrawl,
            limit_departments=limit_departments,
            retries=retries,
            wait_timeout=wait_timeout,
            enable_external_enrichment=enable_external_enrichment,
        )

        for r in records:
            compare_and_log_changes(conn, r)

        upsert_records_sqlite(conn, records)

        logging.info(
            "sync done | crawled=%d | recrawl=%s | db_path=%s",
            len(records),
            recrawl,
            db_path,
        )

    finally:
        conn.close()
