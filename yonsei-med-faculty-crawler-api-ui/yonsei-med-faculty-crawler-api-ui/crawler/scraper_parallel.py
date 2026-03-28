import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

from .config import INDEX_URL, HEADLESS, PAGE_LOAD_SLEEP, DETAIL_PAGE_SLEEP, DETAIL_RETRY_COUNT
from .models import FacultyRecord
from .utils import (
    clean_text,
    normalize_email,
    normalize_phone,
    split_department_label,
    parse_name_line,
    extract_labeled_value,
    any_korean,
    any_english,
)


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
    driver.implicitly_wait(5)
    return driver


def get_page_soup(driver, url: str, sleep_sec: float) -> BeautifulSoup:
    driver.get(url)
    time.sleep(sleep_sec)
    return BeautifulSoup(driver.page_source, "html.parser")


def parse_index_for_medicine_departments(driver) -> List[Dict[str, str]]:
    soup = get_page_soup(driver, INDEX_URL, PAGE_LOAD_SLEEP)
    departments = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = clean_text(a.get_text(" ", strip=True))
        if not text:
            continue
        if "depMember.do" in href and "type=departMent" in href and "campus=sinchonMed" in href:
            full_url = urljoin(INDEX_URL, href)
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
    return departments


def enrich_record_from_detail(driver, record: FacultyRecord):
    if not record.detail_url:
        return
    last_error = None
    for _ in range(DETAIL_RETRY_COUNT):
        try:
            soup = get_page_soup(driver, record.detail_url, DETAIL_PAGE_SLEEP)
            text = clean_text(soup.get_text("\n", strip=True))
            detail_email = normalize_email(extract_labeled_value(text, "E-mail"))
            detail_tel = normalize_phone(extract_labeled_value(text, "Tel"))
            detail_office = extract_labeled_value(text, "Office")
            detail_campus = extract_labeled_value(text, "Campus")
            detail_dept = extract_labeled_value(text, "Department")
            if detail_email:
                record.email = detail_email
            if detail_tel:
                record.phone = detail_tel
            if detail_office:
                record.office = detail_office
            if detail_campus:
                record.campus = detail_campus
            if detail_dept and not record.department_en:
                record.department_en = detail_dept
            for line in [clean_text(x) for x in soup.stripped_strings]:
                if any_korean(line) and any_english(line):
                    nk, ne = parse_name_line(line)
                    if nk and not record.name_ko:
                        record.name_ko = nk
                    if ne and not record.name_en:
                        record.name_en = ne
                    break
            return
        except Exception as e:
            last_error = e
            time.sleep(1.0)
    if last_error:
        raise last_error


def parse_department_page(driver, dept_meta: Dict[str, str], existing_detail_urls: Optional[Set[str]] = None) -> List[FacultyRecord]:
    soup = get_page_soup(driver, dept_meta["department_url"], PAGE_LOAD_SLEEP)
    records = []
    seen_detail = set()
    existing_detail_urls = existing_detail_urls or set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "depMember.do" in href and "mode=view" in href and "userId=" in href:
            detail_url = urljoin(dept_meta["department_url"], href)
            if detail_url in seen_detail:
                continue
            seen_detail.add(detail_url)
            if detail_url in existing_detail_urls:
                logging.info("skip existing: %s", detail_url)
                continue
            parent_text = clean_text(a.parent.get_text("\n", strip=True)) if a.parent else ""
            lines = [clean_text(x) for x in parent_text.split("\n") if clean_text(x)]
            name_ko, name_en, title_ko, email, campus = "", "", "", "", ""
            for line in lines:
                if any_korean(line) and any_english(line):
                    nk, ne = parse_name_line(line)
                    if nk or ne:
                        name_ko, name_en = nk, ne
                        break
            for line in lines:
                if "@" in line:
                    email = normalize_email(line)
                if "/" in line and dept_meta["department_en"] in line:
                    title_ko = clean_text(line.split("/")[-1])
                if "Campus" in line:
                    campus = line
            rec = FacultyRecord(
                college_ko=dept_meta["college_ko"],
                college_en=dept_meta["college_en"],
                department_ko=dept_meta["department_ko"],
                department_en=dept_meta["department_en"],
                campus=campus,
                name_ko=name_ko,
                name_en=name_en,
                title_ko=title_ko,
                email=email,
                detail_url=detail_url,
                source_department_url=dept_meta["department_url"],
            )
            try:
                enrich_record_from_detail(driver, rec)
            except Exception as e:
                logging.warning("detail parse failed: %s | %s", detail_url, e)
            records.append(rec)
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
    logging.info("departments found: %d", len(departments))
    if not departments:
        return []
    chunks = chunk_departments(departments, workers)
    logging.info("parallel workers: %d | chunks: %d", workers, len(chunks))
    all_records: List[FacultyRecord] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [
            executor.submit(crawl_department_chunk, i + 1, chunk, headless, existing_detail_urls)
            for i, chunk in enumerate(chunks)
        ]
        for future in as_completed(futures):
            all_records.extend(future.result())
    return deduplicate(all_records)
