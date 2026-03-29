from dataclasses import dataclass


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
    orcid_id: str = ""
    orcid_url: str = ""
    external_source_url: str = ""
