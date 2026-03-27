# Yonsei College of Medicine Faculty Crawler

연세대학교 의과대학 교수 명단과 기본 정보(영문명, 이메일, 전화번호, 연구실 등)를 수집하는 Selenium 기반 크롤러입니다.

## 수집 항목

- college_ko
- college_en
- department_ko
- department_en
- campus
- name_ko
- name_en
- title_ko
- email
- phone
- office
- detail_url
- source_department_url

## 설치

```bash
pip install -r requirements.txt
```

## 실행

```bash
python run.py
```

## 결과 파일

실행 후 아래 파일이 생성됩니다.

- `output/yonsei_medicine_faculty.db`
- `output/yonsei_medicine_faculty.csv`
- `logs/crawler.log`

## SQLite에서 확인

```sql
SELECT name_ko, name_en, department_ko, email, phone
FROM faculty
ORDER BY department_ko, name_ko;
```

## 주의

- 사이트 구조가 바뀌면 selector나 파싱 로직 수정이 필요할 수 있습니다.
- 일부 교수 페이지에는 전화번호 또는 이메일이 비어 있을 수 있습니다.
- 실행 환경에 Chrome 브라우저가 설치되어 있어야 합니다.
