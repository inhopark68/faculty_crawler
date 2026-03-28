BASE_URL = "https://ee.yonsei.ac.kr"
INDEX_URL = f"{BASE_URL}/faculty/dep_search.do"

DEFAULT_DB_PATH = "output/yonsei_medicine_faculty.db"
DEFAULT_CSV_PATH = "output/yonsei_medicine_faculty.csv"
DEFAULT_XLSX_PATH = "output/yonsei_medicine_faculty.xlsx"
DEFAULT_LOG_PATH = "logs/crawler.log"

HEADLESS = True
PAGE_LOAD_SLEEP = 1.0
DETAIL_PAGE_SLEEP = 0.8
DETAIL_RETRY_COUNT = 3
