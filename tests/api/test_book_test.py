"""Booking a single test from a plain request ("do the ECG test")."""
from datetime import date, timedelta

import pytest

from ai.classifier import classify_rules
from tests.conftest import ask, auth


def test_do_the_ecg_test_proposes_a_booking(client, reseed):
    r = ask(client, "rahul", "do the Electrocardiogram (ECG) test")
    assert r["intent"] == "action" and r["status"] == "ok" and r["mode"] == "workflow"
    assert "pending order for Electrocardiogram (ECG)" in r["answer"]
    plan = r["action_required"]
    assert plan["type"] == "confirm_plan" and len(plan["items"]) == 1
    assert plan["items"][0]["label"] == "Book Electrocardiogram (ECG)"
    res = client.post("/actions/confirm", json={"pending_action_id": plan["pending_action_id"]},
                      headers=auth(client, "rahul"))
    assert res.status_code == 200
    again = ask(client, "rahul", "book my ECG")
    assert "already booked" in again["answer"] and again["action_required"] is None


def test_requested_day_is_used(client, reseed):
    r = ask(client, "rahul", "Book my chest x-ray tomorrow")
    tomorrow = date.today() + timedelta(days=1)
    if tomorrow.weekday() == 6:
        pytest.skip("no diagnostic slots on Sundays")
    assert tomorrow.strftime("%d %b %Y") in r["answer"]
    assert r["action_required"]["items"][0]["label"] == "Book Chest X-ray"


def test_completed_test_is_not_booked_again(client):
    r = ask(client, "rahul", "I need a CBC test")
    assert "already completed" in r["answer"] and r["action_required"] is None


def test_no_order_means_ask_your_doctor(client):
    r = ask(client, "asha", "do the ECG test")
    assert "ask your doctor to order it" in r["answer"] and r["action_required"] is None


def test_staff_cannot_book_for_patients(client):
    r = ask(client, "staff1", "book an ECG test")
    assert r["action_required"] is None and "patients" in r["answer"]


@pytest.mark.parametrize("q,booking", [
    ("do the Electrocardiogram (ECG) test", True),
    ("Please book my chest x-ray", True),
    ("I need an MRI", True),
    ("How do I schedule an MRI scan?", False),
    ("What were my CBC results?", False),
    ("Which pre-op tests do I still need before my operation?", False),
    ("Is an ECG covered by my insurance?", False),
    ("Do you have treatment information for proton beam therapy?", False),
])
def test_booking_vs_question(q, booking):
    assert (classify_rules(q).get("route") == "book_test") is booking
