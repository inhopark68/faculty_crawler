import re
import sqlite3
import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


DB_PATH = Path("output/yonsei_medicine_faculty.db")

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
TITLE_KO_RE = re.compile(r"(교수|부교수|조교수|명예교수|임상교수|연구교수|겸임교수|강사)")
NAME_KO_RE = re.compile(r"^[가-힣]{2,4}$")

NOISE_EXACT = {
    "본문 바로가기",
    "주메뉴 바로가기",
    "서브메뉴 바로가기",
    "연세대학교 교원정보 | Yonsei Faculty Information",
    "Yonsei Faculty Information",
    "통합검색",
    "통합검색 단어 입력",
    "Login",
    "Name",
    "Department",
    "개인정보처리방침",
    "법적고지",
    "논문",
    "학술활동",
    "저역서",
    "연구과제",
}

NOISE_PREFIXES = (
    "Yonsei University (",
    "COPYRIGHT (C)",
    "학술활동목록",
)

NOISE_CONTAINS = (
    "프로필사진",
    "논문 (Journal Article)",
    "저역서 (Publications)",
    "연구과제 (Research Project)",
    "지적재산권 (Intellectual Property)",
    "전시및작품활동 (Activities)",
    "수상 (Award)",
    "학술활동 (Conference Paper)",
)


def make_driver(headless: bool = True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,2000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    driver_path = ChromeDriverManager().install()
    if driver_path.endswith("THIRD_PARTY_NOTICES.chromedriver"):
        driver_path = driver_path.replace("THIRD_PARTY_NOTICES.chromedriver", "chromedriver.exe")
    service = Service(driver_path)
    driver = webdriver.Chrome(service=service, options=options)
    return driver


def clean_text(text: str) -> str:
    return " ".join(str(text or "").replace("\xa0", " ").split()).strip()


def normalize_email(text: str) -> str:
    m = EMAIL_RE.search(clean_text(text))
    return m.group(0).lower() if m else ""


def normalize_phone(text: str) -> str:
    text = clean_text(text)
    if not text:
        return ""
    m = re.search(r"(\+?\d[\d\-\(\) ]{6,}\d)", text)
    return clean_text(m.group(1)) if m else ""


def is_noise_line(line: str) -> bool:
    if not line:
        return True
    if line in NOISE_EXACT:
        return True
    if any(line.startswith(prefix) for prefix in NOISE_PREFIXES):
        return True
    if any(token in line for token in NOISE_CONTAINS):
        return True
    return False


def clean_profile_lines(soup: BeautifulSoup):
    lines = [clean_text(x) for x in soup.stripped_strings]
    return [line for line in lines if not is_noise_line(line)]


def extract_labeled(lines, label: str) -> str:
    prefix = f"{label} :"
    for line in lines:
        if line.startswith(prefix):
            return clean_text(line[len(prefix):])
    return ""


def extract_name_ko(lines):
    for line in lines[:20]:
        if NAME_KO_RE.fullmatch(line):
            return line
    return ""


def extract_name_en(lines):
    for line in lines[:20]:
        if "Campus" in line or "Department" in line or "Yonsei" in line:
            continue
        if EMAIL_RE.search(line):
            continue
        if re.fullmatch(r"[A-Z][a-z]+(?:[- ][A-Z][a-z]+){1,3}", line):
            return line
    return ""


def extract_title_ko(lines):
    for line in lines:
        m = TITLE_KO_RE.search(line)
        if m:
            return clean_text(m.group(1))
    return ""


def suspicious_row(row: sqlite3.Row) -> bool:
    name_ko = clean_text(row["name_ko"])
    name_en = clean_text(row["name_en"])
    title_ko = clean_text(row["title_ko"])
    office = clean_text(row["office"])

    if not row["detail_url"]:
        return False

    if not name_ko or len(name_ko) > 6 or "Campus" in name_ko or "Department" in name_ko:
        return True
    if name_en in {'"', 'Yonsei Faculty Information', 'Department', 'Name'}:
        return True
    if "Campus" in name_en or "Department of" in name_en:
        return True
    if "@" in title_ko or title_ko in {"논문", "학술활동", "Yonsei Faculty Information"}:
        return True
    if office in {"논문", "학술활동", "Yonsei Faculty Information"}:
        return True
    return False


def recrawl_detail(driver, detail_url: str):
    driver.get(detail_url)
    time.sleep(1.5)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    lines = clean_profile_lines(soup)

    return {
        "name_ko": extract_name_ko(lines),
        "name_en": extract_name_en(lines),
        "title_ko": extract_title_ko(lines),
        "email": normalize_email(extract_labeled(lines, "E-mail")),
        "phone": normalize_phone(extract_labeled(lines, "Tel")),
        "office": extract_labeled(lines, "Office"),
        "campus": extract_labeled(lines, "Campus"),
        "department_en": extract_labeled(lines, "Department"),
    }


def main():
    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT id, name_ko, name_en, title_ko, office, email, phone, campus, department_en, detail_url
        FROM faculty
        ORDER BY id
    """)
    rows = cur.fetchall()

    targets = [row for row in rows if suspicious_row(row)]
    print(f"suspicious rows: {len(targets)}")

    if not targets:
        conn.close()
        print("nothing to fix")
        return

    driver = make_driver(headless=True)
    fixed = 0
    try:
        for row in targets:
            detail_url = row["detail_url"]
            try:
                new_data = recrawl_detail(driver, detail_url)
                cur.execute("""
                    UPDATE faculty
                    SET name_ko = ?,
                        name_en = ?,
                        title_ko = ?,
                        email = CASE WHEN ? != '' THEN ? ELSE email END,
                        phone = CASE WHEN ? != '' THEN ? ELSE phone END,
                        office = ?,
                        campus = CASE WHEN ? != '' THEN ? ELSE campus END,
                        department_en = CASE WHEN ? != '' THEN ? ELSE department_en END
                    WHERE id = ?
                """, (
                    new_data["name_ko"],
                    new_data["name_en"],
                    new_data["title_ko"],
                    new_data["email"], new_data["email"],
                    new_data["phone"], new_data["phone"],
                    new_data["office"],
                    new_data["campus"], new_data["campus"],
                    new_data["department_en"], new_data["department_en"],
                    row["id"],
                ))
                fixed += 1
                print(f"fixed {row['id']}: {detail_url}")
            except Exception as e:
                print(f"failed {row['id']}: {detail_url} | {e}")
        conn.commit()
    finally:
        driver.quit()
        conn.close()

    print(f"done. fixed rows: {fixed}")


if __name__ == "__main__":
    main()
