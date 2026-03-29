import logging
from pathlib import Path

from app.sync_faculty import sync_faculty
from app.database import connect_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def main():
    db_path = Path("./output/yonsei_medicine_faculty_test.db")

    print(f"[1] sync start: {db_path}")
    sync_faculty(
        db_path=str(db_path),
        workers=1,
        recrawl=True,
        headless=True,
        limit_departments=1,
        retries=2,
        wait_timeout=20,
        enable_external_enrichment=False,
    )

    print("[2] open db")
    conn = connect_db(db_path)
    try:
        cur = conn.cursor()

        print("[3] schema check")
        cols = cur.execute("PRAGMA table_info(faculty)").fetchall()
        col_names = [c[1] for c in cols]
        required = [
            "orcid_id",
            "orcid_url",
            "external_source_url",
        ]
        for name in required:
            print(f"  - {name}: {'OK' if name in col_names else 'MISSING'}")

        print("[4] row counts")
        total = cur.execute("SELECT COUNT(*) FROM faculty").fetchone()[0]
        with_email = cur.execute("SELECT COUNT(*) FROM faculty WHERE email IS NOT NULL AND TRIM(email) != ''").fetchone()[0]
        with_phone = cur.execute("SELECT COUNT(*) FROM faculty WHERE phone IS NOT NULL AND TRIM(phone) != ''").fetchone()[0]
        with_office = cur.execute("SELECT COUNT(*) FROM faculty WHERE office IS NOT NULL AND TRIM(office) != ''").fetchone()[0]
        with_orcid = cur.execute("SELECT COUNT(*) FROM faculty WHERE orcid_id IS NOT NULL AND TRIM(orcid_id) != ''").fetchone()[0]
        with_external = cur.execute("SELECT COUNT(*) FROM faculty WHERE external_source_url IS NOT NULL AND TRIM(external_source_url) != ''").fetchone()[0]

        print(f"  - total: {total}")
        print(f"  - with email: {with_email}")
        print(f"  - with phone: {with_phone}")
        print(f"  - with office: {with_office}")
        print(f"  - with orcid: {with_orcid}")
        print(f"  - with external_source_url: {with_external}")

    finally:
        conn.close()

    print("[done]")


if __name__ == "__main__":
    main()