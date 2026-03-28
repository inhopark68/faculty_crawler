import argparse
import csv
import logging
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List

from crawler.scraper_parallel_fixed import crawl_all_parallel


def build_parser():
    parser = argparse.ArgumentParser(
        description="Yonsei medicine faculty crawler runner"
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
        "--output",
        type=str,
        default="output/faculty_records.csv",
        help="CSV output path (default: output/faculty_records.csv)",
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


def write_csv(records: Iterable[Any], output_path: str):
    rows: List[Dict[str, Any]] = [record_to_dict(r) for r in records]

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        logging.warning("No records to write. Creating empty CSV: %s", path)
        path.write_text("", encoding="utf-8-sig")
        return

    fieldnames = list(rows[0].keys())

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    logging.info("CSV saved: %s", path.resolve())


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
        "headless=%s | workers=%d | limit_departments=%d",
        headless,
        args.workers,
        args.limit_departments,
    )

    records = crawl_all_parallel(
        headless=headless,
        workers=max(1, args.workers),
        limit_departments=max(0, args.limit_departments),
    )

    logging.info("crawl finished | records=%d", len(records))
    write_csv(records, args.output)


if __name__ == "__main__":
    main()
