import logging

from app.sync_faculty import sync_faculty


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    # 기존 데이터 포함 재크롤링 + 업데이트
    sync_faculty(
        db_path="faculty.db",
        workers=4,
        recrawl=True,
        headless=True,
    )


if __name__ == "__main__":
    main()