import re


def clean_text(v: str) -> str:
    if not v:
        return ""
    return re.sub(r"\s+", " ", v).strip()


def normalize_email(v: str) -> str:
    v = clean_text(v).upper()
    if not v:
        return ""

    v = v.replace("@YUHS.AC@YONSEI.AC.KR", "@YUHS.AC.KR")
    v = v.replace("@YONSEI.AC@YONSEI.AC.KR", "@YONSEI.AC.KR")
    v = v.replace(" ", "").replace(";", "").replace(",", "")
    return v


def normalize_phone(v: str) -> str:
    v = clean_text(v)
    if not v:
        return ""
    m = re.search(r"(\+?\d[\d\-\)\(\s]{6,}\d)", v)
    return clean_text(m.group(1)) if m else v


def split_department_label(label: str):
    parts = [clean_text(x) for x in label.split("/") if clean_text(x)]
    if len(parts) >= 2:
        return parts[0], parts[1]
    return label, ""


def parse_name_line(line: str):
    line = clean_text(line)
    if not line:
        return "", ""

    m = re.match(r"^([가-힣·\s]+)\s+([A-Za-z][A-Za-z ,.'\-]*)$", line)
    if m:
        return clean_text(m.group(1)), clean_text(m.group(2))

    if re.search(r"[가-힣]", line) and not re.search(r"[A-Za-z]", line):
        return line, ""
    if re.search(r"[A-Za-z]", line) and not re.search(r"[가-힣]", line):
        return "", line

    return line, ""


def extract_labeled_value(text: str, label: str) -> str:
    m = re.search(rf"{re.escape(label)}\s*:\s*(.+)", text, flags=re.IGNORECASE)
    return clean_text(m.group(1)) if m else ""
