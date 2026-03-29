import json
import logging
import math
import re
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import quote_plus, urljoin, urlparse

import requests
from requests import Session
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from . import config as app_config
from .models import FacultyRecord
from .utils import clean_text, normalize_email, normalize_phone, split_department_label

INDEX_URL = getattr(app_config, "INDEX_URL", "")
HEADLESS = getattr(app_config, "HEADLESS", True)

CONFIG_ORCID_PATH = Path(__file__).resolve().parents[1] / "config_orcid.json"

EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(r"\d{2,4}-\d{3,4}-\d{4}")
ORCID_URL_RE = re.compile(r"https?://orcid\.org/(\d{4}-\d{4}-\d{4}-\d{3}[0-9X])", re.I)
ORCID_ID_RE = re.compile(r"\b(\d{4}-\d{4}-\d{4}-\d{3}[0-9X])\b", re.I)

NAME_KO_INLINE_RE = re.compile(r"([가-힣]{2,4})")
NAME_EN_INLINE_RE = re.compile(r"([A-Z][a-z]+(?:[- ][A-Z][a-z]+){1,3})")

KOR_TITLE_RE = re.compile(r"(명예교수|임상교수|연구교수|겸임교수|부교수|조교수|교수|강사)")
ENG_TITLE_PATTERNS = [
    (re.compile(r"\bEmeritus Professor\b", re.I), "명예교수"),
    (re.compile(r"\bClinical Professor\b", re.I), "임상교수"),
    (re.compile(r"\bResearch Professor\b", re.I), "연구교수"),
    (re.compile(r"\bAdjunct Professor\b", re.I), "겸임교수"),
    (re.compile(r"\bAssociate Professor\b", re.I), "부교수"),
    (re.compile(r"\bAssistant Professor\b", re.I), "조교수"),
    (re.compile(r"\bProfessor\b", re.I), "교수"),
    (re.compile(r"\bLecturer\b", re.I), "강사"),
]

NOISE_LINES = {
    "", "Login", "Name", "Department", "more +",
    "논문", "학술활동", "저역서", "연구과제",
    "Yonsei Faculty Information", "연세대학교 교원정보 | Yonsei Faculty Information",
    "통합검색", "통합검색 단어 입력", "본문 바로가기", "주메뉴 바로가기", "서브메뉴 바로가기",
    "개인정보처리방침", "법적고지", "교원정보",
}

DEBUG_DIR = Path(__file__).resolve().parents[1] / "debug"


EXTERNAL_PROFILE_SOURCES = getattr(app_config, "EXTERNAL_PROFILE_SOURCES", [
    {"name": "yonsei_medicine", "base_url": "https://medicine.yonsei.ac.kr"},
    {"name": "yonsei_health_system", "base_url": "https://www.yuhs.or.kr"},
    {"name": "severance_hospital", "base_url": "https://sev.iseverance.com"},
])
EXTERNAL_SEARCH_PATHS = getattr(app_config, "EXTERNAL_SEARCH_PATHS", [
    "/search/search.do?query={query}",
    "/search/search.do?searchWord={query}",
    "/search?query={query}",
    "/search?keyword={query}",
    "/?s={query}",
])
EXTERNAL_SOURCE_TIMEOUT = getattr(app_config, "EXTERNAL_SOURCE_TIMEOUT", 12)
EXTERNAL_SOURCE_MAX_PAGES = getattr(app_config, "EXTERNAL_SOURCE_MAX_PAGES", 8)



class CrawlCancelled(Exception):
    pass


