# User Guide

이 번들은 크롤러 테스트를 빠르게 시작할 수 있도록 만든 `unittest` 기반 예시 모음입니다.

## 포함 파일

- `tests/test_parser_helpers_unittest.py`
- `tests/test_deduplicate_unittest.py`
- `tests/test_department_parsing_unittest.py`
- `tests/test_orcid_unittest.py`
- `tests/test_crawl_flow_unittest.py`
- `folder_structure.md`
- `user_guide.md`

## 전제 조건

아래 구조를 가정합니다.

```text
project_root/
├─ your_package/
│  └─ crawler.py
├─ tests/
└─ user_guide.md
```

## 가장 먼저 할 일

1. 압축을 해제합니다.
2. `tests/` 폴더를 프로젝트 루트에 복사합니다.
3. 패키지명이 `your_package`가 아니라면 테스트 파일 안의 import를 실제 패키지명으로 바꿉니다.
4. `crawler.py` 안에 아래 함수들이 존재하는지 확인합니다.

### 테스트 대상 함수 예시

- `_extract_orcid_from_text`
- `_extract_title_ko`
- `_parse_inline_fields`
- `_extract_labeled_alias`
- `_extract_email_from_soup`
- `_extract_email_fallback`
- `_extract_phone_fallback`
- `_extract_office_fallback`
- `_clean_lines`
- `_score_orcid_candidate`
- `deduplicate`
- `parse_department_page`
- `crawl_all_parallel`
- `CrawlProgress`
- `CrawlCancelled`

## 실행 방법

전체 테스트 실행:

```bash
python -m unittest discover -s tests -p "test_*_unittest.py" -v
```

특정 파일만 실행:

```bash
python -m unittest tests.test_parser_helpers_unittest -v
```

## 테스트 구성 설명

### 1. `test_parser_helpers_unittest.py`
순수 함수 위주 테스트입니다.

확인 내용:
- ORCID 추출
- 직함 추출
- 라벨 alias 추출
- inline field 파싱

### 2. `test_deduplicate_unittest.py`
중복 제거 로직 테스트입니다.

확인 내용:
- 같은 `detail_url` 중복 제거
- 다른 URL이어도 같은 사람 정보면 병합되는지
- 다른 사람은 유지되는지

### 3. `test_department_parsing_unittest.py`
상세 페이지 보조 추출 함수 테스트입니다.

확인 내용:
- mailto 기반 이메일 추출
- HTML fallback 이메일 추출
- 전화번호 fallback
- 연구실 fallback

### 4. `test_orcid_unittest.py`
ORCID 점수 계산 로직 테스트입니다.

### 5. `test_crawl_flow_unittest.py`
전체 흐름 테스트입니다.

확인 내용:
- `parse_department_page`의 기본 흐름
- 취소 처리
- `crawl_all_parallel` 진행률 콜백 호출

## 주의사항

- 이 테스트 번들은 외부 사이트에 실제 접속하지 않도록 작성되어 있습니다.
- Selenium 실브라우저를 직접 띄우지 않고 mock 기반으로 흐름을 검증합니다.
- 따라서 실제 운영 환경 검증을 완전히 대체하지는 않습니다.

## 권장 검증 순서

1. `test_parser_helpers_unittest.py`
2. `test_deduplicate_unittest.py`
3. `test_department_parsing_unittest.py`
4. `test_orcid_unittest.py`
5. `test_crawl_flow_unittest.py`

## 실제 운영 전 추가로 해볼 것

- `workers=1`, `limit_departments=1`로 스모크 테스트
- 결과 레코드 5건 수동 점검
- `workers=2`로 병렬 테스트
- 취소 시나리오 테스트
- ORCID 매칭률 확인

## 자주 수정하는 부분

보통 아래만 수정하면 됩니다.

- 테스트 파일 import 경로의 `your_package`
- 실제 프로젝트 구조에 따른 파일 위치
- `FacultyRecord` 필드명이 다를 경우 관련 assertion

## 실패할 때 점검할 것

### ImportError
- 패키지명 `your_package`를 실제 이름으로 바꿨는지 확인

### AttributeError
- 테스트 대상 함수명이 실제 크롤러 코드와 일치하는지 확인

### AssertionError
- 현재 크롤러 구현과 테스트 기대값이 다른지 비교
- 특히 이름 정규식, 라벨 alias, deduplicate 정책을 확인

## 한 줄 정리

이 번들은 **크롤러 핵심 로직을 안전하게 리팩토링하기 위한 최소 테스트 골격**입니다.
