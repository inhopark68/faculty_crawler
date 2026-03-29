import re
from typing import Tuple


def clean_text(text: str) -> str:
    if text is None:
        return ""
    text = str(text).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_email(email: str) -> str:
    email = clean_text(email).lower()
    return email


def normalize_phone(phone: str) -> str:
    phone = clean_text(phone)
    phone = re.sub(r"[^\d\-+() ]", "", phone)
    phone = re.sub(r"\s+", " ", phone).strip()
    return phone


def split_department_label(text: str) -> Tuple[str, str]:
    text = clean_text(text)
    m = re.match(r"^(.*?)([A-Za-z].*)$", text)
    if m:
        return clean_text(m.group(1)), clean_text(m.group(2))
    return text, ""