import unittest
from types import SimpleNamespace

from app.crawler import deduplicate


def make_record(
    name_ko="",
    name_en="",
    department_en="",
    email="",
    phone="",
    office="",
    detail_url="",
):
    return SimpleNamespace(
        name_ko=name_ko,
        name_en=name_en,
        department_en=department_en,
        email=email,
        phone=phone,
        office=office,
        detail_url=detail_url,
    )


class TestDeduplicate(unittest.TestCase):
    def test_deduplicate_by_full_key(self):
        r1 = make_record(name_ko="홍길동", email="a@example.com", detail_url="http://x/1")
        r2 = make_record(name_ko="홍길동", email="a@example.com", detail_url="http://x/1")

        result = deduplicate([r1, r2])
        self.assertEqual(len(result), 1)

    def test_deduplicate_keep_different_detail_url_current_behavior(self):
        r1 = make_record(
            name_ko="홍길동",
            name_en="Gil Dong Hong",
            department_en="Anatomy",
            email="a@example.com",
            detail_url="http://x/1",
        )
        r2 = make_record(
            name_ko="홍길동",
            name_en="Gil Dong Hong",
            department_en="Anatomy",
            email="a@example.com",
            detail_url="http://x/2",
        )

        result = deduplicate([r1, r2])
        self.assertEqual(len(result), 2)

    def test_deduplicate_keep_different_people(self):
        r1 = make_record(name_ko="홍길동", email="a@example.com", detail_url="http://x/1")
        r2 = make_record(name_ko="김철수", email="b@example.com", detail_url="http://x/2")

        result = deduplicate([r1, r2])
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
