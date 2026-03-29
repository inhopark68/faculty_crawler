import unittest
from unittest.mock import patch

from app import crawler


class DummyDriver:
    def __init__(self):
        self.page_source = "<html><body></body></html>"
        self.current_url = "http://example.com"

    def find_elements(self, by=None, value=None):
        return []

    def get(self, url):
        self.current_url = url

    def quit(self):
        pass


class DummyWait:
    def until(self, condition):
        return True


class TestCrawlFlow(unittest.TestCase):
    @patch("app.crawler.WebDriverWait", side_effect=lambda *args, **kwargs: DummyWait())
    @patch("app.crawler.safe_get", return_value=None)
    @patch(
        "app.crawler._snapshot_anchors",
        return_value=[
            {"href": "http://example.com/detail/1?mode=view&depMember.do", "text": "홍길동 Professor hong@example.com"},
            {"href": "mailto:hong@example.com", "text": "hong@example.com"},
        ],
    )
    def test_parse_department_page_with_mocked_helpers(
        self,
        mock_snapshot_anchors,
        mock_safe_get,
        mock_wait,
    ):
        driver = DummyDriver()
        driver.page_source = '''
        <html>
          <body>
            <div>E-mail : hong@example.com</div>
            <div>Tel : 02-1234-5678</div>
            <div>Office : A동 301호</div>
            <div>Campus : Sinchon</div>
            <div>Department : Anatomy</div>
          </body>
        </html>
        '''

        dept_meta = {
            "college_ko": "의과대학",
            "college_en": "College of Medicine",
            "department_ko": "해부학교실",
            "department_en": "Anatomy",
            "department_url": "http://example.com/department",
        }

        records = crawler.parse_department_page(
            driver=driver,
            dept_meta=dept_meta,
            existing_detail_urls=set(),
            retries=1,
            wait_timeout=1,
            recrawl=False,
            cancel_check=lambda: False,
            detail_progress_callback=None,
            orcid_token="",
        )

        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual(r.email, "hong@example.com")
        self.assertEqual(r.phone, "02-1234-5678")
        self.assertEqual(r.office, "A동 301호")
        self.assertEqual(r.department_en, "Anatomy")

    def test_crawl_progress_cancelled(self):
        progress = crawler.CrawlProgress(
            total_departments=3,
            progress_callback=None,
            cancel_check=lambda: True,
        )

        with self.assertRaises(crawler.CrawlCancelled):
            progress.check_cancelled()

    def test_parse_department_page_cancelled_early(self):
        driver = DummyDriver()

        dept_meta = {
            "college_ko": "의과대학",
            "college_en": "College of Medicine",
            "department_ko": "해부학교실",
            "department_en": "Anatomy",
            "department_url": "http://example.com/department",
        }

        with self.assertRaises(crawler.CrawlCancelled):
            crawler.parse_department_page(
                driver=driver,
                dept_meta=dept_meta,
                cancel_check=lambda: True,
            )

    @patch("app.crawler.get_orcid_access_token", return_value="")
    @patch("app.crawler.parse_index_for_medicine_departments")
    @patch("app.crawler.crawl_department_chunk", return_value=[])
    @patch("app.crawler.make_driver")
    def test_crawl_all_parallel_flow(
        self,
        mock_make_driver,
        mock_crawl_department_chunk,
        mock_parse_index,
        mock_get_orcid,
    ):
        mock_make_driver.return_value = DummyDriver()
        mock_parse_index.return_value = [
            {
                "college_ko": "의과대학",
                "college_en": "College of Medicine",
                "department_ko": "해부학교실",
                "department_en": "Anatomy",
                "department_url": "http://example.com/department/1",
            }
        ]

        progress_calls = []

        def progress(percent, message):
            progress_calls.append((percent, message))

        result = crawler.crawl_all_parallel(
            headless=True,
            workers=1,
            limit_departments=1,
            progress_callback=progress,
            cancel_check=lambda: False,
        )

        self.assertIsInstance(result, list)
        self.assertTrue(any(p == 1 for p, _ in progress_calls))
        self.assertTrue(any(p == 10 for p, _ in progress_calls))


if __name__ == "__main__":
    unittest.main()
