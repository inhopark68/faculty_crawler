import logging
import math
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from .config import INDEX_URL, HEADLESS, PAGE_LOAD_SLEEP, DETAIL_PAGE_SLEEP
from .models import FacultyRecord
from .utils import clean_text, normalize_email, normalize_phone, split_department_label


EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
TITLE_KO_RE = re.compile(r"(교수|부교수|조교수|명예교수|임상교수|연구교수|겸임교수|강사)")
NAME_KO_RE = re.compile(r"^[가-힣]{2,4}$")
NAME_EN_RE = re.compile(r"^[A-Z][a-z]+(?:[- ][A-Z][a-z]+){1,3}$")

NOISE_LINES = {
    "", "Login", "Name", "Department", "more +",
    "논문", "학술활동", "저역서", "연구과제",
    "Yonsei Faculty Information", "연세대학교 교원정보 | Yonsei Faculty Information",
    "통합검색", "통합검색 단어 입력", "본문 바로가기", "주메뉴 바로가기", "서브메뉴 바로가기",
    "개인정보처리방침", "법적고지", "교원정보",
}


def make_driver(headless: bool = HEADLESS):
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
    driver.implicitly_wait(3)
    return driver


def wait_document_ready(driver, timeout: int = 15):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def _extract_labeled(lines: List[str], label: str) -> str:
    prefix = f"{label} :"
    for line in lines:
        if line.startswith(prefix):
            return clean_text(line[len(prefix):])
    return ""


def _clean_lines(lines: List[str]) -> List[str]:
    out = []
    seen = set()
    for line in lines:
        line = clean_text(line)
        if not line or line in NOISE_LINES:
            continue
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def _snapshot_anchors(driver) -> List[Dict[str, str]]:
    items = []
    for a in driver.find_elements(By.TAG_NAME, "a"):
        try:
            href = clean_text(a.get_attribute("href") or "")
            text = clean_text(a.text or "")
            if href or text:
                items.append({"href": href, "text": text})
        except Exception:
            continue
    return items


def parse_index_for_medicine_departments(driver) -> List[Dict[str, str]]:
    driver.get(INDEX_URL)
    wait_document_ready(driver, timeout=15)
    time.sleep(PAGE_LOAD_SLEEP)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    departments = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = clean_text(a.get_text(" ", strip=True))
        if not text:
            continue

        if "depMember.do" in href and "type=departMent" in href and "campus=sinchonMed" in href:
            full_url = urljoin(driver.current_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)

            dept_ko, dept_en = split_department_label(text)
            departments.append({
                "college_ko": "의과대학",
                "college_en": "College of Medicine",
                "department_ko": dept_ko,
                "department_en": dept_en,
                "department_url": full_url,
            })

    logging.info("medicine departments parsed: %d", len(departments))
    return departments


