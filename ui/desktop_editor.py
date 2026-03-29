from pathlib import Path
import json
import sqlite3
import pandas as pd
import re
import shutil
from datetime import datetime, timedelta
import multiprocessing
import os
import sys

import requests
from PySide6.QtCore import Qt, QUrl, QObject, QThread, Signal, QTimer
from PySide6.QtGui import QAction, QDesktopServices, QColor, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
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
    QDialog,
    QDialogButtonBox,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
)

import inspect
import app.crawler as crawler_module
from app.database import (
    init_db,
    ensure_faculty_table_schema,
    get_existing_detail_urls,
    save_to_db,
)

DB_PATH = Path(__file__).resolve().parent / "output" / "yonsei_medicine_faculty.db"
ORCID_CONFIG_PATH = Path(__file__).resolve().parent / "config_orcid.json"

COLUMN_DEFINITIONS = [
    {"name": "id", "label": "ID", "editable": False},
    {"name": "department_ko", "label": "학과(한글)", "editable": True},
    {"name": "department_en", "label": "학과(영문)", "editable": True},
    {"name": "name_ko", "label": "이름(한글)", "editable": True},
    {"name": "name_en", "label": "이름(영문)", "editable": True},
    {"name": "title_ko", "label": "직함", "editable": True},
    {"name": "email", "label": "이메일", "editable": True},
    {"name": "orcid_id", "label": "ORCID", "editable": True},
    {"name": "phone", "label": "전화번호", "editable": True},
    {"name": "office", "label": "연구실", "editable": True},
    {"name": "campus", "label": "캠퍼스", "editable": True},
    {"name": "detail_url", "label": "상세 URL", "editable": True},
    {"name": "collected_at", "label": "수집일시", "editable": False},
]

TABLE_COLUMNS = [column["name"] for column in COLUMN_DEFINITIONS]
EDITABLE_COLUMNS = {column["name"] for column in COLUMN_DEFINITIONS if column["editable"]}
COLUMN_LABELS = {column["name"]: column["label"] for column in COLUMN_DEFINITIONS}


def configure_windows_multiprocessing():
    """
    Windows/PyInstaller 환경에서 multiprocessing 또는 subprocess 기반 크롤러가
    잘못된 실행 파일을 자식 프로세스로 띄우며 WinError 193을 내는 경우를 줄입니다.
    """
    if os.name != "nt":
        return

    try:
        multiprocessing.freeze_support()
    except Exception:
        pass

    try:
        multiprocessing.set_executable(sys.executable)
    except Exception:
        pass




def _call_crawler_with_supported_kwargs(crawl_func, **kwargs):
    """호출 가능한 크롤러가 받는 인자만 골라 안전하게 호출합니다."""
    try:
        sig = inspect.signature(crawl_func)
        supported = {k: v for k, v in kwargs.items() if k in sig.parameters}
    except (TypeError, ValueError):
        supported = kwargs
    return crawl_func(**supported)


def _resolve_crawl_callable(prefer_safe_mode: bool = False):
    """crawler 모듈에서 사용 가능한 크롤링 엔트리포인트를 찾습니다."""
    safe_candidates = [
        "crawl_all_sequential",
        "crawl_all_serial",
        "crawl_all_sync",
        "crawl_all",
        "crawl_faculty_all",
    ]
    parallel_candidates = ["crawl_all_parallel"]

    ordered = (safe_candidates + parallel_candidates) if prefer_safe_mode else (parallel_candidates + safe_candidates)
    for name in ordered:
        func = getattr(crawler_module, name, None)
        if callable(func):
            return func, name
    raise RuntimeError("app.crawler에서 사용할 수 있는 크롤링 함수를 찾지 못했습니다. crawl_all_parallel 또는 crawl_all 계열 함수가 필요합니다.")

