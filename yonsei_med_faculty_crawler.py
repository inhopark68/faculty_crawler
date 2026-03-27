import re
import time
import logging
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASE_URL = "https://ee.yonsei.ac.kr"
INDEX_URL = f"{BASE_URL}/faculty/dep_search.do"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    )
}


@dataclass
class FacultyRecord:
    college_ko: str = ""
    college_en: str = ""
    department_ko: str = ""
    department_en: str = ""
    campus: str = ""
    name_ko: str = ""
    name_en: str = ""
    title_ko: str = ""
    email: str = ""
    phone: str = ""
    office: str = ""
    detail_url: str = ""
    source_department_url: str = ""


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(HEADERS)

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


SESSION = build_session()


def get_soup(url: str, sleep_sec: float = 0.4) -> BeautifulSoup:
    time.sleep(sleep_sec)
    resp = SESSION.get(url, timeout=30)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def normalize_email(email: str) -> str:
    email = clean_text(email).upper()
    if not email:
        return ""

    # 카드 페이지에서 종종 "@YUHS.AC@YONSEI.AC.KR" 같이 깨진 값이 보임
    email = email.replace("@YUHS.AC@YONSEI.AC.KR", "@YUHS.AC.KR")
    email = email.replace("@YONSEI.AC@YONSEI.AC.KR", "@YONSEI.AC.KR")

    # 공백/쉼표 등 제거
    email = email.replace(" ", "").replace(";", "").replace(",", "")
    return email


def normalize_phone(phone: str) -> str:
    phone = clean_text(phone)
    if not phone:
        return ""

    # 괄호/하이픈/공백 정도만 허용
    m = re.search(r"(\+?\d[\d\-\)\(\s]{6,}\d)", phone)
    return clean_text(m.group(1)) if m else phone


def split_department_label(label: str) -> tuple[str, str]:
    parts = [clean_text(x) for x in label.split("/") if clean_text(x)]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return label, ""


def parse_index_for_medicine_departments() -> List[Dict[str, str]]:
    soup = get_soup(INDEX_URL)

    # 텍스트 결과만으로도 의과대학 섹션과 개별 링크가 확인됨
    departments = []
    seen = set()

    current_college_ko = ""
    current_college_en = ""
    inside_medicine = False

    # 실제 HTML 구조에 너무 의존하지 않게 전체 링크를 순회
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        text = clean_text(a.get_text(" ", strip=True))

        if not text:
            continue

        full_url = urljoin(INDEX_URL, href)

        # dep_search 페이지 내 의과대학 하위 depMember 링크만 수집
        # 보통 campus=sinchonMed & type=departMent 형태
        if "depMember.do" in href and "type=departMent" in href:
            # 링크 텍스트가 "가정의학교실 / Department of Family Medicine" 식
            dept_ko, dept_en = split_department_label(text)

            # 의과대학 링크만 걸러내기: URL 패턴 우선
            if "campus=sinchonMed" in href:
                if full_url not in seen:
                    seen.add(full_url)
                    departments.append(
                        {
                            "college_ko": "의과대학",
                            "college_en": "College of Medicine",
                            "department_ko": dept_ko,
                            "department_en": dept_en,
                            "department_url": full_url,
                        }
                    )

    return departments


def parse_name_line(line: str) -> tuple[str, str]:
    """
    예:
    '김경현 Kyunghyun Kim'
    '강석구 Seok-Gu Kang'
    '문주형 Ju Hyung'
    """
    line = clean_text(line)
    if not line:
        return "", ""

    m = re.match(r"^([가-힣·\s]+)\s+([A-Za-z][A-Za-z ,.'\-]*)$", line)
    if m:
        return clean_text(m.group(1)), clean_text(m.group(2))

    # 이름이 한글만/영문만 있으면 대응
    if re.search(r"[가-힣]", line) and not re.search(r"[A-Za-z]", line):
        return line, ""
    if re.search(r"[A-Za-z]", line) and not re.search(r"[가-힣]", line):
        return "", line

    return line, ""


def extract_detail_url_from_anchor(anchor_tag, base_url: str) -> str:
    href = anchor_tag.get("href", "")
    if not href:
        return ""
    return urljoin(base_url, href)


def parse_department_page(dept_meta: Dict[str, str]) -> List[FacultyRecord]:
    url = dept_meta["department_url"]
    soup = get_soup(url)

    records: List[FacultyRecord] = []
    seen_detail_urls = set()

    # 카드형 목록에서 more + 링크가 상세 페이지로 연결됨
    # 목록 페이지 텍스트상 교수명/직위/이메일이 이미 보이므로 여기서 1차 수집
    anchors = soup.find_all("a", href=True)

    for a in anchors:
        href = a.get("href", "")
        text = clean_text(a.get_text(" ", strip=True))

        if "depMember.do" in href and "mode=view" in href and "userId=" in href:
            detail_url = urljoin(url, href)
            if detail_url in seen_detail_urls:
                continue
            seen_detail_urls.add(detail_url)

            block_text = ""
            parent = a.parent
            if parent:
                block_text = clean_text(parent.get_text("\n", strip=True))

            # 주변 텍스트를 조금 더 넓게 잡기
            candidate_text = block_text or clean_text(a.get_text("\n", strip=True))
            lines = [clean_text(x) for x in candidate_text.split("\n") if clean_text(x)]

            name_ko, name_en, campus, title_ko, email = "", "", "", "", ""

            # 이름 찾기
            for line in lines:
                if re.search(r"[가-힣]", line) and re.search(r"[A-Za-z]", line):
                    nk, ne = parse_name_line(line)
                    if nk or ne:
                        name_ko, name_en = nk, ne
                        break

            # campus/title/email 찾기
            for line in lines:
                if "Campus" in line:
                    campus = line
                if "/" in line and dept_meta["department_en"] in line:
                    # 예: Department of Neurosurgery/부교수
                    title_ko = clean_text(line.split("/")[-1])
                if "@" in line:
                    email = normalize_email(line)

            record = FacultyRecord(
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
                source_department_url=url,
            )

            # 상세 페이지로 보강
            enrich_record_from_detail(record)
            records.append(record)

    return records


