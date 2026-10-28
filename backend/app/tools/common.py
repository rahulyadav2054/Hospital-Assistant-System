import json
import re
from datetime import datetime

from ..models import Department


class NotFound(Exception):
    """Raised when a tool finds no matching record (also used to avoid revealing other patients' data)."""


class ActionError(Exception):
    """A confirm/cancel failure that maps to an HTTP status (404, 409, 410 ...)."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def fmt_dt(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M")


def fmt_num(v: float) -> str:
    return f"{v:g}"


def _contains_word(text: str, phrase: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def resolve_departments(db, text: str | None) -> list[Department]:
    """Map free text ('cardiology', 'heart', 'my knee') to departments. Exact names win over keywords."""
    if not text:
        return []
    t = text.lower()
    depts = db.query(Department).all()
    by_name = [d for d in depts if _contains_word(t, d.name.lower()) or t.strip() == d.id.lower()]
    if by_name:
        return by_name
    hits = []
    for d in depts:
        if any(_contains_word(t, k) for k in json.loads(d.keywords)):
            hits.append(d)
    return hits


def resolve_department(db, text: str | None) -> Department | None:
    hits = resolve_departments(db, text)
    return hits[0] if hits else None


# Common patient phrasings -> canonical lab test names (longest phrase is matched first).
TEST_SYNONYMS = {
    "fasting blood sugar": "Fasting Glucose", "fasting sugar": "Fasting Glucose", "fasting glucose": "Fasting Glucose",
    "blood sugar": "Glucose", "sugar": "Glucose", "glucose": "Glucose",
    "hba1c": "HbA1c", "hb a1c": "HbA1c", "a1c": "HbA1c", "glycated": "HbA1c",
    "cholesterol": "Cholesterol", "lipid": "Cholesterol",
    "haemoglobin": "Hemoglobin", "hemoglobin": "Hemoglobin", "hb": "Hemoglobin",
    "complete blood count": "CBC", "cbc": "CBC", "blood count": "CBC",
    "platelets": "Platelet", "platelet": "Platelet",
    "wbc": "White Blood Cell", "white blood cell": "White Blood Cell",
    "creatinine": "Creatinine", "kidney": "Creatinine",
}


def normalize_test(name: str | None) -> str | None:
    if not name:
        return None
    t = name.lower()
    for phrase in sorted(TEST_SYNONYMS, key=len, reverse=True):
        if _contains_word(t, phrase):
            return TEST_SYNONYMS[phrase]
    return None
