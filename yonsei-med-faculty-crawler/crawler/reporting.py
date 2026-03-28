import json
from collections import Counter
from pathlib import Path
from typing import List

from .models import FacultyRecord


def build_summary(records: List[FacultyRecord]):
    by_department = Counter()
    email_count = 0
    phone_count = 0
    for r in records:
        by_department[r.department_ko or r.department_en or "UNKNOWN"] += 1
        if r.email:
            email_count += 1
        if r.phone:
            phone_count += 1
    return {
        "total_records": len(records),
        "records_with_email": email_count,
        "records_with_phone": phone_count,
        "department_counts": dict(sorted(by_department.items()))
    }


def save_summary_json(records: List[FacultyRecord], path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    summary = build_summary(records)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def print_summary(records: List[FacultyRecord]):
    summary = build_summary(records)
    print("\n=== Crawl Summary ===")
    print(f"Total records      : {summary['total_records']}")
    print(f"Records with email : {summary['records_with_email']}")
    print(f"Records with phone : {summary['records_with_phone']}")
    print("Top departments    :")
    for dept, count in list(summary["department_counts"].items())[:10]:
        print(f"  - {dept}: {count}")
