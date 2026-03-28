import argparse
import logging
from pathlib import Path

from crawler.config import DEFAULT_CSV_PATH, DEFAULT_DB_PATH, DEFAULT_LOG_PATH, DEFAULT_XLSX_PATH, HEADLESS
from crawler.database import create_db, save_to_csv, save_to_db, save_to_xlsx, get_existing_detail_urls
from crawler.reporting import print_summary, save_summary_json
from crawler.scraper_parallel import crawl_all_parallel


def str2bool(value):
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    if value in {"1", "true", "t", "yes", "y"}:
        return True
    if value in {"0", "false", "f", "no", "n"}:
            return False
    raise argparse.ArgumentTypeError(f"invalid boolean value: {value}")


def setup_logging(log_path: str):
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )


def build_parser():
    parser = argparse.ArgumentParser(description="Yonsei College of Medicine faculty crawler - parallel version")
    parser.add_argument("--headless", type=str2bool, default=HEADLESS, help="Run browser headless: true/false")
    parser.add_argument("--csv", default=DEFAULT_CSV_PATH, help="CSV output path")
    parser.add_argument("--xlsx", default=DEFAULT_XLSX_PATH, help="XLSX output path")
    parser.add_argument("--db", default=DEFAULT_DB_PATH, help="SQLite DB output path")
    parser.add_argument("--log", default=DEFAULT_LOG_PATH, help="Log file path")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel browser workers")
    parser.add_argument("--resume", type=str2bool, default=True, help="Skip already collected detail_url records from DB")
    parser.add_argument("--limit-departments", type=int, default=0, help="Limit number of departments for testing (0 = no limit)")
    parser.add_argument("--save-xlsx", type=str2bool, default=True, help="Whether to save XLSX output")
    parser.add_argument("--save-csv", type=str2bool, default=True, help="Whether to save CSV output")
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    setup_logging(args.log)
    logging.info("parallel crawler started")

    conn = create_db(args.db)
    try:
        existing_detail_urls = get_existing_detail_urls(conn) if args.resume else set()
        logging.info("resume mode: %s | existing records: %d", args.resume, len(existing_detail_urls))

        records = crawl_all_parallel(
            headless=args.headless,
            workers=args.workers,
            existing_detail_urls=existing_detail_urls,
            limit_departments=args.limit_departments,
        )
        logging.info("newly crawled records: %d", len(records))
        save_to_db(conn, records)
    finally:
        conn.close()

    if args.save_csv:
        save_to_csv(records, args.csv)
        logging.info("saved csv: %s", args.csv)

    if args.save_xlsx:
        save_to_xlsx(records, args.xlsx)
        logging.info("saved xlsx: %s", args.xlsx)

    summary_path = str(Path(args.db).with_suffix(".summary.json"))
    save_summary_json(records, summary_path)
    logging.info("saved summary: %s", summary_path)

    print_summary(records)
    logging.info("parallel crawler finished")


if __name__ == "__main__":
    main()
