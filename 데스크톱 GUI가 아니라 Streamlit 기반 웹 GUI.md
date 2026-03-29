데스크톱 GUI가 아니라 Streamlit 기반 웹 GUI

SQLite DB 읽기
학과 목록 로드
이름/학과/이메일 유무로 필터
결과 표 출력
CSV 다운로드
학과별 집계 출력

즉, tkinter로 새로 짜는 대신 지금처럼 streamlit UI로 가는 게 더 실용적입니다.

실행 방법
프로젝트 루트에서:
bash:

streamlit run ui/app.py

파일명이 아직 없다면 예를 들어 아래처럼 저장하세요.

ui/
  app.py

그리고 실행:

.\.venv\Scripts\activate
streamlit run ui/app.py


  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://172.30.1.72:8501




DeskTop GUI 실행 순서

프로젝트 루트에서:

  cd D:\coding\yuhs_home_crowling\yonsei-med-faculty-crawler
.\.venv\Scripts\activate
python -m pip install PySide6 pandas
python run_sqlite.py
python run_desktop.py