def parse_department_page(driver, dept_meta: Dict[str, str], existing_detail_urls: Optional[Set[str]] = None) -> List[FacultyRecord]:
    driver.get(dept_meta["department_url"])
    wait_document_ready(driver, timeout=15)
    time.sleep(PAGE_LOAD_SLEEP)

    existing_detail_urls = existing_detail_urls or set()
    anchors = _snapshot_anchors(driver)

    logging.info("anchor snapshot size: %d", len(anchors))
    if anchors:
        logging.info("anchor sample: %s", anchors[:20])

    members: Dict[str, Dict[str, str]] = {}
    current_detail = None

    for item in anchors:
        href = item["href"]
        text = item["text"]

        if "depMember.do?mode=view" in href:
            current_detail = href
            if current_detail not in members:
                members[current_detail] = {
                    "detail_url": current_detail,
                    "name_ko": "",
                    "name_en": "",
                    "title_ko": "",
                    "email": "",
                }

            # Sometimes the name itself is on the same detail link anchor.
            if NAME_KO_RE.fullmatch(text) and text not in NOISE_LINES:
                members[current_detail]["name_ko"] = text
            elif NAME_EN_RE.fullmatch(text):
                members[current_detail]["name_en"] = text

            m = TITLE_KO_RE.search(text)
            if m and not members[current_detail]["title_ko"]:
                members[current_detail]["title_ko"] = clean_text(m.group(1))
            continue

        if not current_detail:
            continue

        if NAME_KO_RE.fullmatch(text) and text not in NOISE_LINES and not members[current_detail]["name_ko"]:
            members[current_detail]["name_ko"] = text
            continue

        if NAME_EN_RE.fullmatch(text) and not members[current_detail]["name_en"]:
            members[current_detail]["name_en"] = text
            continue

        m = TITLE_KO_RE.search(text)
        if m and not members[current_detail]["title_ko"]:
            members[current_detail]["title_ko"] = clean_text(m.group(1))
            continue

        if href.startswith("mailto:"):
            email = normalize_email(href.replace("mailto:", ""))
            if email and not members[current_detail]["email"]:
                members[current_detail]["email"] = email

    logging.info("members collected: %d", len(members))
    if members:
        logging.info("member sample: %s", list(members.values())[:5])

    records: List[FacultyRecord] = []
    for detail_url, data in members.items():
        if detail_url in existing_detail_urls:
            continue

        detail_email = ""
        detail_phone = ""
        detail_office = ""
        detail_campus = ""
        detail_department_en = ""

        try:
            driver.get(detail_url)
            wait_document_ready(driver, timeout=15)
            time.sleep(DETAIL_PAGE_SLEEP)

            soup = BeautifulSoup(driver.page_source, "html.parser")
            lines = _clean_lines([clean_text(x) for x in soup.stripped_strings])

            detail_email = normalize_email(_extract_labeled(lines, "E-mail"))
            detail_phone = normalize_phone(_extract_labeled(lines, "Tel"))
            detail_office = _extract_labeled(lines, "Office")
            detail_campus = _extract_labeled(lines, "Campus")
            detail_department_en = _extract_labeled(lines, "Department")
        except Exception as e:
            logging.warning("detail parse failed: %s | %s", detail_url, e)

        rec = FacultyRecord(
            college_ko=dept_meta["college_ko"],
            college_en=dept_meta["college_en"],
            department_ko=dept_meta["department_ko"],
            department_en=detail_department_en or dept_meta["department_en"],
            campus=detail_campus,
            name_ko=data["name_ko"],
            name_en=data["name_en"],
            title_ko=data["title_ko"],
            email=detail_email or data["email"],
            phone=detail_phone,
            office=detail_office,
            detail_url=detail_url,
            source_department_url=dept_meta["department_url"],
        )
        records.append(rec)

    logging.info(
        "department result: %s | detail links=%d | new records=%d",
        dept_meta["department_ko"],
        len(members),
        len(records),
    )
    return records


def deduplicate(records: List[FacultyRecord]) -> List[FacultyRecord]:
    result = {}
    for r in records:
        key = (
            clean_text(r.name_ko),
            clean_text(r.name_en).upper(),
            clean_text(r.department_en).upper(),
            normalize_email(r.email),
            clean_text(r.detail_url),
        )
        result[key] = r
    return list(result.values())


def chunk_departments(departments: List[Dict[str, str]], workers: int) -> List[List[Dict[str, str]]]:
    workers = max(1, workers)
    chunk_size = max(1, math.ceil(len(departments) / workers))
    return [departments[i:i + chunk_size] for i in range(0, len(departments), chunk_size)]


def crawl_department_chunk(chunk_id: int, departments: List[Dict[str, str]], headless: bool, existing_detail_urls: Optional[Set[str]] = None) -> List[FacultyRecord]:
    driver = make_driver(headless=headless)
    try:
        records: List[FacultyRecord] = []
        for idx, dept in enumerate(departments, start=1):
            logging.info("[worker %d] [%d/%d] %s / %s", chunk_id, idx, len(departments), dept["department_ko"], dept["department_en"])
            try:
                dept_records = parse_department_page(driver, dept, existing_detail_urls=existing_detail_urls)
                records.extend(dept_records)
            except Exception as e:
                logging.warning("[worker %d] department failed: %s | %s", chunk_id, dept["department_url"], e)
        return records
    finally:
        driver.quit()


def crawl_all_parallel(headless: bool = HEADLESS, workers: int = 4, existing_detail_urls: Optional[Set[str]] = None, limit_departments: int = 0) -> List[FacultyRecord]:
    bootstrap_driver = make_driver(headless=headless)
    try:
        departments = parse_index_for_medicine_departments(bootstrap_driver)
    finally:
        bootstrap_driver.quit()

    if limit_departments > 0:
        departments = departments[:limit_departments]

    if not departments:
        return []

    chunks = chunk_departments(departments, workers)
    all_records: List[FacultyRecord] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [
            executor.submit(crawl_department_chunk, i + 1, chunk, headless, existing_detail_urls)
            for i, chunk in enumerate(chunks)
        ]
        for future in as_completed(futures):
            all_records.extend(future.result())

    return deduplicate(all_records)