class CrawlProgress:
    def __init__(
        self,
        total_departments: int,
        progress_callback: Optional[Callable[[int, str], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ):
        self.total_departments = max(1, total_departments)
        self.done_departments = 0
        self.failed_departments = 0
        self.total_records = 0
        self.lock = threading.Lock()
        self.start_ts = time.time()
        self.progress_callback = progress_callback
        self.cancel_check = cancel_check

    def check_cancelled(self):
        if self.cancel_check and self.cancel_check():
            raise CrawlCancelled("사용자 요청으로 중단되었습니다.")

    def emit(self, percent: int, message: str):
        if self.progress_callback:
            try:
                self.progress_callback(max(0, min(100, int(percent))), message)
            except Exception:
                pass

    def department_done(self, dept_name: str, new_records: int, failed: bool = False):
        with self.lock:
            self.done_departments += 1
            self.total_records += new_records
            if failed:
                self.failed_departments += 1

            raw_percent = (self.done_departments / self.total_departments) * 100
            ui_percent = 20 + int(raw_percent * 0.65)

            elapsed = time.time() - self.start_ts
            message = (
                f"{dept_name} 완료 | {self.done_departments}/{self.total_departments} "
                f"| 누적 {self.total_records}건 | 실패 {self.failed_departments}"
            )

            logging.info(
                "[PROGRESS] %.1f%% (%d/%d) | 완료학과=%s | 누적레코드=%d | 실패=%d | 경과=%.1fs",
                raw_percent,
                self.done_departments,
                self.total_departments,
                dept_name,
                self.total_records,
                self.failed_departments,
                elapsed,
            )
            self.emit(ui_percent, message)


def make_http_session() -> Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ko,en-US;q=0.9,en;q=0.8",
    })
    return session


def _same_domain(url: str, base_url: str) -> bool:
    try:
        return urlparse(url).netloc.endswith(urlparse(base_url).netloc)
    except Exception:
        return False


def _extract_name_en_fallback(lines: List[str]) -> str:
    for line in lines:
        m = NAME_EN_INLINE_RE.search(line)
        if m:
            return clean_text(m.group(1))
    return ""


def _tokens_for_external_match(name_ko: str, name_en: str, department_ko: str, department_en: str, email: str) -> List[str]:
    tokens = []
    for value in [name_ko, name_en, department_ko, department_en, email]:
        value = clean_text(value)
        if value:
            tokens.append(value)
    return list(dict.fromkeys(tokens))


def _page_identity_score(text: str, name_ko: str, name_en: str, email: str, department_ko: str, department_en: str) -> int:
    text = text or ""
    score = 0
    if name_ko and name_ko in text:
        score += 60
    if name_en and _normalize_name_for_match(name_en) and _normalize_name_for_match(name_en) in _normalize_name_for_match(text):
        score += 60
    if email and normalize_email(email) and normalize_email(email) in normalize_email(text):
        score += 120
    if department_ko and department_ko in text:
        score += 20
    if department_en and department_en.lower() in text.lower():
        score += 20
    return score


