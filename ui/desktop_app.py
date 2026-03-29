from pathlib import Path
import sqlite3
import pandas as pd

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


DB_PATH = Path(__file__).resolve().parents[1] / "output" / "yonsei_medicine_faculty.db"


class FacultySearchWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("연세대학교 의과대학 교수 검색")
        self.resize(1200, 720)

        self.result_df = pd.DataFrame()
        self.dept_df = pd.DataFrame()

        self._build_ui()
        self._load_initial_data()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)

        title = QLabel("연세대학교 의과대학 교수 검색")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        root.addWidget(title)

        self.db_label = QLabel(f"DB 경로: {DB_PATH}")
        self.db_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.db_label)

        form_wrap = QWidget()
        form = QGridLayout(form_wrap)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("이름(한글/영문) 검색")

        self.department_combo = QComboBox()
        self.department_combo.addItem("전체")

        self.email_only_check = QCheckBox("이메일 있는 교수만")

        self.search_button = QPushButton("검색")
        self.search_button.clicked.connect(self.search)

        self.refresh_button = QPushButton("새로고침")
        self.refresh_button.clicked.connect(self.refresh_data)

        self.export_button = QPushButton("CSV 저장")
        self.export_button.clicked.connect(self.export_csv)

        form.addWidget(QLabel("이름 검색"), 0, 0)
        form.addWidget(self.name_input, 0, 1)

        form.addWidget(QLabel("학과 선택"), 0, 2)
        form.addWidget(self.department_combo, 0, 3)

        form.addWidget(self.email_only_check, 0, 4)
        form.addWidget(self.search_button, 0, 5)
        form.addWidget(self.refresh_button, 0, 6)
        form.addWidget(self.export_button, 0, 7)

        root.addWidget(form_wrap)

        metrics_wrap = QWidget()
        metrics = QHBoxLayout(metrics_wrap)

        self.total_label = QLabel("교수 수: 0")
        self.email_label = QLabel("이메일 보유: 0")
        self.phone_label = QLabel("전화 보유: 0")

        for w in [self.total_label, self.email_label, self.phone_label]:
            w.setStyleSheet("font-size: 14px; padding: 6px;")
            metrics.addWidget(w)

        metrics.addStretch(1)
        root.addWidget(metrics_wrap)

        self.table = QTableWidget()
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        root.addWidget(self.table)

        self.statusBar().showMessage("준비됨")

        menubar = self.menuBar()
        file_menu = menubar.addMenu("파일")

        export_action = QAction("CSV 저장", self)
        export_action.triggered.connect(self.export_csv)
        file_menu.addAction(export_action)

        refresh_action = QAction("새로고침", self)
        refresh_action.triggered.connect(self.refresh_data)
        file_menu.addAction(refresh_action)

    def _connect_db(self):
        if not DB_PATH.exists():
            raise FileNotFoundError(
                "DB 파일이 없습니다. 먼저 `python run_sqlite.py`로 데이터를 수집해 주세요."
            )
        return sqlite3.connect(DB_PATH)

    def load_departments(self):
        conn = self._connect_db()
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

    def load_faculty(self, name_keyword: str, department_keyword: str, has_email_only: bool):
        conn = self._connect_db()
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

    def _load_initial_data(self):
        try:
            self.dept_df = self.load_departments()
            self.department_combo.clear()
            self.department_combo.addItem("전체")

            if not self.dept_df.empty:
                for dept in self.dept_df["department_ko"].fillna("").tolist():
                    self.department_combo.addItem(dept)

            self.search()
        except Exception as e:
            QMessageBox.critical(self, "오류", str(e))
            self.statusBar().showMessage("초기 로딩 실패")

    def refresh_data(self):
        self.statusBar().showMessage("새로고침 중...")
        self._load_initial_data()
        self.statusBar().showMessage("새로고침 완료")

    def search(self):
        try:
            name_keyword = self.name_input.text().strip()
            department_keyword = self.department_combo.currentText()
            has_email_only = self.email_only_check.isChecked()

            self.result_df = self.load_faculty(
                name_keyword=name_keyword,
                department_keyword=department_keyword,
                has_email_only=has_email_only,
            )

            self._render_table(self.result_df)
            self._update_metrics(self.result_df)
            self.statusBar().showMessage(f"검색 완료: {len(self.result_df)}건")
        except Exception as e:
            QMessageBox.critical(self, "검색 오류", str(e))
            self.statusBar().showMessage("검색 실패")

    def _update_metrics(self, df: pd.DataFrame):
        if df.empty:
            total = 0
            email_cnt = 0
            phone_cnt = 0
        else:
            total = len(df)
            email_cnt = int(df["email"].fillna("").astype(str).str.strip().ne("").sum())
            phone_cnt = int(df["phone"].fillna("").astype(str).str.strip().ne("").sum())

        self.total_label.setText(f"교수 수: {total}")
        self.email_label.setText(f"이메일 보유: {email_cnt}")
        self.phone_label.setText(f"전화 보유: {phone_cnt}")

    def _render_table(self, df: pd.DataFrame):
        self.table.clear()

        if df.empty:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return

        columns = list(df.columns)
        self.table.setColumnCount(len(columns))
        self.table.setRowCount(len(df))
        self.table.setHorizontalHeaderLabels(columns)

        for row_idx, row in enumerate(df.itertuples(index=False)):
            for col_idx, value in enumerate(row):
                text = "" if pd.isna(value) else str(value)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeColumnsToContents()

    def export_csv(self):
        if self.result_df.empty:
            QMessageBox.information(self, "알림", "저장할 검색 결과가 없습니다.")
            return

        default_path = str(
            Path(__file__).resolve().parents[1] / "output" / "yonsei_faculty_search_result.csv"
        )

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "CSV 저장",
            default_path,
            "CSV Files (*.csv)",
        )

        if not file_path:
            return

        try:
            self.result_df.to_csv(file_path, index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "저장 완료", f"저장되었습니다.\n{file_path}")
            self.statusBar().showMessage(f"CSV 저장 완료: {file_path}")
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", str(e))


def main():
    import sys

    app = QApplication(sys.argv)
    window = FacultySearchWindow()
    window.show()
    sys.exit(app.exec())