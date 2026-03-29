# desktop_editor_option_patch.py
# 적용 대상: desktop_editor.py
# 목적:
# - 테스트 모드 옵션 체크박스 추가
# - 외부 보강 사용 체크박스 추가
# - ORCID 사용 체크박스 추가
# - CrawlWorker / start_crawl 에 옵션 전달
#
# 사용 방법:
# 1) desktop_editor.py 상단 import에 필요한 함수/클래스를 확인
# 2) 아래 코드 블록의 해당 클래스/메서드로 교체
# 3) sync_faculty / crawler 쪽에 enable_external_enrichment, enable_orcid 인자가 연결되어 있어야 함

from PySide6.QtWidgets import QCheckBox, QLabel, QLineEdit

# ------------------------------------------------------------------
# 1. CrawlWorker 교체
# ------------------------------------------------------------------

class CrawlWorker(QObject):
    finished = Signal(int)
    error = Signal(str)
    status = Signal(str)
    progress = Signal(int)
    progress_detail = Signal(str)

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

    def run(self):
        try:
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

            records = crawl_all_parallel(
                headless=self.headless,
                workers=max(1, self.workers),
                existing_detail_urls=existing_detail_urls,
                limit_departments=effective_limit,
                recrawl=True,
                retries=max(1, self.retries),
                wait_timeout=max(5, self.wait_timeout),
                progress_callback=self._on_progress,
                cancel_check=lambda: self._cancel_requested,
                enable_external_enrichment=self.enable_external_enrichment,
                enable_orcid=self.enable_orcid,
            )

            if self._cancel_requested:
                raise RuntimeError("사용자 요청으로 중단되었습니다.")

            self.progress.emit(90)
            self.progress_detail.emit(f"DB 저장 준비: {len(records)}건")
            self.status.emit("DB 저장 중...")
            save_to_db(records)

            self.progress.emit(100)
            self.progress_detail.emit(f"완료: {len(records)}건")
            self.finished.emit(len(records))
        except Exception as e:
            self.error.emit(str(e))


# ------------------------------------------------------------------
# 2. FacultyEditorWindow._build_ui 내 추가 위젯
#    기존 crawl 관련 위젯 생성 구간에 아래 항목을 추가
# ------------------------------------------------------------------

def build_ui_crawl_option_widgets(self):
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
    self.retries_input.setFixedWidth(90)

    self.wait_timeout_input = QLineEdit()
    self.wait_timeout_input.setPlaceholderText("대기 시간")
    self.wait_timeout_input.setText("20")
    self.wait_timeout_input.setFixedWidth(90)


# ------------------------------------------------------------------
# 3. FacultyEditorWindow._build_ui 레이아웃 추가 예시
#    기존 search_grid.addWidget(...) crawl 영역에 추가
# ------------------------------------------------------------------

def bind_crawl_option_widgets(self, search_grid):
    search_grid.addWidget(QLabel("크롤링"), 1, 0)
    search_grid.addWidget(self.crawl_button, 1, 1)
    search_grid.addWidget(self.stop_crawl_button, 1, 2)
    search_grid.addWidget(self.headless_check, 1, 3)
    search_grid.addWidget(self.test_mode_check, 1, 4)
    search_grid.addWidget(QLabel("학과 제한"), 1, 5)
    search_grid.addWidget(self.crawl_limit_input, 1, 6)
    search_grid.addWidget(self.external_enrichment_check, 1, 7)
    search_grid.addWidget(self.enable_orcid_check, 1, 8)

    search_grid.addWidget(QLabel("재시도"), 2, 0)
    search_grid.addWidget(self.retries_input, 2, 1)
    search_grid.addWidget(QLabel("대기 시간"), 2, 2)
    search_grid.addWidget(self.wait_timeout_input, 2, 3)
    search_grid.addWidget(self.auto_update_check, 2, 4)
    search_grid.addWidget(self.auto_update_interval, 2, 5)
    search_grid.addWidget(self.orcid_btn, 2, 6)

    search_grid.addWidget(QLabel("진행률"), 3, 0)
    search_grid.addWidget(self.progress_bar, 3, 1, 1, 4)
    search_grid.addWidget(self.progress_label, 3, 5, 1, 4)


# ------------------------------------------------------------------
# 4. FacultyEditorWindow 에 메서드 추가
# ------------------------------------------------------------------

def on_toggle_test_mode(self, checked: bool):
    self.crawl_limit_input.setEnabled(checked)
    if checked and not self.crawl_limit_input.text().strip():
        self.crawl_limit_input.setText("1")
    if not checked:
        self.crawl_limit_input.setText("0")


# ------------------------------------------------------------------
# 5. FacultyEditorWindow.start_crawl 교체
# ------------------------------------------------------------------

def start_crawl(self):
    if self.crawl_thread is not None and self.crawl_thread.isRunning():
        QMessageBox.information(self, "알림", "이미 크롤링이 실행 중입니다.")
        return

    try:
        workers = 1
        limit_departments = int((self.crawl_limit_input.text() or "0").strip())
        retries = int((self.retries_input.text() or "2").strip())
        wait_timeout = int((self.wait_timeout_input.text() or "20").strip())
    except ValueError:
        QMessageBox.warning(self, "입력 오류", "학과 제한, 재시도, 대기 시간은 숫자로 입력해 주세요.")
        return

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


# ------------------------------------------------------------------
# 6. FacultyEditorWindow.on_crawl_finished / on_crawl_error 가 없다면 추가
# ------------------------------------------------------------------

def on_crawl_finished(self, count: int):
    self._set_busy(False)
    self.progress_bar.setValue(100)
    self.progress_label.setText(f"완료: {count}건")
    self.statusBar().showMessage(f"크롤링 완료: {count}건")
    self.refresh_data()
    self.crawl_worker = None
    self.crawl_thread = None


def on_crawl_error(self, message: str):
    self._set_busy(False)
    self.statusBar().showMessage("크롤링 실패")
    QMessageBox.critical(self, "크롤링 오류", message)
    self.crawl_worker = None
    self.crawl_thread = None


# ------------------------------------------------------------------
# 7. _build_ui 에 실제 연결 예시
# ------------------------------------------------------------------
#
# self.build_ui_crawl_option_widgets()
# ...
# self.bind_crawl_option_widgets(search_grid)
#
# 위 두 줄을 _build_ui 내부에 맞게 연결하면 됨.
#
# 만약 기존 _build_ui 를 직접 수정할 경우:
# - 기존 crawl_limit_input 생성부를 유지하되
# - test_mode_check / external_enrichment_check / enable_orcid_check
#   / retries_input / wait_timeout_input 만 추가해도 충분함.
