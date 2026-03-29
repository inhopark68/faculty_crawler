    
from pathlib import Path
import json

EXTERNAL_SOURCE_CONFIG_PATH = Path(__file__).resolve().parents[1] / "external_sources.json"

DEFAULT_EXTERNAL_PROFILE_SOURCES = [
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


def load_external_profile_sources():
    if EXTERNAL_SOURCE_CONFIG_PATH.exists():
        try:
            with open(EXTERNAL_SOURCE_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                sources = data.get("sources", [])
                if isinstance(sources, list) and sources:
                    return sources
        except Exception:
            pass
    return DEFAULT_EXTERNAL_PROFILE_SOURCES


EXTERNAL_PROFILE_SOURCES = load_external_profile_sources()