def load_orcid_config():
    if not ORCID_CONFIG_PATH.exists():
        return {}
    try:
        with open(ORCID_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_orcid_config(data: dict):
    with open(ORCID_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def issue_orcid_token(client_id: str, client_secret: str) -> str:
    resp = requests.post(
        "https://orcid.org/oauth/token",
        headers={"Accept": "application/json"},
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": "/read-public",
        },
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return data.get("access_token", "")


class OrcidConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("ORCID Public API 설정")
        self.resize(560, 260)

        cfg = load_orcid_config()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.client_id_input = QLineEdit(cfg.get("client_id", ""))
        self.client_secret_input = QLineEdit(cfg.get("client_secret", ""))
        self.client_secret_input.setEchoMode(QLineEdit.Password)

        self.token_input = QPlainTextEdit()
        self.token_input.setPlainText(cfg.get("token", ""))
        self.token_input.setPlaceholderText("발급된 /read-public access token")

        form.addRow("Client ID", self.client_id_input)
        form.addRow("Client Secret", self.client_secret_input)
        form.addRow("Access Token", self.token_input)

        layout.addLayout(form)

        btn_row = QHBoxLayout()

        self.issue_btn = QPushButton("토큰 발급")
        self.issue_btn.clicked.connect(self.issue_token)

        self.save_btn = QPushButton("저장")
        self.save_btn.clicked.connect(self.save_config_only)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        btn_row.addWidget(self.issue_btn)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch(1)

        layout.addLayout(btn_row)
        layout.addWidget(self.status_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    def issue_token(self):
        client_id = self.client_id_input.text().strip()
        client_secret = self.client_secret_input.text().strip()

        if not client_id or not client_secret:
            QMessageBox.warning(self, "입력 오류", "Client ID와 Client Secret을 입력해 주세요.")
            return

        try:
            token = issue_orcid_token(client_id, client_secret)
            if not token:
                raise RuntimeError("토큰을 발급받지 못했습니다.")
            self.token_input.setPlainText(token)
            self.status_label.setText("토큰 발급 성공")
            self.save_config_only()
        except Exception as e:
            self.status_label.setText(str(e))
            QMessageBox.critical(self, "ORCID 오류", str(e))

    def save_config_only(self):
        data = {
            "client_id": self.client_id_input.text().strip(),
            "client_secret": self.client_secret_input.text().strip(),
            "token": self.token_input.toPlainText().strip(),
        }
        save_orcid_config(data)
        self.status_label.setText("설정 저장 완료")


class AddFacultyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("교수 추가")
        self.resize(500, 420)

        self.inputs = {}

        layout = QVBoxLayout(self)
        form = QFormLayout()

        for field in [
            "department_ko",
            "department_en",
            "name_ko",
            "name_en",
            "title_ko",
            "email",
            "orcid_id",
            "phone",
            "office",
            "campus",
            "detail_url",
        ]:
            edit = QLineEdit()
            self.inputs[field] = edit
            form.addRow(COLUMN_LABELS[field], edit)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self):
        return {k: v.text().strip() for k, v in self.inputs.items()}


class DiffPreviewDialog(QDialog):
    def __init__(self, diff_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("저장 전 변경 내용 확인")
        self.resize(900, 600)

        layout = QVBoxLayout(self)

        label = QLabel("아래 변경 내용을 확인한 뒤 저장하세요.")
        layout.addWidget(label)

        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(diff_text)
        layout.addWidget(self.text)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class CrawlWorker(QObject):
    finished = Signal(int)
    error = Signal(str)
    status = Signal(str)
    progress = Signal(int)
    progress_detail = Signal(str)
    log = Signal(str)

    def __init__(
        self,
        workers=1,
        headless=True,
        limit_departments=0,
        enable_external_enrichment=True,
        enable_orcid=True,
        retries=2,
        wait_timeout=20,
        test_mode=False,
    ):
        super().__init__()
        self.workers = workers
        self.headless = headless
        self.limit_departments = limit_departments
        self.enable_external_enrichment = enable_external_enrichment
        self.enable_orcid = enable_orcid
        self.retries = retries
        self.wait_timeout = wait_timeout
        self.test_mode = test_mode
        self._cancel_requested = False

    def cancel(self):
        self._cancel_requested = True
        self.status.emit("크롤링 중단 요청됨... 현재 작업 마무리 후 중단합니다.")

    def _on_progress(self, percent: int, message: str):
        self.progress.emit(percent)
        self.progress_detail.emit(message)
        self.status.emit(message)
        self.log.emit(message)

    def _log(self, message: str):
        self.log.emit(message)
        self.status.emit(message)

    def run(self):
        try:
            started_at = datetime.now()
            self._log(f"크롤링 작업 시작: {started_at:%Y-%m-%d %H:%M:%S}")
            self.progress.emit(0)
            self.progress_detail.emit("초기화 시작")
            self.status.emit("DB 초기화 중...")
            init_db()
            ensure_faculty_table_schema()

            if self._cancel_requested:
                raise RuntimeError("사용자 요청으로 중단되었습니다.")

            self.progress.emit(5)
            self.progress_detail.emit("기존 URL 로드")
            self.status.emit("기존 detail_url 로드 중...")
            existing_detail_urls = get_existing_detail_urls()

            if self._cancel_requested:
                raise RuntimeError("사용자 요청으로 중단되었습니다.")

            self.progress.emit(10)
            self.progress_detail.emit("크롤링 실행 중")
            self.status.emit("크롤링 실행 중...")

            effective_limit = max(0, self.limit_departments if self.test_mode else 0)
            crawl_kwargs = dict(
                headless=self.headless,
                workers=max(1, self.workers),
                existing_detail_urls=existing_detail_urls,
                limit_departments=effective_limit,
                recrawl=True,
                retries=max(1, self.retries),
                wait_timeout=max(5, self.wait_timeout),
                progress_callback=self._on_progress,
                cancel_check=lambda: self._cancel_requested,
            )

            prefer_safe_mode = os.name == "nt" and (getattr(sys, "frozen", False) or sys.platform.startswith("win"))
            crawl_func, crawl_func_name = _resolve_crawl_callable(prefer_safe_mode=prefer_safe_mode)
            self.status.emit(f"크롤러 실행 함수: {crawl_func_name}")
            self.log.emit(f"실행 옵션 | workers={max(1, self.workers)} | headless={self.headless} | retries={self.retries} | wait_timeout={self.wait_timeout} | limit={effective_limit} | 외부보강={self.enable_external_enrichment} | ORCID={self.enable_orcid}")

            crawl_invoke_kwargs = dict(crawl_kwargs)
            crawl_invoke_kwargs.update(
                enable_external_enrichment=self.enable_external_enrichment,
                enable_orcid=self.enable_orcid,
            )

            try:
                records = _call_crawler_with_supported_kwargs(crawl_func, **crawl_invoke_kwargs)
            except OSError as e:
                if getattr(e, "winerror", None) != 193:
                    raise

                self.status.emit("병렬 크롤링 실행에 실패하여 안전 모드(단일 프로세스)로 재시도합니다.")
                self.log.emit("병렬 실행 실패로 workers=1 안전 모드 재시도")
                safe_func, safe_name = _resolve_crawl_callable(prefer_safe_mode=True)
                safe_kwargs = dict(crawl_invoke_kwargs)
                safe_kwargs["workers"] = 1
                records = _call_crawler_with_supported_kwargs(safe_func, **safe_kwargs)
                self.status.emit(f"안전 모드 크롤러 실행 함수: {safe_name}")

            if self._cancel_requested:
                raise RuntimeError("사용자 요청으로 중단되었습니다.")

            self.progress.emit(90)
            self.progress_detail.emit(f"DB 저장 준비: {len(records)}건")
            self.status.emit("DB 저장 중...")
            save_to_db(records)

            elapsed = datetime.now() - started_at
            self.progress.emit(100)
            self.progress_detail.emit(f"완료: {len(records)}건")
            self.log.emit(f"크롤링 완료: {len(records)}건 / 소요 시간: {elapsed}")
            self.finished.emit(len(records))
        except OSError as e:
            if getattr(e, "winerror", None) == 193:
                message = (
                    "[WinError 193] 올바른 Win32 응용 프로그램이 아닌 파일을 실행하려고 했습니다.\n\n"
                    "가능한 원인:\n"
                    "- 크롤러가 .exe가 아닌 파일을 실행 파일로 사용한 경우\n"
                    "- 32비트/64비트 아키텍처가 맞지 않는 경우\n"
                    "- 패키징된 앱에서 자식 프로세스 실행 경로가 잘못 잡힌 경우\n\n"
                    "조치: desktop_editor.py에서 순차 크롤링 안전 모드 재시도를 넣었습니다.\n"
                    "그래도 계속 실패하면 app.crawler 내부의 외부 실행 파일/드라이버 경로를 확인해 주세요.\n\n"
                    f"원본 오류: {e}"
                )
                self.error.emit(message)
            else:
                self.log.emit(f"크롤링 예외 발생: {e}")
            self.error.emit(str(e))
        except Exception as e:
            self.log.emit(f"크롤링 예외 발생: {e}")
            self.error.emit(str(e))


class FacultyEditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("연세대학교 의과대학 교수명단 편집기")
        self.resize(1820, 920)
        self._ensure_window_buttons()

        self.df = pd.DataFrame()
        self.original_df = pd.DataFrame()
        self.dirty = False

        self.crawl_thread = None
        self.crawl_worker = None
        self.auto_update_timer = None

        self._build_ui()
        self._fit_to_primary_screen()
        self._load_initial_data()


    def _fit_to_primary_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            self.setGeometry(60, 80, 1820, 920)
            return

        available = screen.availableGeometry()

        # 1920 x 1080 디스플레이 권장 크기
        recommended_width = 1820
        recommended_height = 920

        # 실제 화면이 더 작으면 화면 안에 맞춤
        width = min(recommended_width, available.width())
        height = min(recommended_height, available.height())

        x = available.x() + max(0, (available.width() - width) // 2)
        y = available.y() + max(0, (available.height() - height) // 2)

        self.setGeometry(x, y, width, height)

    def _ensure_window_buttons(self):
        flags = self.windowFlags()
        flags |= Qt.Window
        flags |= Qt.WindowCloseButtonHint
        flags |= Qt.WindowMinMaxButtonsHint
        self.setWindowFlags(flags)


    def closeEvent(self, event):
        try:
            if self.crawl_thread is not None and self.crawl_thread.isRunning():
                reply = QMessageBox.question(
                    self,
                    "종료 확인",
                    "크롤링이 실행 중입니다. 종료할까요?",
                )
                if reply != QMessageBox.Yes:
                    event.ignore()
                    return
                if self.crawl_worker is not None:
                    self.crawl_worker.cancel()
        except Exception:
            pass
        event.accept()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)

        title = QLabel("연세대학교 의과대학 교수명단 편집기")
        title.setStyleSheet("font-size: 20px; font-weight: bold;")
        root.addWidget(title)

        self.db_label = QLabel(f"DB 경로: {DB_PATH}")
        self.db_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.db_label)

        search_wrap = QWidget()
        search_grid = QGridLayout(search_wrap)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("이름 검색")

        self.department_combo = QComboBox()
        self.department_combo.addItem("전체")

        self.email_only_check = QCheckBox("이메일 있는 교수만")

        self.search_btn = QPushButton("검색")
        self.search_btn.clicked.connect(self.search)

        self.refresh_btn = QPushButton("새로고침")
        self.refresh_btn.clicked.connect(self.refresh_data)

        self.add_btn = QPushButton("행 추가")
        self.add_btn.clicked.connect(self.add_record)

        self.delete_btn = QPushButton("선택 행 삭제")
        self.delete_btn.clicked.connect(self.delete_selected_rows)

        self.save_btn = QPushButton("DB 저장")
        self.save_btn.clicked.connect(self.save_changes)

        self.export_btn = QPushButton("CSV 내보내기")
        self.export_btn.clicked.connect(self.export_csv)

        self.close_btn = QPushButton("닫기")
        self.close_btn.clicked.connect(self.close)

        self.crawl_button = QPushButton("크롤링 실행")
        self.crawl_button.clicked.connect(self.start_crawl)

        self.stop_crawl_button = QPushButton("중단")
        self.stop_crawl_button.clicked.connect(self.stop_crawl)
        self.stop_crawl_button.setEnabled(False)

        self.headless_check = QCheckBox("헤드리스")
        self.headless_check.setChecked(True)

        self.test_mode_check = QCheckBox("테스트 모드")
        self.test_mode_check.setChecked(True)
        self.test_mode_check.toggled.connect(self.on_toggle_test_mode)

        self.external_enrichment_check = QCheckBox("외부 보강 사용")
        self.external_enrichment_check.setChecked(True)

        self.enable_orcid_check = QCheckBox("ORCID 사용")
        self.enable_orcid_check.setChecked(True)

        self.crawl_limit_input = QLineEdit()
        self.crawl_limit_input.setPlaceholderText("학과 제한(0=전체)")
        self.crawl_limit_input.setText("1")
        self.crawl_limit_input.setFixedWidth(140)

        self.retries_input = QLineEdit()
        self.retries_input.setPlaceholderText("재시도")
        self.retries_input.setText("2")
        self.retries_input.setFixedWidth(80)

        self.wait_timeout_input = QLineEdit()
        self.wait_timeout_input.setPlaceholderText("대기 시간")
        self.wait_timeout_input.setText("20")
        self.wait_timeout_input.setFixedWidth(80)

        self.workers_input = QSpinBox()
        self.workers_input.setRange(1, 8)
        self.workers_input.setValue(2)
        self.workers_input.setFixedWidth(80)
        if os.name == "nt":
            self.workers_input.setValue(1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")

        self.progress_label = QLabel("대기 중")

        self.auto_update_check = QCheckBox("자동 업데이트")
        self.auto_update_interval = QSpinBox()
        self.auto_update_interval.setRange(1, 1440)
        self.auto_update_interval.setValue(60)
        self.auto_update_interval.setSuffix(" 분")

        self.auto_update_timer = QTimer(self)
        self.auto_update_timer.timeout.connect(self.run_scheduled_crawl)
        self.auto_update_check.toggled.connect(self.toggle_auto_update)

        self.orcid_btn = QPushButton("ORCID 설정")
        self.orcid_btn.clicked.connect(self.open_orcid_dialog)

        self.external_source_btn = QPushButton("외부 보강 URL 설정")
        self.external_source_btn.clicked.connect(self.open_external_source_dialog)

        search_grid.addWidget(QLabel("이름"), 0, 0)
        search_grid.addWidget(self.name_input, 0, 1)
        search_grid.addWidget(QLabel("학과"), 0, 2)
        search_grid.addWidget(self.department_combo, 0, 3)
        search_grid.addWidget(self.email_only_check, 0, 4)
        search_grid.addWidget(self.search_btn, 0, 5)
        search_grid.addWidget(self.refresh_btn, 0, 6)
        search_grid.addWidget(self.add_btn, 0, 7)
        search_grid.addWidget(self.delete_btn, 0, 8)
        search_grid.addWidget(self.save_btn, 0, 9)
        search_grid.addWidget(self.export_btn, 0, 10)
        search_grid.addWidget(self.close_btn, 0, 11)

        search_grid.addWidget(QLabel("크롤링"), 1, 0)
        search_grid.addWidget(self.crawl_button, 1, 1)
        search_grid.addWidget(self.stop_crawl_button, 1, 2)
        search_grid.addWidget(self.headless_check, 1, 3)
        search_grid.addWidget(self.test_mode_check, 1, 4)
        search_grid.addWidget(QLabel("학과 제한"), 1, 5)
        search_grid.addWidget(self.crawl_limit_input, 1, 6)
        search_grid.addWidget(self.external_enrichment_check, 1, 7)
        search_grid.addWidget(self.enable_orcid_check, 1, 8)
        search_grid.addWidget(self.orcid_btn, 1, 9)
        search_grid.addWidget(self.external_source_btn, 1, 10)

        search_grid.addWidget(QLabel("재시도"), 2, 0)
        search_grid.addWidget(self.retries_input, 2, 1)
        search_grid.addWidget(QLabel("대기 시간"), 2, 2)
        search_grid.addWidget(self.wait_timeout_input, 2, 3)
        search_grid.addWidget(QLabel("워커 수"), 2, 4)
        search_grid.addWidget(self.workers_input, 2, 5)
        search_grid.addWidget(self.auto_update_check, 2, 6)
        search_grid.addWidget(self.auto_update_interval, 2, 7)

        search_grid.addWidget(QLabel("진행률"), 3, 0)
        search_grid.addWidget(self.progress_bar, 3, 1, 1, 4)
        search_grid.addWidget(self.progress_label, 3, 5, 1, 5)

        root.addWidget(search_wrap)

        stats_wrap = QWidget()
        stats_layout = QHBoxLayout(stats_wrap)

        self.total_label = QLabel("교수 수: 0")
        self.email_label = QLabel("이메일 보유: 0")
        self.phone_label = QLabel("전화 보유: 0")
        self.changed_label = QLabel("변경 사항: 없음")

        for w in [self.total_label, self.email_label, self.phone_label, self.changed_label]:
            w.setStyleSheet("font-size: 14px; padding: 4px;")
            stats_layout.addWidget(w)

        stats_layout.addStretch(1)
        root.addWidget(stats_wrap)

        self.table = QTableWidget()
        self.table.setColumnCount(len(TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels([COLUMN_LABELS[c] for c in TABLE_COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.itemChanged.connect(self.on_item_changed)
        self.table.itemDoubleClicked.connect(self.on_item_double_clicked)
        root.addWidget(self.table)

        self.log_output = QPlainTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setPlaceholderText("크롤링 로그가 여기에 표시됩니다.")
        self.log_output.setMaximumBlockCount(2000)
        self.log_output.setMinimumHeight(180)
        root.addWidget(self.log_output)

        self.statusBar().showMessage("준비됨")

        menubar = self.menuBar()
        file_menu = menubar.addMenu("파일")

        act_save = QAction("DB 저장", self)
        act_save.triggered.connect(self.save_changes)
        file_menu.addAction(act_save)

        act_export = QAction("CSV 내보내기", self)
        act_export.triggered.connect(self.export_csv)
        file_menu.addAction(act_export)

        act_refresh = QAction("새로고침", self)
        act_refresh.triggered.connect(self.refresh_data)
        file_menu.addAction(act_refresh)

        act_crawl = QAction("크롤링 실행", self)
        act_crawl.triggered.connect(self.start_crawl)
        file_menu.addAction(act_crawl)

        act_orcid = QAction("ORCID 설정", self)
        act_orcid.triggered.connect(self.open_orcid_dialog)
        file_menu.addAction(act_orcid)

        act_external_source = QAction("외부 보강 URL 설정", self)
        act_external_source.triggered.connect(self.open_external_source_dialog)
        file_menu.addAction(act_external_source)

    def open_orcid_dialog(self):
        dlg = OrcidConfigDialog(self)
        dlg.exec()

    def open_external_source_dialog(self):
        dlg = ExternalSourceConfigDialog(self)
        dlg.exec()

    def _set_busy(self, busy: bool):
        widgets = [
            self.search_btn,
            self.refresh_btn,
            self.add_btn,
            self.delete_btn,
            self.save_btn,
            self.export_btn,
            self.crawl_button,
            self.workers_input,
            self.retries_input,
            self.wait_timeout_input,
            self.crawl_limit_input,
            self.headless_check,
            self.test_mode_check,
            self.external_enrichment_check,
            self.enable_orcid_check,
        ]
        for w in widgets:
            w.setEnabled(not busy)

        self.stop_crawl_button.setEnabled(busy)

    def update_progress(self, value: int):
        self.progress_bar.setValue(max(0, min(100, value)))

    def update_progress_detail(self, text: str):
        self.progress_label.setText(text)

    def append_log(self, message: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.appendPlainText(f"[{stamp}] {message}")

    def clear_log(self):
        self.log_output.clear()

    def stop_crawl(self):
        if self.crawl_worker is not None:
            self.crawl_worker.cancel()
            self.statusBar().showMessage("크롤링 중단 요청됨")

    def toggle_auto_update(self, checked: bool):
        if checked:
            minutes = self.auto_update_interval.value()
            self.auto_update_timer.start(minutes * 60 * 1000)
            next_run = datetime.now() + timedelta(minutes=minutes)
            self.statusBar().showMessage(f"자동 업데이트 시작. 다음 실행: {next_run:%Y-%m-%d %H:%M:%S}")
        else:
            self.auto_update_timer.stop()
            self.statusBar().showMessage("자동 업데이트 중지")

    def run_scheduled_crawl(self):
        if self.crawl_thread is not None and self.crawl_thread.isRunning():
            return
        self.start_crawl()

    def on_toggle_test_mode(self, checked: bool):
        self.crawl_limit_input.setEnabled(checked)
        if checked and not self.crawl_limit_input.text().strip():
            self.crawl_limit_input.setText("1")
        if not checked:
            self.crawl_limit_input.setText("0")
        if os.name == "nt" and not checked and self.workers_input.value() < 1:
            self.workers_input.setValue(1)

    def _connect_db(self):
        if not DB_PATH.exists():
            raise FileNotFoundError("DB 파일이 없습니다. 먼저 크롤링을 실행해 주세요.")
        return sqlite3.connect(DB_PATH)

    def _get_table_columns_from_db(self):
        conn = self._connect_db()
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(faculty)")
            cols = [row[1] for row in cur.fetchall()]
            return cols
        finally:
            conn.close()

    def _ensure_id_column_exists(self):
        db_columns = self._get_table_columns_from_db()
        if "id" not in db_columns:
            raise RuntimeError(
                "faculty 테이블에 id 컬럼이 없습니다.\n"
                "편집 저장 기능을 쓰려면 기본키 id가 필요합니다."
            )

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
            db_columns = self._get_table_columns_from_db()
            orcid_select = "orcid_id" if "orcid_id" in db_columns else "'' AS orcid_id"

            sql = f"""
            SELECT
                id,
                department_ko, department_en, name_ko, name_en, title_ko,
                email, {orcid_select}, phone, office, campus, detail_url, collected_at
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
            init_db()
            ensure_faculty_table_schema()
            try:
                self._ensure_id_column_exists()
            except Exception:
                pass
            dept_df = self.load_departments() if DB_PATH.exists() else pd.DataFrame(columns=["department_ko"])

            self.department_combo.clear()
            self.department_combo.addItem("전체")
            for dept in dept_df.get("department_ko", pd.Series(dtype=str)).fillna("").tolist():
                if dept:
                    self.department_combo.addItem(dept)

            self.search()
        except Exception as e:
            QMessageBox.critical(self, "초기화 오류", str(e))
            self.statusBar().showMessage("초기화 실패")

    def _normalize_value(self, value):
        if value is None:
            return ""
        return str(value).strip()

    def _mark_item_changed_style(self, item, changed: bool):
        if changed:
            item.setBackground(QBrush(QColor(255, 245, 204)))
        else:
            item.setBackground(QBrush())

    def _find_original_value(self, row: int, col_name: str):
        if self.original_df.empty or row >= len(self.original_df):
            return ""
        if col_name not in self.original_df.columns:
            return ""
        return self._normalize_value(self.original_df.at[row, col_name])

    def _refresh_row_styles(self, row: int):
        if row < 0 or row >= self.table.rowCount():
            return

        for col_idx, col_name in enumerate(TABLE_COLUMNS):
            item = self.table.item(row, col_idx)
            if item is None:
                continue

            if col_name == "id":
                self._mark_item_changed_style(item, False)
                continue

            current_value = self._normalize_value(item.text())
            original_value = self._find_original_value(row, col_name)
            self._mark_item_changed_style(item, current_value != original_value)

    def refresh_data(self):
        if self.dirty:
            reply = QMessageBox.question(
                self,
                "확인",
                "저장하지 않은 변경 사항이 있습니다. 그래도 새로고침할까요?",
            )
            if reply != QMessageBox.Yes:
                return

        self.search()
        self.statusBar().showMessage("새로고침 완료")

    def search(self):
        try:
            self.table.blockSignals(True)

            if not DB_PATH.exists():
                self.df = pd.DataFrame(columns=TABLE_COLUMNS)
                self.original_df = self.df.copy(deep=True)
                self._render_table(self.df)
                self._update_stats(self.df)
                self.statusBar().showMessage("DB가 아직 없어 빈 화면으로 시작합니다.")
                return

            name_keyword = self.name_input.text().strip()
            department_keyword = self.department_combo.currentText()
            has_email_only = self.email_only_check.isChecked()

            self.df = self.load_faculty(name_keyword, department_keyword, has_email_only).copy()
            self.original_df = self.df.copy(deep=True)

            self._render_table(self.df)
            self._update_stats(self.df)
            self.dirty = False
            self.changed_label.setText("변경 사항: 없음")
            self.statusBar().showMessage(f"검색 완료: {len(self.df)}건")
        except Exception as e:
            QMessageBox.critical(self, "검색 오류", str(e))
            self.statusBar().showMessage("검색 실패")
        finally:
            self.table.blockSignals(False)

    def _render_table(self, df: pd.DataFrame):
        self.table.setRowCount(0)

        if df.empty:
            return

        self.table.setRowCount(len(df))

        for row_idx, row in enumerate(df.itertuples(index=False)):
            for col_idx, col_name in enumerate(TABLE_COLUMNS):
                value = getattr(row, col_name) if hasattr(row, col_name) else ""
                text = "" if pd.isna(value) else str(value)
                item = QTableWidgetItem(text)

                if col_name not in EDITABLE_COLUMNS:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)

                if col_name == "id":
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setTextAlignment(Qt.AlignCenter)

                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeColumnsToContents()

        for row_idx in range(self.table.rowCount()):
            self._refresh_row_styles(row_idx)

            try:
                orcid_col = TABLE_COLUMNS.index("orcid_id")
                orcid_item = self.table.item(row_idx, orcid_col)
                if orcid_item is not None and orcid_item.text().strip():
                    orcid_item.setToolTip("더블클릭하면 ORCID 페이지가 열립니다.")
            except Exception:
                pass

            try:
                url_col = TABLE_COLUMNS.index("detail_url")
                url_item = self.table.item(row_idx, url_col)
                if url_item is not None and url_item.text().strip():
                    url_item.setToolTip("더블클릭하면 상세 페이지가 열립니다.")
            except Exception:
                pass

    def _update_stats(self, df: pd.DataFrame):
        total = len(df)
        email_cnt = int(df["email"].fillna("").astype(str).str.strip().ne("").sum()) if not df.empty and "email" in df else 0
        phone_cnt = int(df["phone"].fillna("").astype(str).str.strip().ne("").sum()) if not df.empty and "phone" in df else 0

        self.total_label.setText(f"교수 수: {total}")
        self.email_label.setText(f"이메일 보유: {email_cnt}")
        self.phone_label.setText(f"전화 보유: {phone_cnt}")

    def on_item_changed(self, item):
        row = item.row()
        col = item.column()
        col_name = TABLE_COLUMNS[col]
        value = item.text()

        if self.df.empty or row >= len(self.df):
            return

        self.df.at[row, col_name] = value
        self._refresh_row_styles(row)

        self.dirty = True
        self.changed_label.setText("변경 사항: 있음")

    def on_item_double_clicked(self, item):
        col_name = TABLE_COLUMNS[item.column()]
        value = item.text().strip()

        if col_name == "detail_url":
            if value.startswith("http://") or value.startswith("https://"):
                QDesktopServices.openUrl(QUrl(value))
            return

        if col_name == "orcid_id":
            if not value:
                return
            if value.startswith("http://") or value.startswith("https://"):
                QDesktopServices.openUrl(QUrl(value))
                return
            QDesktopServices.openUrl(QUrl(f"https://orcid.org/{value}"))

    def _is_valid_email(self, value: str) -> bool:
        value = (value or "").strip()
        if not value:
            return True
        return re.match(r"^[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}$", value, re.I) is not None

    def _is_valid_url(self, value: str) -> bool:
        value = (value or "").strip()
        if not value:
            return True
        return value.startswith("http://") or value.startswith("https://")

    def _validate_dataframe(self):
        errors = []

        if self.df.empty:
            return errors

        for idx, row in self.df.fillna("").iterrows():
            excel_row = idx + 1

            name_ko = str(row.get("name_ko", "")).strip()
            name_en = str(row.get("name_en", "")).strip()
            email = str(row.get("email", "")).strip()
            detail_url = str(row.get("detail_url", "")).strip()

            if not name_ko and not name_en:
                errors.append(f"{excel_row}행: 이름(한글/영문) 중 하나는 입력해야 합니다.")

            if email and not self._is_valid_email(email):
                errors.append(f"{excel_row}행: 이메일 형식이 올바르지 않습니다. ({email})")

            if detail_url and not self._is_valid_url(detail_url):
                errors.append(f"{excel_row}행: 상세 URL 형식이 올바르지 않습니다. ({detail_url})")

        return errors

    def _backup_database(self):
        db_path = Path(DB_PATH)
        if not db_path.exists():
            return None

        backup_dir = db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{db_path.stem}_backup_{timestamp}{db_path.suffix}"

        shutil.copy2(db_path, backup_path)
        return backup_path

    def add_record(self):
        dialog = AddFacultyDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        data = dialog.get_data()
        if not data["name_ko"] and not data["name_en"]:
            QMessageBox.warning(self, "입력 오류", "이름(한글 또는 영문)은 하나 이상 입력해 주세요.")
            return

        if data["email"] and not self._is_valid_email(data["email"]):
            QMessageBox.warning(self, "입력 오류", "이메일 형식이 올바르지 않습니다.")
            return

        if data["detail_url"] and not self._is_valid_url(data["detail_url"]):
            QMessageBox.warning(self, "입력 오류", "상세 URL은 http:// 또는 https:// 로 시작해야 합니다.")
            return

        new_row = {
            "id": "",
            "department_ko": data["department_ko"],
            "department_en": data["department_en"],
            "name_ko": data["name_ko"],
            "name_en": data["name_en"],
            "title_ko": data["title_ko"],
            "email": data["email"],
            "orcid_id": data["orcid_id"],
            "phone": data["phone"],
            "office": data["office"],
            "campus": data["campus"],
            "detail_url": data["detail_url"],
            "collected_at": "",
        }

        self.df = pd.concat([self.df, pd.DataFrame([new_row])], ignore_index=True)
        self._render_table(self.df)
        self._update_stats(self.df)

        for row_idx in range(self.table.rowCount()):
            self._refresh_row_styles(row_idx)

        self.dirty = True
        self.changed_label.setText("변경 사항: 있음")
        self.statusBar().showMessage("행 추가됨")

    def delete_selected_rows(self):
        selected_rows = sorted({idx.row() for idx in self.table.selectionModel().selectedRows()}, reverse=True)
        if not selected_rows:
            QMessageBox.information(self, "알림", "삭제할 행을 선택해 주세요.")
            return

        reply = QMessageBox.question(self, "확인", f"{len(selected_rows)}개 행을 삭제할까요?")
        if reply != QMessageBox.Yes:
            return

        for row in selected_rows:
            self.df = self.df.drop(index=row)

        self.df = self.df.reset_index(drop=True)
        self._render_table(self.df)
        self._update_stats(self.df)

        self.dirty = True
        self.changed_label.setText("변경 사항: 있음")
        self.statusBar().showMessage("선택 행 삭제됨")

    def _normalize_df_for_save(self, df: pd.DataFrame):
        out = df.copy()

        for col in TABLE_COLUMNS:
            if col not in out.columns:
                out[col] = ""

        for col in out.columns:
            out[col] = out[col].fillna("").astype(str)

        return out

    def _build_diff_text(self):
        lines = []

        current_df = self.df.copy()
        original_df = self.original_df.copy()

        for col in TABLE_COLUMNS:
            if col not in current_df.columns:
                current_df[col] = ""
            if col not in original_df.columns:
                original_df[col] = ""

        current_df = current_df.fillna("").astype(str)
        original_df = original_df.fillna("").astype(str)

        current_by_id = {}
        original_by_id = {}

        for _, row in current_df.iterrows():
            row_id = row.get("id", "").strip()
            if row_id:
                current_by_id[row_id] = row.to_dict()

        for _, row in original_df.iterrows():
            row_id = row.get("id", "").strip()
            if row_id:
                original_by_id[row_id] = row.to_dict()

        current_ids = set(current_by_id.keys())
        original_ids = set(original_by_id.keys())

        deleted_ids = sorted(original_ids - current_ids, key=lambda x: int(x) if str(x).isdigit() else str(x))
        added_rows = current_df[current_df["id"].astype(str).str.strip() == ""].to_dict("records")
        updated_ids = sorted(current_ids & original_ids, key=lambda x: int(x) if str(x).isdigit() else str(x))

        if added_rows:
            lines.append("[추가될 행]")
            for i, row in enumerate(added_rows, start=1):
                summary = f"- 신규 #{i}: {row.get('name_ko', '') or row.get('name_en', '')} / {row.get('department_ko', '')}"
                lines.append(summary)
            lines.append("")

        if deleted_ids:
            lines.append("[삭제될 행]")
            for row_id in deleted_ids:
                old = original_by_id[row_id]
                summary = f"- ID {row_id}: {old.get('name_ko', '') or old.get('name_en', '')} / {old.get('department_ko', '')}"
                lines.append(summary)
            lines.append("")

        changed_any = False
        for row_id in updated_ids:
            old = original_by_id[row_id]
            new = current_by_id[row_id]

            changed_fields = []
            for col in TABLE_COLUMNS:
                if col in {"id", "collected_at"}:
                    continue

                old_val = (old.get(col) or "").strip()
                new_val = (new.get(col) or "").strip()

                if old_val != new_val:
                    changed_fields.append((col, old_val, new_val))

            if changed_fields:
                changed_any = True
                title = f"[수정] ID {row_id} | {new.get('name_ko', '') or new.get('name_en', '')}"
                lines.append(title)
                for col, old_val, new_val in changed_fields:
                    label = COLUMN_LABELS.get(col, col)
                    lines.append(f"  - {label}: '{old_val}' -> '{new_val}'")
                lines.append("")

        if changed_any is False and not added_rows and not deleted_ids:
            return "변경된 내용이 없습니다."

        return "\n".join(lines).strip()

    def save_changes(self):
        try:
            validation_errors = self._validate_dataframe()
            if validation_errors:
                QMessageBox.warning(
                    self,
                    "입력 검증 오류",
                    "아래 내용을 확인하세요.\n\n" + "\n".join(validation_errors[:20])
                )
                self.statusBar().showMessage("입력 검증 실패")
                return

            diff_text = self._build_diff_text()
            if diff_text == "변경된 내용이 없습니다.":
                QMessageBox.information(self, "알림", diff_text)
                return

            preview = DiffPreviewDialog(diff_text, self)
            if preview.exec() != QDialog.Accepted:
                self.statusBar().showMessage("저장이 취소되었습니다.")
                return

            backup_path = self._backup_database()

            current = self._normalize_df_for_save(self.df)
            original = self._normalize_df_for_save(self.original_df)

            current_ids = set(current[current["id"].str.strip() != ""]["id"].tolist())
            original_ids = set(original[original["id"].str.strip() != ""]["id"].tolist())

            deleted_ids = original_ids - current_ids

            current_existing = current[current["id"].str.strip() != ""].copy()
            current_new = current[current["id"].str.strip() == ""].copy()

            conn = self._connect_db()
            try:
                cur = conn.cursor()

                for del_id in deleted_ids:
                    cur.execute("DELETE FROM faculty WHERE id = ?", (del_id,))

                db_columns = self._get_table_columns_from_db()
                has_orcid_column = "orcid_id" in db_columns

                for _, row in current_existing.iterrows():
                    if has_orcid_column:
                        cur.execute(
                            """
                            UPDATE faculty
                            SET
                                department_ko = ?,
                                department_en = ?,
                                name_ko = ?,
                                name_en = ?,
                                title_ko = ?,
                                email = ?,
                                orcid_id = ?,
                                phone = ?,
                                office = ?,
                                campus = ?,
                                detail_url = ?
                            WHERE id = ?
                            """,
                            (
                                row["department_ko"],
                                row["department_en"],
                                row["name_ko"],
                                row["name_en"],
                                row["title_ko"],
                                row["email"],
                                row["orcid_id"],
                                row["phone"],
                                row["office"],
                                row["campus"],
                                row["detail_url"],
                                row["id"],
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            UPDATE faculty
                            SET
                                department_ko = ?,
                                department_en = ?,
                                name_ko = ?,
                                name_en = ?,
                                title_ko = ?,
                                email = ?,
                                phone = ?,
                                office = ?,
                                campus = ?,
                                detail_url = ?
                            WHERE id = ?
                            """,
                            (
                                row["department_ko"],
                                row["department_en"],
                                row["name_ko"],
                                row["name_en"],
                                row["title_ko"],
                                row["email"],
                                row["phone"],
                                row["office"],
                                row["campus"],
                                row["detail_url"],
                                row["id"],
                            ),
                        )

                for _, row in current_new.iterrows():
                    if has_orcid_column:
                        cur.execute(
                            """
                            INSERT INTO faculty (
                                department_ko, department_en, name_ko, name_en, title_ko,
                                email, orcid_id, phone, office, campus, detail_url, collected_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                            """,
                            (
                                row["department_ko"],
                                row["department_en"],
                                row["name_ko"],
                                row["name_en"],
                                row["title_ko"],
                                row["email"],
                                row["orcid_id"],
                                row["phone"],
                                row["office"],
                                row["campus"],
                                row["detail_url"],
                            ),
                        )
                    else:
                        cur.execute(
                            """
                            INSERT INTO faculty (
                                department_ko, department_en, name_ko, name_en, title_ko,
                                email, phone, office, campus, detail_url, collected_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                            """,
                            (
                                row["department_ko"],
                                row["department_en"],
                                row["name_ko"],
                                row["name_en"],
                                row["title_ko"],
                                row["email"],
                                row["phone"],
                                row["office"],
                                row["campus"],
                                row["detail_url"],
                            ),
                        )

                conn.commit()

            finally:
                conn.close()

            self.original_df = self.df.copy(deep=True)
            self.dirty = False
            self.changed_label.setText("변경 사항: 없음")
            self.search()

            msg = "DB 저장 완료"
            if backup_path:
                msg += f"\n백업: {backup_path}"
            QMessageBox.information(self, "완료", msg)
            self.statusBar().showMessage("DB 저장 완료")

        except Exception as e:
            QMessageBox.critical(self, "저장 오류", str(e))
            self.statusBar().showMessage("저장 실패")

    def export_csv(self):
        if self.df.empty:
            QMessageBox.information(self, "알림", "내보낼 데이터가 없습니다.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "CSV 저장",
            str(DB_PATH.parent / "faculty_export.csv"),
            "CSV Files (*.csv)",
        )
        if not path:
            return

        try:
            self.df.to_csv(path, index=False, encoding="utf-8-sig")
            QMessageBox.information(self, "완료", f"CSV 저장 완료\n{path}")
            self.statusBar().showMessage("CSV 저장 완료")
        except Exception as e:
            QMessageBox.critical(self, "CSV 오류", str(e))

    def start_crawl(self):
        if self.crawl_thread is not None and self.crawl_thread.isRunning():
            QMessageBox.information(self, "알림", "이미 크롤링이 실행 중입니다.")
            return

        try:
            workers = int(self.workers_input.value())
            limit_departments = int((self.crawl_limit_input.text() or "0").strip())
            retries = int((self.retries_input.text() or "2").strip())
            wait_timeout = int((self.wait_timeout_input.text() or "20").strip())
        except ValueError:
            QMessageBox.warning(self, "입력 오류", "학과 제한, 재시도, 대기 시간은 숫자로 입력해 주세요.")
            return

        self.clear_log()
        self.append_log("크롤링 실행 요청")
        self.crawl_thread = QThread(self)
        self.crawl_worker = CrawlWorker(
            workers=workers,
            headless=self.headless_check.isChecked(),
            limit_departments=limit_departments,
            enable_external_enrichment=self.external_enrichment_check.isChecked(),
            enable_orcid=self.enable_orcid_check.isChecked(),
            retries=retries,
            wait_timeout=wait_timeout,
            test_mode=self.test_mode_check.isChecked(),
        )
        self.crawl_worker.moveToThread(self.crawl_thread)

        self.crawl_thread.started.connect(self.crawl_worker.run)
        self.crawl_worker.finished.connect(self.on_crawl_finished)
        self.crawl_worker.error.connect(self.on_crawl_error)
        self.crawl_worker.status.connect(self.statusBar().showMessage)
        self.crawl_worker.progress.connect(self.update_progress)
        self.crawl_worker.progress_detail.connect(self.update_progress_detail)

        self.crawl_worker.finished.connect(self.crawl_thread.quit)
        self.crawl_worker.error.connect(self.crawl_thread.quit)
        self.crawl_thread.finished.connect(self.crawl_thread.deleteLater)

        self._set_busy(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText("크롤링 시작")
        self.statusBar().showMessage("크롤링 시작")
        self.crawl_thread.start()

    def _cleanup_crawl_thread(self):
        if self.crawl_thread is not None:
            try:
                self.crawl_thread.quit()
                self.crawl_thread.wait(3000)
            except Exception:
                pass
        self.crawl_worker = None
        self.crawl_thread = None

    def on_crawl_finished(self, count: int):
        self._set_busy(False)
        self.progress_bar.setValue(100)
        self.progress_label.setText(f"완료: {count}건")
        self.append_log(f"크롤링 완료 콜백 수신: {count}건")
        self.statusBar().showMessage(f"크롤링 완료: {count}건")
        self.refresh_data()
        self._cleanup_crawl_thread()

    def on_crawl_error(self, message: str):
        self._set_busy(False)
        self.append_log("크롤링 실패 콜백 수신")
        self.append_log(message)
        self.statusBar().showMessage("크롤링 실패")
        QMessageBox.critical(self, "크롤링 오류", message)
        self._cleanup_crawl_thread()

# -------------------------------------------------------------------
# external enrichment URL 설정 파일
# -------------------------------------------------------------------
EXTERNAL_SOURCE_CONFIG_PATH = Path(__file__).resolve().parent / "external_sources.json"


def load_external_source_config():
    if not EXTERNAL_SOURCE_CONFIG_PATH.exists():
        return {
            "sources": [
                {
                    "name": "yonsei_medicine",
                    "base_url": "https://medicine.yonsei.ac.kr",
                    "search_paths": [
                        "/medicine/board/search.do?searchKeyword={query}",
                        "/search/search.do?query={query}",
                        "/search?query={query}",
                    ],
                },
                {
                    "name": "yonsei_health_system",
                    "base_url": "https://www.yuhs.or.kr",
                    "search_paths": [
                        "/search/search.do?query={query}",
                        "/search/result.do?keyword={query}",
                        "/search?query={query}",
                    ],
                },
                {
                    "name": "severance_hospital",
                    "base_url": "https://sev.iseverance.com",
                    "search_paths": [
                        "/search/search.do?query={query}",
                        "/search/result.do?keyword={query}",
                        "/search?query={query}",
                    ],
                },
            ]
        }

    try:
        with open(EXTERNAL_SOURCE_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sources": []}


def save_external_source_config(data: dict):
    with open(EXTERNAL_SOURCE_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ExternalSourceConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("외부 보강 URL 설정")
        self.resize(780, 520)

        cfg = load_external_source_config()
        sources = cfg.get("sources", [])

        layout = QVBoxLayout(self)

        help_label = QLabel(
            "외부 보강에 사용할 사이트 URL과 검색 경로를 등록합니다.\n"
            "search_paths는 줄바꿈으로 여러 개 입력할 수 있으며, {query} 자리표시자를 포함해야 합니다."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.rows = []

        for idx in range(3):
            source = sources[idx] if idx < len(sources) else {}
            box = QWidget()
            form = QFormLayout(box)

            name_input = QLineEdit(source.get("name", ""))
            base_url_input = QLineEdit(source.get("base_url", ""))

            search_paths_input = QPlainTextEdit()
            search_paths_input.setPlaceholderText("/search?query={query}")
            search_paths_input.setPlainText("\n".join(source.get("search_paths", [])))
            search_paths_input.setFixedHeight(110)

            form.addRow("이름", name_input)
            form.addRow("Base URL", base_url_input)
            form.addRow("Search Paths", search_paths_input)

            layout.addWidget(QLabel(f"[소스 {idx + 1}]"))
            layout.addWidget(box)

            self.rows.append({
                "name": name_input,
                "base_url": base_url_input,
                "search_paths": search_paths_input,
            })

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("저장")
        self.save_btn.clicked.connect(self.save_config)
        btn_row.addWidget(self.save_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        buttons.button(QDialogButtonBox.Close).clicked.connect(self.accept)
        layout.addWidget(buttons)

    def save_config(self):
        sources = []

        for row in self.rows:
            name = row["name"].text().strip()
            base_url = row["base_url"].text().strip()
            raw_paths = row["search_paths"].toPlainText().strip()

            if not name and not base_url and not raw_paths:
                continue

            if not name:
                QMessageBox.warning(self, "입력 오류", "소스 이름을 입력해 주세요.")
                return

            if not base_url.startswith("http://") and not base_url.startswith("https://"):
                QMessageBox.warning(self, "입력 오류", f"Base URL 형식이 올바르지 않습니다: {base_url}")
                return

            search_paths = [line.strip() for line in raw_paths.splitlines() if line.strip()]
            if not search_paths:
                QMessageBox.warning(self, "입력 오류", "search_paths를 1개 이상 입력해 주세요.")
                return

            for path in search_paths:
                if "{query}" not in path:
                    QMessageBox.warning(self, "입력 오류", f"search path에 {{query}}가 없습니다:\n{path}")
                    return

            sources.append({
                "name": name,
                "base_url": base_url.rstrip("/"),
                "search_paths": search_paths,
            })

        save_external_source_config({"sources": sources})
        QMessageBox.information(self, "완료", f"외부 보강 URL 설정 저장 완료\n{EXTERNAL_SOURCE_CONFIG_PATH}")


def main():
    configure_windows_multiprocessing()
    app = QApplication(sys.argv)
    window = FacultyEditorWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
