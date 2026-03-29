import unittest

from app.crawler import _score_orcid_candidate


class TestOrcidScoring(unittest.TestCase):
    def test_score_orcid_candidate_email_match(self):
        candidate = {
            "person": {
                "emails": {
                    "email": [
                        {"email": "prof@example.com"}
                    ]
                },
                "name": {
                    "given-names": {"value": "Gil Dong"},
                    "family-name": {"value": "Hong"},
                },
            },
            "activities-summary": {},
        }

        score = _score_orcid_candidate(
            candidate=candidate,
            name_en="Gil Dong Hong",
            email="prof@example.com",
            department_en="Anatomy",
        )
        self.assertGreaterEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
