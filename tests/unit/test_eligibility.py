"""Every branch of the deterministic eligibility engine (PDF Member 2, Step 7)."""
from datetime import date, timedelta

import pytest

from backend.app.db import db_session
from backend.app.models import Patient
from backend.app.tools.eligibility import check_coverage, resolve_procedure

CTX = {"user_id": 1, "role": "patient"}


def run(patient_id, text):
    with db_session() as db:
        return check_coverage(db, patient_id, CTX, procedure_name=text)


def test_covered_with_prior_auth_and_cost():
    d = run("P001", "knee replacement")
    assert d["covered"] is True and d["coverage_pct"] == 80 and d["prior_auth_required"] is True
    assert d["est_patient_cost"] == 350000 * 20 // 100 + 5000
    assert d["rule_id"] == "R-G-27447" and d["plan_doc_ref"] == "INS-GOLD-001 §4"


def test_covered_without_prior_auth():
    d = run("P001", "MRI")
    assert d["covered"] is True and d["prior_auth_required"] is False and d["coverage_pct"] == 90


def test_not_covered_exclusion():
    d = run("P001", "rhinoplasty")
    assert d["covered"] is False and "Cosmetic" in d["reasons"][0] and d["rule_id"] == "R-G-15780"


def test_not_covered_on_basic():
    d = run("P002", "total knee arthroplasty")
    assert d["covered"] is False and "not covered" in d["reasons"][0]


def test_expired_policy():
    d = run("P004", "knee replacement")
    assert d["covered"] is False and "expired" in d["reasons"][0]


def test_waiting_period():
    d = run("P003", "knee replacement")
    assert d["covered"] is False and "waiting period of 730 days" in d["reasons"][0]


def test_policy_not_started_yet():
    with db_session() as db:
        p = db.get(Patient, "P001")
        original = p.coverage_start
        p.coverage_start = date.today() + timedelta(days=3)
        db.commit()
        try:
            d = check_coverage(db, "P001", CTX, procedure_name="mri")
        finally:
            p.coverage_start = original
            db.commit()
    assert d["covered"] is False and "starts on" in d["reasons"][0]


def test_unknown_procedure():
    d = run("P001", "teleportation therapy")
    assert d["covered"] is None and "not recognised" in d["reasons"][0]


def test_deterministic():
    assert run("P001", "knee replacement") == run("P001", "knee replacement")


@pytest.mark.parametrize("text,code", [
    ("27447", "27447"), ("Am I covered for gallbladder removal?", "47562"), ("cabg", "33533"),
    ("is cosmetic surgery covered", "15780"), ("hernia operation", "49505"),
])
def test_resolve_procedure(text, code):
    with db_session() as db:
        assert resolve_procedure(db, text).code == code
