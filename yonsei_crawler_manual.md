# Yonsei Medicine Faculty Crawler Manual

## 📌 개요

이 프로그램은 다음을 수행합니다:

1. 연세대학교 의과대학 교원정보 시스템 크롤링
2. 부족한 정보를 외부 사이트에서 보강
   - 연세의대
   - 연세의료원
   - 세브란스병원
3. ORCID API를 통해 연구자 ID 매칭
4. SQLite DB 및 CSV 저장

---

## 🧱 프로젝트 구조

```
project/
│
├── app/
│   ├── crawler.py
│   ├── database.py
│   ├── sync_faculty.py
│   ├── models.py
│   ├── orcid_api.py
│   ├── utils.py
│   └── config.py
│
├── output/
├── debug/
├── sync_smoke_test.py
├── config_orcid.json
```

---

## ⚙️ 주요 기능

### 1. 기본 크롤링
- FIS 교원정보 시스템에서 교수 정보 수집

### 2. 외부 보강
- 연세의대 / 연세의료원 / 세브란스병원
- 부족한 필드 자동 보완

### 3. ORCID 매칭
- 이메일 기반 우선
- 이름 + 소속 fallback

---

## 🚀 실행 방법

### 기본 실행
```bash
python sync_smoke_test.py
```

---

## 🔧 주요 옵션

| 옵션 | 설명 |
|------|------|
| workers | 병렬 처리 |
| limit_departments | 테스트 범위 |
| retries | 재시도 |
| wait_timeout | 로딩 대기 |
| enable_external_enrichment | 외부 보강 |

---

## 📊 결과 확인

```sql
SELECT COUNT(*) FROM faculty;
```

---

## 🛑 종료 방법

- Ctrl + C
- taskkill /F /IM python.exe

---

## ⚡ 운영 전략

### 테스트
```
enable_external_enrichment=False
limit_departments=1
```

### 운영
```
enable_external_enrichment=True
workers=2~4
```

---

## 📌 한 줄 요약

연세 의대 교수 데이터를 수집하고 외부 사이트와 ORCID로 보강하는 크롤러
