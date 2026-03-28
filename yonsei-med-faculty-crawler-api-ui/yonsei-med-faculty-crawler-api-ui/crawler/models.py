from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FacultyRecord:
    college_ko: str = ""
    college_en: str = ""
    department_ko: str = ""
    department_en: str = ""
    campus: str = ""
    name_ko: str = ""
    name_en: str = ""
    title_ko: str = ""
    email: str = ""
    phone: str = ""
    office: str = ""
    detail_url: str = ""
    source_department_url: str = ""
    collected_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