def extract_labeled_value(text: str, label: str) -> str:
    """
    상세 페이지의 텍스트:
    Campus : Seoul Campus
    Department : Department of Neurosurgery
    E-mail : NSKHK@YUHS.AC
    Tel : 02)2123-...
    Office : ...
    """
    pattern = rf"{re.escape(label)}\s*:\s*(.+)"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    return clean_text(m.group(1)) if m else ""


def enrich_record_from_detail(record: FacultyRecord) -> None:
    if not record.detail_url:
        return

    try:
        soup = get_soup(record.detail_url, sleep_sec=0.3)
        text = clean_text(soup.get_text("\n", strip=True))

        # 상세 페이지 예시에서 E-mail / Tel / Office / Department 구조 확인 가능
        detail_dept = extract_labeled_value(text, "Department")
        detail_email = normalize_email(extract_labeled_value(text, "E-mail"))
        detail_tel = normalize_phone(extract_labeled_value(text, "Tel"))
        detail_office = extract_labeled_value(text, "Office")
        detail_campus = extract_labeled_value(text, "Campus")

        # 페이지 상단 이름 재시도
        # 첫 부분에서 "한글명  영문명" 줄을 찾아 보강
        for line in [clean_text(x) for x in soup.stripped_strings]:
            if re.search(r"[가-힣]", line) and re.search(r"[A-Za-z]", line):
                nk, ne = parse_name_line(line)
                if nk and not record.name_ko:
                    record.name_ko = nk
                if ne and not record.name_en:
                    record.name_en = ne
                if nk or ne:
                    break

        if detail_campus:
            record.campus = detail_campus
        if detail_email:
            record.email = detail_email
        if detail_tel:
            record.phone = detail_tel
        if detail_office:
            record.office = detail_office
        if detail_dept and not record.department_en:
            record.department_en = detail_dept

    except Exception as e:
        logging.warning("detail parse failed: %s | %s", record.detail_url, e)


def deduplicate_records(records: List[FacultyRecord]) -> List[FacultyRecord]:
    dedup: Dict[tuple, FacultyRecord] = {}

    for r in records:
        key = (
            clean_text(r.name_ko),
            clean_text(r.name_en).upper(),
            clean_text(r.department_en).upper(),
            normalize_email(r.email),
            clean_text(r.detail_url),
        )
        dedup[key] = r

    return list(dedup.values())


def records_to_dataframe(records: List[FacultyRecord]) -> pd.DataFrame:
    rows = [asdict(r) for r in records]
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    preferred_cols = [
        "college_ko",
        "college_en",
        "department_ko",
        "department_en",
        "campus",
        "name_ko",
        "name_en",
        "title_ko",
        "email",
        "phone",
        "office",
        "detail_url",
        "source_department_url",
    ]
    df = df[preferred_cols]

    df = df.sort_values(
        by=["department_ko", "title_ko", "name_ko", "name_en"],
        na_position="last"
    ).reset_index(drop=True)

    return df


def save_outputs(df: pd.DataFrame, csv_path: str, xlsx_path: str) -> None:
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False)

    # openpyxl이 있으면 열 너비 자동 조정
    try:
        from openpyxl import load_workbook

        wb = load_workbook(xlsx_path)
        ws = wb.active

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val = "" if cell.value is None else str(cell.value)
                max_len = max(max_len, len(val))
            ws.column_dimensions[col_letter].width = min(max_len + 2, 50)

        wb.save(xlsx_path)
    except Exception as e:
        logging.warning("xlsx post-processing skipped: %s", e)


def crawl_yonsei_medicine_faculty() -> pd.DataFrame:
    departments = parse_index_for_medicine_departments()
    logging.info("found departments: %d", len(departments))

    all_records: List[FacultyRecord] = []

    for i, dept in enumerate(departments, start=1):
        logging.info(
            "[%d/%d] %s / %s",
            i, len(departments), dept["department_ko"], dept["department_en"]
        )
        try:
            records = parse_department_page(dept)
            all_records.extend(records)
        except Exception as e:
            logging.exception("department failed: %s | %s", dept["department_url"], e)

    all_records = deduplicate_records(all_records)
    df = records_to_dataframe(all_records)
    return df


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s"
    )

    df = crawl_yonsei_medicine_faculty()

    logging.info("total faculty rows: %d", len(df))

    csv_path = "yonsei_college_of_medicine_faculty.csv"
    xlsx_path = "yonsei_college_of_medicine_faculty.xlsx"
    save_outputs(df, csv_path, xlsx_path)

    print(df.head(20).to_string(index=False))
    print(f"\nSaved:\n- {csv_path}\n- {xlsx_path}")


if __name__ == "__main__":
    main()