# Yonsei College of Medicine Faculty Crawler + FastAPI + Streamlit

연세대학교 의과대학 교수 정보를 수집하고, SQLite로 저장한 뒤,
FastAPI 검색 API와 Streamlit 웹 UI로 조회할 수 있는 패키지입니다.

## 포함 구성

- Selenium 기반 병렬 크롤러
- SQLite / CSV / XLSX 저장
- 재실행 시 `detail_url` 기준 resume
- FastAPI 검색 API
- Streamlit 웹 UI

## 설치

```bash
pip install -r requirements.txt
```

## 1) 데이터 수집

기본 실행:

```bash
python run.py --workers 4
```

테스트 실행:

```bash
python run.py --workers 2 --limit-departments 3
```

기본 DB 경로:

```text
output/yonsei_medicine_faculty.db
```

## 2) FastAPI 실행

```bash
uvicorn api.main:app --reload
```

브라우저에서 확인:

- API 문서: `http://127.0.0.1:8000/docs`
- 헬스체크: `http://127.0.0.1:8000/health`
- 교수 목록: `http://127.0.0.1:8000/faculty`

예시 쿼리:

- `http://127.0.0.1:8000/faculty?department=내과`
- `http://127.0.0.1:8000/faculty?name=김`
- `http://127.0.0.1:8000/faculty?has_email=true`
- `http://127.0.0.1:8000/faculty/departments`

## 3) Streamlit 실행

```bash
streamlit run ui/app.py
```

브라우저에서 확인:

- `http://localhost:8501`

## 주요 파일

- `run.py`: 크롤러 실행
- `api/main.py`: FastAPI 앱
- `ui/app.py`: Streamlit 앱
- `output/yonsei_medicine_faculty.db`: 수집 DB

## 주의

- 먼저 `python run.py`로 데이터를 수집해야 UI/API에서 결과를 볼 수 있습니다.
- Chrome 브라우저가 설치되어 있어야 합니다.
- 워커 수는 보통 `4~6` 정도가 무난합니다.