def _collect_external_candidate_urls(session: Session, source: Dict[str, str], queries: List[str], max_urls: int = EXTERNAL_SOURCE_MAX_PAGES) -> List[str]:
    base_url = source.get("base_url", "").rstrip("/")
    if not base_url:
        return []

    candidates = [base_url]
    seen = {base_url}

    for q in queries[:3]:
        encoded = quote_plus(q)
        for path in EXTERNAL_SEARCH_PATHS:
            search_url = urljoin(base_url + "/", path.format(query=encoded).lstrip("/"))
            try:
                resp = session.get(search_url, timeout=EXTERNAL_SOURCE_TIMEOUT)
                if resp.status_code >= 400:
                    continue
                soup = BeautifulSoup(resp.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    href = urljoin(search_url, a.get("href", ""))
                    text = clean_text(a.get_text(" ", strip=True))
                    blob = f"{href} {text}"
                    if not _same_domain(href, base_url):
                        continue
                    if not any(token.lower() in blob.lower() for token in queries if token):
                        continue
                    if href not in seen:
                        seen.add(href)
                        candidates.append(href)
                    if len(candidates) >= max_urls:
                        return candidates
            except Exception:
                continue

    try:
        resp = session.get(base_url, timeout=EXTERNAL_SOURCE_TIMEOUT)
        if resp.status_code < 400:
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = urljoin(base_url + "/", a.get("href", ""))
                text = clean_text(a.get_text(" ", strip=True))
                blob = f"{href} {text}"
                if not _same_domain(href, base_url):
                    continue
                if not any(keyword in blob.lower() for keyword in ["prof", "faculty", "doctor", "staff", "people", "교수", "의료진", "진료"]):
                    continue
                if href not in seen:
                    seen.add(href)
                    candidates.append(href)
                if len(candidates) >= max_urls:
                    break
    except Exception:
        pass

    return candidates[:max_urls]


def _parse_external_profile_html(html: str) -> Dict[str, str]:
    soup = BeautifulSoup(html or "", "html.parser")
    lines = _clean_lines([clean_text(x) for x in soup.stripped_strings])
    email = _extract_email_fallback(html or "", lines)
    phone = _extract_phone_fallback(lines)
    office = _extract_labeled(lines, "Office") or _extract_office_fallback(lines)
    title_ko = ""
    for line in lines:
        title_ko = _extract_title_ko(line)
        if title_ko:
            break
    return {
        "name_en": _extract_name_en_fallback(lines),
        "email": email,
        "phone": phone,
        "office": office,
        "title_ko": title_ko,
        "orcid_id": _extract_orcid_from_text(html or "")[0],
        "orcid_url": _extract_orcid_from_text(html or "")[1],
    }


def enrich_from_external_sources(
    record: FacultyRecord,
    dept_meta: Dict[str, str],
    session: Optional[Session] = None,
    orcid_token: str = "",
) -> FacultyRecord:
    missing = [
        not getattr(record, "name_en", ""),
        not getattr(record, "email", ""),
        not getattr(record, "title_ko", ""),
        not getattr(record, "phone", ""),
        not getattr(record, "office", ""),
        not getattr(record, "orcid_id", ""),
    ]
    if not any(missing):
        return record

    own_session = False
    if session is None:
        session = make_http_session()
        own_session = True

    best_score = -1
    best_data: Dict[str, str] = {}
    queries = _tokens_for_external_match(
        getattr(record, "name_ko", ""),
        getattr(record, "name_en", ""),
        dept_meta.get("department_ko", ""),
        getattr(record, "department_en", "") or dept_meta.get("department_en", ""),
        getattr(record, "email", ""),
    )

    try:
        for source in EXTERNAL_PROFILE_SOURCES:
            for candidate_url in _collect_external_candidate_urls(session, source, queries):
                try:
                    resp = session.get(candidate_url, timeout=EXTERNAL_SOURCE_TIMEOUT)
                    if resp.status_code >= 400:
                        continue
                    html = resp.text or ""
                    page_score = _page_identity_score(
                        html,
                        getattr(record, "name_ko", ""),
                        getattr(record, "name_en", ""),
                        getattr(record, "email", ""),
                        dept_meta.get("department_ko", ""),
                        getattr(record, "department_en", "") or dept_meta.get("department_en", ""),
                    )
                    if page_score < 60:
                        continue
                    parsed = _parse_external_profile_html(html)
                    parsed["source_url"] = candidate_url
                    if page_score > best_score:
                        best_score = page_score
                        best_data = parsed
                except Exception:
                    continue

        if best_data:
            if not getattr(record, "name_en", "") and best_data.get("name_en"):
                record.name_en = best_data["name_en"]
            if not getattr(record, "email", "") and best_data.get("email"):
                record.email = normalize_email(best_data["email"])
            if not getattr(record, "title_ko", "") and best_data.get("title_ko"):
                record.title_ko = best_data["title_ko"]
            if not getattr(record, "phone", "") and best_data.get("phone"):
                record.phone = normalize_phone(best_data["phone"])
            if not getattr(record, "office", "") and best_data.get("office"):
                record.office = best_data["office"]
            if not getattr(record, "orcid_id", "") and best_data.get("orcid_id"):
                setattr(record, "orcid_id", best_data["orcid_id"])
                setattr(record, "orcid_url", best_data.get("orcid_url", ""))

        if not getattr(record, "orcid_id", ""):
            orcid_id, orcid_url = search_orcid_by_api(
                name_ko=getattr(record, "name_ko", ""),
                name_en=getattr(record, "name_en", ""),
                email=getattr(record, "email", ""),
                department_en=getattr(record, "department_en", "") or dept_meta.get("department_en", ""),
                token=orcid_token,
            )
            if orcid_id:
                setattr(record, "orcid_id", orcid_id)
                setattr(record, "orcid_url", orcid_url)
    finally:
        if own_session:
            session.close()

    return record


def load_orcid_config() -> dict:
    if not CONFIG_ORCID_PATH.exists():
        return {}
    try:
        with open(CONFIG_ORCID_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_orcid_access_token() -> str:
    cfg = load_orcid_config()
    client_id = cfg.get("client_id", "")
    client_secret = cfg.get("client_secret", "")
    token = cfg.get("token", "")

    if token:
        return token

    if not client_id or not client_secret:
        return ""

    try:
        resp = requests.post(
            "https://orcid.org/oauth/token",
            headers={"Accept": "application/json"},
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": "/read-public",
            },
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("access_token", "")
    except Exception as e:
        logging.warning("ORCID token fetch failed: %r", e)
        return ""


def _normalize_name_for_match(name: str) -> str:
    return re.sub(r"[^A-Za-z]", "", (name or "").strip()).lower()


def _extract_orcid_from_text(text: str) -> Tuple[str, str]:
    text = text or ""

    m = ORCID_URL_RE.search(text)
    if m:
        oid = m.group(1)
        return oid, f"https://orcid.org/{oid}"

    m = ORCID_ID_RE.search(text)
    if m:
        oid = m.group(1)
        return oid, f"https://orcid.org/{oid}"

    return "", ""


def _extract_orcid_from_page(driver, soup: BeautifulSoup, lines: List[str]) -> Tuple[str, str]:
    html = driver.page_source or ""

    oid, url = _extract_orcid_from_text(html)
    if oid:
        return oid, url

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        oid, url = _extract_orcid_from_text(href)
        if oid:
            return oid, url

    for line in lines:
        oid, url = _extract_orcid_from_text(line)
        if oid:
            return oid, url

    return "", ""


def _score_orcid_candidate(candidate: dict, name_en: str, email: str, department_en: str) -> int:
    score = 0
    name_norm = _normalize_name_for_match(name_en)
    email_norm = normalize_email(email)

    person = candidate.get("person", {}) if isinstance(candidate, dict) else {}
    emails = person.get("emails", {}).get("email", []) if isinstance(person, dict) else []
    names = person.get("name", {}) if isinstance(person, dict) else {}
    activities = candidate.get("activities-summary", {}) if isinstance(candidate, dict) else {}

    given = names.get("given-names", {}).get("value", "") if isinstance(names, dict) else ""
    family = names.get("family-name", {}).get("value", "") if isinstance(names, dict) else ""
    candidate_name_norm = _normalize_name_for_match(f"{given} {family}")

    if name_norm and candidate_name_norm and name_norm == candidate_name_norm:
        score += 60

    for item in emails:
        cand_email = normalize_email(item.get("email", ""))
        if email_norm and cand_email and email_norm == cand_email:
            score += 100
            break

    dept_norm = (department_en or "").strip().lower()
    if dept_norm:
        aff_text = str(activities).lower()
        if dept_norm in aff_text:
            score += 30

    return score


def search_orcid_by_api(name_ko: str, name_en: str, email: str = "", department_en: str = "", token: str = "") -> Tuple[str, str]:
    if not token:
        return "", ""

    query_parts = []

    if name_en:
        query_parts.append(f'given-and-family-names:"{name_en}"')
    elif name_ko:
        query_parts.append(f'text:"{name_ko}"')

    if email:
        query_parts.append(f'email:"{email}"')

    if department_en:
        query_parts.append(f'affiliation-org-name:"{department_en}"')

    if not query_parts:
        return "", ""

    query = " AND ".join(query_parts)

    try:
        resp = requests.get(
            "https://pub.orcid.org/v3.0/search/",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
            params={"q": query},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result", [])
        if not results:
            return "", ""

        best_id = ""
        best_score = -1

        for item in results[:5]:
            oid = (
                item.get("orcid-identifier", {}).get("path")
                or item.get("orcid-id")
                or ""
            )
            if not oid:
                continue

            try:
                detail_resp = requests.get(
                    f"https://pub.orcid.org/v3.0/{oid}",
                    headers={
                        "Accept": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                    timeout=20,
                )
                detail_resp.raise_for_status()
                detail = detail_resp.json()
                score = _score_orcid_candidate(detail, name_en, email, department_en)
                if score > best_score:
                    best_score = score
                    best_id = oid
            except Exception:
                continue

        if best_id and best_score >= 60:
            return best_id, f"https://orcid.org/{best_id}"

        return "", ""
    except Exception as e:
        logging.warning("ORCID search failed: %r", e)
        return "", ""


def make_driver(headless: bool = HEADLESS):
    options = Options()
    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1400,2000")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_argument("--log-level=3")
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
    driver.set_page_load_timeout(40)
    driver.set_script_timeout(40)
    return driver


def wait_document_ready(driver, timeout: int = 15):
    WebDriverWait(driver, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def safe_get(driver, url: str, retries: int = 2, wait_timeout: int = 12):
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            logging.info("safe_get attempt %d/%d: %s", attempt, retries, url)
            driver.get(url)
            wait_document_ready(driver, timeout=wait_timeout)
            return
        except Exception as e:
            last_error = e
            logging.warning("safe_get failed %d/%d: %s | %r", attempt, retries, url, e)
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
            time.sleep(1.5)

    raise last_error


def _extract_labeled(lines: List[str], label: str) -> str:
    prefix = f"{label} :"
    for line in lines:
        if line.startswith(prefix):
            return clean_text(line[len(prefix):])
    return ""


def _clean_lines(lines: List[str]) -> List[str]:
    out, seen = [], set()
    for line in lines:
        line = clean_text(line)
        if not line or line in NOISE_LINES:
            continue
        if line not in seen:
            seen.add(line)
            out.append(line)
    return out


def _extract_title_ko(text: str) -> str:
    text = clean_text(text)
    m = KOR_TITLE_RE.search(text)
    if m:
        return clean_text(m.group(1))
    for pattern, mapped in ENG_TITLE_PATTERNS:
        if pattern.search(text):
            return mapped
    return ""


def _parse_inline_fields(text: str) -> Dict[str, str]:
    text = clean_text(text)
    name_ko = name_en = title_ko = email = ""

    if text and text not in NOISE_LINES:
        m = NAME_KO_INLINE_RE.search(text)
        if m:
            candidate = clean_text(m.group(1))
            if candidate not in NOISE_LINES:
                name_ko = candidate

        m = NAME_EN_INLINE_RE.search(text)
        if m:
            name_en = clean_text(m.group(1))

        title_ko = _extract_title_ko(text)

        m = EMAIL_RE.search(text)
        if m:
            email = normalize_email(m.group(0))

    return {
        "name_ko": name_ko,
        "name_en": name_en,
        "title_ko": title_ko,
        "email": email,
    }


def _snapshot_anchors(driver):
    items = []
    current_url = driver.current_url

    for a in driver.find_elements(By.TAG_NAME, "a"):
        try:
            raw_href = clean_text(a.get_attribute("href") or "")
            href = urljoin(current_url, raw_href) if raw_href else ""
            text = clean_text(a.text or "")
            if href or text:
                items.append({"href": href, "text": text})
        except Exception:
            continue
    return items


def _save_debug_html(filename: str, html: str):
    try:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_DIR / filename, "w", encoding="utf-8") as f:
            f.write(html)
    except Exception:
        pass


def _extract_phone_fallback(lines: List[str]) -> str:
    for line in lines:
        m = PHONE_RE.search(line)
        if m:
            return normalize_phone(m.group(0))
    return ""


def _extract_office_fallback(lines: List[str]) -> str:
    for line in lines:
        if any(keyword in line for keyword in ["호", "Room", "Building", "센터", "관", "연구실"]):
            return clean_text(line)
    return ""


def _extract_email_fallback(html: str, lines: List[str]) -> str:
    emails = EMAIL_RE.findall(html or "")
    if emails:
        return normalize_email(emails[0])

    for line in lines:
        emails = EMAIL_RE.findall(line)
        if emails:
            return normalize_email(emails[0])

    return ""


def parse_index_for_medicine_departments(driver, retries: int = 2, wait_timeout: int = 12):
    safe_get(driver, INDEX_URL, retries=retries, wait_timeout=wait_timeout)

    soup = BeautifulSoup(driver.page_source, "html.parser")
    departments, seen = [], set()

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


def parse_department_page(
    driver,
    dept_meta: Dict[str, str],
    existing_detail_urls: Optional[Set[str]] = None,
    retries: int = 2,
    wait_timeout: int = 12,
    recrawl: bool = False,
    cancel_check: Optional[Callable[[], bool]] = None,
    detail_progress_callback: Optional[Callable[[str], None]] = None,
    orcid_token: str = "",
):
    existing_detail_urls = existing_detail_urls or set()

    if cancel_check and cancel_check():
        raise CrawlCancelled("사용자 요청으로 중단되었습니다.")

    safe_get(
        driver,
        dept_meta["department_url"],
        retries=retries,
        wait_timeout=wait_timeout,
    )

    WebDriverWait(driver, max(20, wait_timeout)).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    WebDriverWait(driver, max(20, wait_timeout)).until(
        lambda d: len(d.find_elements(By.TAG_NAME, "a")) > 10
    )

    time.sleep(1)

    anchors = _snapshot_anchors(driver)

    detail_candidates = [
        a for a in anchors
        if "depMember.do" in a["href"] and "mode=view" in a["href"]
    ]

    if not detail_candidates:
        logging.warning("no detail links found: %s", dept_meta["department_url"])
        _save_debug_html("last_department_page.html", driver.page_source)
        return []

    members = {}
    current_detail = None

    for item in anchors:
        href = item["href"]
        text = item["text"]

        if "depMember.do" in href and "mode=view" in href:
            current_detail = href

            if current_detail not in members:
                members[current_detail] = {
                    "detail_url": current_detail,
                    "name_ko": "",
                    "name_en": "",
                    "title_ko": "",
                    "email": "",
                }

            parsed = _parse_inline_fields(text)
            for k, v in parsed.items():
                if v and not members[current_detail][k]:
                    members[current_detail][k] = v
            continue

        if not current_detail:
            continue

        parsed = _parse_inline_fields(text)
        for k, v in parsed.items():
            if v and not members[current_detail][k]:
                members[current_detail][k] = v

        if href.startswith("mailto:"):
            email = normalize_email(href.replace("mailto:", ""))
            if email and not members[current_detail]["email"]:
                members[current_detail]["email"] = email

    records = []

    total_members = len(members)
    for member_idx, (detail_url, data) in enumerate(members.items(), start=1):
        if cancel_check and cancel_check():
            raise CrawlCancelled("사용자 요청으로 중단되었습니다.")

        detail_msg = f"{dept_meta['department_ko']} 상세 {member_idx}/{total_members}"
        logging.info("[DETAIL] %s (%d/%d)", dept_meta["department_ko"], member_idx, total_members)

        if detail_progress_callback:
            try:
                detail_progress_callback(detail_msg)
            except Exception:
                pass

        if (not recrawl) and detail_url in existing_detail_urls:
            logging.info("skip existing detail_url: %s", detail_url)
            continue

        detail_email = ""
        detail_phone = ""
        detail_office = ""
        detail_campus = ""
        detail_department_en = ""
        detail_title_ko = ""
        detail_orcid_id = ""
        detail_orcid_url = ""

        try:
            safe_get(
                driver,
                detail_url,
                retries=retries,
                wait_timeout=wait_timeout,
            )

            soup = BeautifulSoup(driver.page_source, "html.parser")
            html = driver.page_source or ""
            lines = _clean_lines([clean_text(x) for x in soup.stripped_strings])

            detail_email = normalize_email(_extract_labeled(lines, "E-mail"))
            detail_phone = normalize_phone(_extract_labeled(lines, "Tel"))
            detail_office = _extract_labeled(lines, "Office")
            detail_campus = _extract_labeled(lines, "Campus")
            detail_department_en = _extract_labeled(lines, "Department")

            if not detail_email:
                detail_email = _extract_email_fallback(html, lines)

            if not detail_phone:
                detail_phone = _extract_phone_fallback(lines)

            if not detail_office:
                detail_office = _extract_office_fallback(lines)

            for line in lines:
                detail_title_ko = _extract_title_ko(line)
                if detail_title_ko:
                    break

            detail_orcid_id, detail_orcid_url = _extract_orcid_from_page(driver, soup, lines)

            if not detail_orcid_id:
                detail_orcid_id, detail_orcid_url = search_orcid_by_api(
                    name_ko=data["name_ko"],
                    name_en=data["name_en"],
                    email=detail_email or data["email"],
                    department_en=detail_department_en or dept_meta["department_en"],
                    token=orcid_token,
                )

        except Exception as e:
            logging.warning("detail parse failed: %s | %r", detail_url, e)
            logging.warning(traceback.format_exc())
            _save_debug_html("last_detail_page.html", driver.page_source)

        record = FacultyRecord(
            college_ko=dept_meta["college_ko"],
            college_en=dept_meta["college_en"],
            department_ko=dept_meta["department_ko"],
            department_en=detail_department_en or dept_meta["department_en"],
            campus=detail_campus,
            name_ko=data["name_ko"],
            name_en=data["name_en"],
            title_ko=data["title_ko"] or detail_title_ko,
            email=detail_email or data["email"],
            phone=detail_phone,
            office=detail_office,
            detail_url=detail_url,
            source_department_url=dept_meta["department_url"],
        )

        try:
            setattr(record, "orcid_id", detail_orcid_id)
            setattr(record, "orcid_url", detail_orcid_url)
        except Exception:
            pass

        try:
            record = enrich_from_external_sources(
                record,
                dept_meta={
                    **dept_meta,
                    "department_en": detail_department_en or dept_meta["department_en"],
                },
                orcid_token=orcid_token,
            )
        except Exception as e:
            logging.warning("external enrichment failed: %s | %r", detail_url, e)

        records.append(record)

    logging.info(
        "department result: %s | detail links=%d | records=%d",
        dept_meta["department_ko"],
        len(members),
        len(records),
    )
    return records


def deduplicate(records):
    result = {}
    for r in records:
        key = (
            clean_text(getattr(r, "name_ko", "")),
            clean_text(getattr(r, "name_en", "")).upper(),
            clean_text(getattr(r, "department_en", "")).upper(),
            normalize_email(getattr(r, "email", "")),
            clean_text(getattr(r, "detail_url", "")),
        )
        result[key] = r
    return list(result.values())


def chunk_departments(departments, workers):
    workers = max(1, workers)
    chunk_size = max(1, math.ceil(len(departments) / workers))
    return [departments[i:i + chunk_size] for i in range(0, len(departments), chunk_size)]


def crawl_department_chunk(
    chunk_id,
    departments,
    headless,
    existing_detail_urls=None,
    retries: int = 2,
    wait_timeout: int = 12,
    progress: Optional[CrawlProgress] = None,
    recrawl: bool = False,
    orcid_token: str = "",
):
    records = []

    for idx, dept in enumerate(departments, start=1):
        if progress:
            progress.check_cancelled()
            progress.emit(
                20,
                f"학과 처리 시작: {dept['department_ko']} ({idx}/{len(departments)} / worker {chunk_id})"
            )

        logging.info(
            "[worker %d] [%d/%d] %s / %s",
            chunk_id,
            idx,
            len(departments),
            dept["department_ko"],
            dept["department_en"],
        )

        driver = None
        dept_records = []
        failed = False

        try:
            driver = make_driver(headless=headless)
            dept_records = parse_department_page(
                driver,
                dept,
                existing_detail_urls=existing_detail_urls,
                retries=retries,
                wait_timeout=wait_timeout,
                recrawl=recrawl,
                cancel_check=progress.cancel_check if progress else None,
                detail_progress_callback=(lambda msg: progress.emit(20, msg)) if progress else None,
                orcid_token=orcid_token,
            )
            records.extend(dept_records)

        except CrawlCancelled:
            raise
        except Exception as e:
            failed = True
            logging.warning(
                "[worker %d] department failed: %s | %r",
                chunk_id,
                dept["department_url"],
                e,
            )
            logging.warning(traceback.format_exc())

        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass

            if progress:
                progress.department_done(
                    dept_name=dept["department_ko"],
                    new_records=len(dept_records),
                    failed=failed,
                )

    return records


def crawl_all_parallel(
    headless=HEADLESS,
    workers=1,
    existing_detail_urls=None,
    limit_departments=0,
    retries: int = 2,
    wait_timeout: int = 12,
    recrawl: bool = False,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
):
    if progress_callback:
        progress_callback(1, "학과 목록 불러오는 중...")

    orcid_token = get_orcid_access_token()

    bootstrap_driver = make_driver(headless=headless)
    try:
        departments = parse_index_for_medicine_departments(
            bootstrap_driver,
            retries=retries,
            wait_timeout=wait_timeout,
        )
    finally:
        bootstrap_driver.quit()

    if limit_departments > 0:
        departments = departments[:limit_departments]

    if not departments:
        logging.warning("no departments found")
        if progress_callback:
            progress_callback(100, "학과를 찾지 못했습니다.")
        return []

    logging.info("total departments to crawl: %d", len(departments))
    logging.info("existing detail urls loaded: %d", len(existing_detail_urls or set()))
    logging.info(
        "crawl options | retries=%d | wait_timeout=%d | recrawl=%s",
        retries,
        wait_timeout,
        recrawl,
    )

    if progress_callback:
        progress_callback(10, f"학과 {len(departments)}개 확인")

    chunks = chunk_departments(departments, workers)
    all_records = []
    progress = CrawlProgress(
        total_departments=len(departments),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )

    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = [
            executor.submit(
                crawl_department_chunk,
                i + 1,
                chunk,
                headless,
                existing_detail_urls,
                retries,
                wait_timeout,
                progress,
                recrawl,
                orcid_token,
            )
            for i, chunk in enumerate(chunks)
        ]

        for future in as_completed(futures):
            try:
                progress.check_cancelled()
                all_records.extend(future.result())
            except CrawlCancelled:
                for f in futures:
                    f.cancel()
                raise
            except Exception as e:
                logging.warning("worker future failed: %r", e)
                logging.warning(traceback.format_exc())

    result = deduplicate(all_records)
    logging.info("crawl_all_parallel result count after deduplicate: %d", len(result))

    if progress_callback:
        progress_callback(85, f"크롤링 완료, 중복 제거 후 {len(result)}건")

    return result