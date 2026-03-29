# 폴더 구조와 파일 위치

아래 구조를 기준으로 배치하면 됩니다.

```text
project_root/
├─ your_package/
│  ├─ __init__.py
│  ├─ crawler.py
│  ├─ models.py
│  ├─ utils.py
│  └─ config.py
├─ tests/
│  ├─ test_parser_helpers_unittest.py
│  ├─ test_deduplicate_unittest.py
│  ├─ test_department_parsing_unittest.py
│  ├─ test_orcid_unittest.py
│  └─ test_crawl_flow_unittest.py
└─ user_guide.md
```

## 위치 설명

- `your_package/crawler.py`
  - 실제 크롤러 코드 파일 위치입니다.
  - 테스트 코드의 import 경로 `your_package.crawler`는 이 파일을 가리킵니다.

- `tests/`
  - 단위 테스트 파일을 두는 폴더입니다.
  - 프로젝트 루트 바로 아래에 두는 것을 권장합니다.

- `user_guide.md`
  - 테스트 실행 방법, 수정 포인트, 주의사항을 정리한 문서입니다.
  - 프로젝트 루트에 두는 것을 권장합니다.

## 경로를 바꿔야 하는 경우

현재 테스트 파일은 아래 import를 사용합니다.

```python
from your_package.crawler import ...
from your_package import crawler
```

실제 패키지명이 `your_package`가 아니라면, 테스트 파일 안의 `your_package`를 실제 패키지명으로 일괄 변경해 주세요.
