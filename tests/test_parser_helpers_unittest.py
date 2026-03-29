import unittest

from app.crawler import (
    _extract_orcid_from_text,
    _extract_title_ko,
    _parse_inline_fields,
)


class TestParserHelpers(unittest.TestCase):
    def test_extract_orcid_from_text_url(self):
        oid, url = _extract_orcid_from_text(
            "Profile: https://orcid.org/0000-0002-1825-0097"
        )
        self.assertEqual(oid, "0000-0002-1825-0097")
        self.assertEqual(url, "https://orcid.org/0000-0002-1825-0097")

    def test_extract_orcid_from_text_plain_id(self):
        oid, url = _extract_orcid_from_text("ORCID 0000-0002-1825-0097")
        self.assertEqual(oid, "0000-0002-1825-0097")
        self.assertEqual(url, "https://orcid.org/0000-0002-1825-0097")

    def test_extract_orcid_from_text_not_found(self):
        oid, url = _extract_orcid_from_text("No orcid here")
        self.assertEqual(oid, "")
        self.assertEqual(url, "")

    def test_extract_title_ko_korean(self):
        self.assertEqual(_extract_title_ko("홍길동 교수"), "교수")

    def test_extract_title_ko_english_associate(self):
        self.assertEqual(_extract_title_ko("John Doe Associate Professor"), "부교수")

    def test_extract_title_ko_english_assistant(self):
        self.assertEqual(_extract_title_ko("Jane Smith Assistant Professor"), "조교수")

    def test_extract_title_ko_not_found(self):
        self.assertEqual(_extract_title_ko("No title text"), "")

    def test_parse_inline_fields_with_title_and_email(self):
        result = _parse_inline_fields("홍길동 Professor hong@example.com")
        self.assertEqual(result["email"], "hong@example.com")
        self.assertEqual(result["title_ko"], "교수")

    def test_parse_inline_fields_name_only_current_behavior(self):
        result = _parse_inline_fields("의과대학")
        self.assertIn("name_ko", result)
        self.assertIn("name_en", result)
        self.assertIn("title_ko", result)
        self.assertIn("email", result)


if __name__ == "__main__":
    unittest.main()
