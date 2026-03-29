# Yonsei Medicine Faculty Crawler - 운영/배포 매뉴얼

## 📦 목적
이 문서는 크롤러를 실제 운영 환경에서 안정적으로 실행/관리하기 위한 가이드입니다.

---

## 🧰 요구사항

- Python 3.10+
- Chrome 브라우저
- pip 패키지:
  ```
  selenium
  webdriver-manager
  requests
  beautifulsoup4
  ```

설치:
```bash
pip install -r requirements.txt
```

---

## 📁 권장 배포 구조

```
project/
│
├── app/
├── output/
├── logs/
├── config_orcid.json
├── run_sync.py
└── .venv/
```

---

## 🚀 실행 스크립트 (운영용)

`run_sync.py`

```python
from app.sync_faculty import sync_faculty

if __name__ == "__main__":
    sync_faculty(
        db_path="./output/faculty.db",
        workers=2,
        recrawl=True,
        headless=True,
        limit_departments=0,
        retries=3,
        wait_timeout=25,
        enable_external_enrichment=True,
    )
```

---

## ⏱ 자동 실행 (Windows Task Scheduler)

### 작업 생성
1. 작업 스케줄러 열기
2. 기본 작업 만들기
3. 트리거: 매일 / 매주
4. 동작:
   ```
   python D:\path\to\run_sync.py
   ```

---

## 🐧 자동 실행 (Linux / macOS)

```bash
crontab -e
```

```bash
0 3 * * * /usr/bin/python3 /path/run_sync.py
```

---

## 🧾 로그 관리

### 기본 설정 추가

```python
import logging

logging.basicConfig(
    filename="logs/crawler.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
```

---

## 💾 DB 백업 전략

```bash
cp output/faculty.db output/faculty_backup_$(date +%Y%m%d).db
```

또는 Windows:

```powershell
copy output\faculty.db output\faculty_backup.db
```

---

## ⚡ 성능 최적화

| 항목 | 권장값 |
|------|------|
| workers | 2~4 |
| wait_timeout | 20~30 |
| retries | 2~3 |

---

## 🛑 장애 대응

### 1. 크롤링 멈춤
- Ctrl + C
- 또는:
```powershell
taskkill /F /IM python.exe
```

### 2. Chrome 오류
- chromedriver 캐시 삭제 후 재실행

### 3. 데이터 0건
- wait_timeout 증가
- limit_departments 확인

---

## 🔐 ORCID 설정

```json
{
  "client_id": "...",
  "client_secret": "...",
  "token": "..."
}
```

---

## 📊 모니터링 쿼리

```sql
SELECT COUNT(*) FROM faculty;
```

```sql
SELECT COUNT(*) FROM faculty WHERE email IS NOT NULL;
```

```sql
SELECT COUNT(*) FROM faculty WHERE external_source_url IS NOT NULL;
```

---

## 🔁 운영 플로우

```
1. 스케줄 실행
2. 크롤링 수행
3. DB 업데이트
4. 로그 기록
5. 백업
```

---

## 📌 운영 체크리스트

- [ ] DB 생성 확인
- [ ] 로그 파일 생성 확인
- [ ] ORCID 정상 작동
- [ ] external_source_url 채워짐
- [ ] 주기적 실행 확인

---

## 🎯 한 줄 요약

운영 환경에서 자동으로 교수 데이터를 수집하고, 외부 사이트와 ORCID로 보강하여 DB에 저장하는 크롤러
