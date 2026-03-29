import unittest

from bs4 import BeautifulSoup

from app.crawler import (
    _extract_email_fallback,
    _extract_phone_fallback,
    _extract_office_fallback,
    _clean_lines,
    _extract_labeled,
)


class TestDepartmentParsingHelpers(unittest.TestCase):
    def test_extract_labeled_email(self):
        lines = [
            "Department : Anatomy",
            "E-mail : prof@example.com",
        ]
        self.assertEqual(_extract_labeled(lines, "E-mail"), "prof@example.com")

    def test_extract_email_fallback_from_html(self):
        html = "<html><body>Contact: prof@example.com</body></html>"
        lines = []

        email = _extract_email_fallback(html, lines)
        self.assertEqual(email, "prof@example.com")

    def test_extract_email_fallback_from_lines(self):
        html = "<html><body>No email here</body></html>"
        lines = ["문의: prof@example.com"]

        email = _extract_email_fallback(html, lines)
        self.assertEqual(email, "prof@example.com")

    def test_extract_phone_fallback(self):
        lines = ["문의 02-1234-5678"]
        phone = _extract_phone_fallback(lines)
        self.assertEqual(phone, "02-1234-5678")

    def test_extract_office_fallback(self):
        lines = ["AB building 301호", "기타 정보"]
        office = _extract_office_fallback(lines)
        self.assertEqual(office, "AB building 301호")

    def test_clean_lines_remove_noise_and_duplicates(self):
        lines = ["Login", "홍길동", "홍길동", "", "교수"]
        cleaned = _clean_lines(lines)
        self.assertEqual(cleaned, ["홍길동", "교수"])


if __name__ == "__main__":
    unittest.main()
