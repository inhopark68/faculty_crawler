# Yonsei College of Medicine Faculty Crawler + API + UI + Docker

연세대학교 의과대학 교수 정보를 수집하고, SQLite/CSV/XLSX로 저장한 뒤,
FastAPI 검색 API와 Streamlit UI로 조회할 수 있는 Docker 포함 패키지입니다.

## 포함 구성

- Selenium 기반 병렬 크롤러
- SQLite / CSV / XLSX 저장
- FastAPI 검색 API
- Streamlit 웹 UI
- Dockerfile
- docker-compose.yml

## 1. 로컬 실행

설치:

```bash
pip install -r requirements.txt
```

데이터 수집:

```bash
python run.py --workers 4
```

API 실행:

```bash
uvicorn api.main:app --reload
```

UI 실행:

```bash
streamlit run ui/app.py
```

## 2. Docker 실행

이미지 빌드:

```bash
docker compose build
```

데이터 수집:

```bash
docker compose run --rm api python run.py --workers 4
```

API + UI 실행:

```bash
docker compose up
```

접속 주소:

- API 문서: http://127.0.0.1:8000/docs
- Streamlit UI: http://127.0.0.1:8501

## 3. 결과 파일

- `output/yonsei_medicine_faculty.db`
- `output/yonsei_medicine_faculty.csv`
- `output/yonsei_medicine_faculty.xlsx`
- `output/yonsei_medicine_faculty.summary.json`
- `logs/crawler.log`

## 4. 추천 실행 예시

로컬 테스트:

```bash
python run.py --workers 2 --limit-departments 3
```

Docker 테스트:

```bash
docker compose run --rm api python run.py --workers 2 --limit-departments 3
```

## 주의

- Docker 환경에서도 Chrome이 들어 있으므로 Selenium이 동작합니다.
- 워커 수는 보통 4 정도가 무난합니다.
- 먼저 크롤링을 돌려서 DB를 만든 뒤 API/UI를 보는 흐름이 가장 편합니다.
