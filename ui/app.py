from pathlib import Path
import sqlite3
import pandas as pd
import streamlit as st

DB_PATH = Path(__file__).resolve().parents[1] / "output" / "yonsei_medicine_faculty.db"

st.set_page_config(page_title="Yonsei Faculty Search", layout="wide")
st.title("연세대학교 의과대학 교수 검색")
st.caption(f"DB 경로: {DB_PATH}")

if not DB_PATH.exists():
    st.error("DB 파일이 없습니다. 먼저 `python run_sqlite.py`로 데이터를 수집해 주세요.")
    st.stop()


@st.cache_data
def load_departments():
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(
            """
            SELECT department_ko, department_en, COUNT(*) AS cnt
            FROM faculty
            GROUP BY department_ko, department_en
            ORDER BY department_ko
            """,
            conn,
        )
    finally:
        conn.close()


@st.cache_data
def load_faculty(name_keyword: str, department_keyword: str, has_email_only: bool):
    conn = sqlite3.connect(DB_PATH)
    try:
        sql = """
        SELECT
            department_ko, department_en, name_ko, name_en, title_ko,
            email, phone, office, campus, detail_url, collected_at
        FROM faculty
        WHERE 1=1
        """
        params = []

        if name_keyword:
            sql += " AND (name_ko LIKE ? OR name_en LIKE ?)"
            params.extend([f"%{name_keyword}%", f"%{name_keyword}%"])

        if department_keyword and department_keyword != "전체":
            sql += " AND department_ko = ?"
            params.append(department_keyword)

        if has_email_only:
            sql += " AND email IS NOT NULL AND TRIM(email) != ''"

        sql += " ORDER BY department_ko, name_ko, name_en"
        return pd.read_sql_query(sql, conn, params=params)
    finally:
        conn.close()


dept_df = load_departments()
department_options = ["전체"] + dept_df["department_ko"].fillna("").tolist()

with st.sidebar:
    st.header("검색 조건")
    name_keyword = st.text_input("이름 검색", "")
    department_keyword = st.selectbox("학과 선택", department_options, index=0)
    has_email_only = st.checkbox("이메일 있는 교수만", value=False)

    if st.button("새로고침"):
        st.cache_data.clear()
        st.rerun()

result_df = load_faculty(name_keyword, department_keyword, has_email_only)

m1, m2, m3 = st.columns(3)
m1.metric("교수 수", len(result_df))
m2.metric(
    "이메일 보유",
    int(result_df["email"].fillna("").astype(str).str.strip().ne("").sum()) if not result_df.empty else 0,
)
m3.metric(
    "전화 보유",
    int(result_df["phone"].fillna("").astype(str).str.strip().ne("").sum()) if not result_df.empty else 0,
)

st.subheader("검색 결과")
st.dataframe(result_df, use_container_width=True, hide_index=True)

csv_bytes = result_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
st.download_button(
    label="검색 결과 CSV 다운로드",
    data=csv_bytes,
    file_name="yonsei_faculty_search_result.csv",
    mime="text/csv",
)

st.subheader("학과별 인원")
st.dataframe(dept_df, use_container_width=True, hide_index=True)