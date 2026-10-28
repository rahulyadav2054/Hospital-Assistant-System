"""Endpoint contracts: health, login, /me, /sources, and the two-phase action flow edge cases."""
from datetime import datetime, timedelta

from backend.app.db import db_session
from backend.app.models import PendingAction, Slot
from tests.conftest import ask, auth


def test_health(client):
    r = client.get("/health").json()
    assert r["ok"] is True and r["ai_mode"] == "offline"


def test_login_returns_user(client):
    r = client.post("/auth/login", json={"username": "Asha", "password": "demo123"}).json()
    assert r["user"] == {"id": r["user"]["id"], "username": "asha", "name": "Asha Verma", "role": "patient",
                         "patient_id": "P001"}


def test_profile(client):
    r = client.get("/me/profile", headers=auth(client, "asha")).json()
    assert r["plan"]["name"] == "CareShield Gold"


def test_me_appointments_and_pending_tests(client):
    appts = client.get("/me/appointments", headers=auth(client, "asha")).json()
    assert {a["appointment_id"] for a in appts} == {"APT-1042", "APT-1043", "APT-1044"}
    tests = client.get("/me/pending-tests", headers=auth(client, "rahul")).json()
    assert {t["order_id"] for t in tests} == {"ORD-503", "ORD-504"}
    assert client.get("/me/appointments", headers=auth(client, "staff1")).json() == []


def test_source_drawer(client):
    r = ask(client, "asha", "What are visiting hours for ICU patients?")
    ref = next(c["ref"] for c in r["citations"] if c["source_type"] == "document")
    chunk = client.get(f"/sources/{ref}", headers=auth(client, "asha")).json()
    assert chunk["doc_id"] == "POL-VIS-001" and "11:00" in chunk["text"]
    assert client.get("/sources/NOPE::0::0", headers=auth(client, "asha")).status_code == 404


def test_validation(client):
    r = client.post("/chat", json={"message": "", "session_id": "x"}, headers=auth(client, "asha"))
    assert r.status_code == 422
    r = client.post("/chat", json={"message": "hi", "session_id": "bad id with spaces"}, headers=auth(client, "asha"))
    assert r.status_code == 422


def test_long_message_friendly_error(client):
    r = ask(client, "asha", "a" * 2500)
    assert r["status"] == "error" and "2000" in r["answer"]


def _propose(client):
    return ask(client, "asha", "Reschedule my cardiology appointment")["action_required"]


def test_cancel_pending_action(client, reseed):
    pa = _propose(client)["pending_action_id"]
    r = client.post("/actions/cancel", json={"pending_action_id": pa}, headers=auth(client, "asha"))
    assert r.json() == {"status": "cancelled"}
    r = client.post("/actions/confirm", json={"pending_action_id": pa}, headers=auth(client, "asha"))
    assert r.status_code == 404


def test_confirm_twice(client, reseed):
    pa = _propose(client)["pending_action_id"]
    assert client.post("/actions/confirm", json={"pending_action_id": pa},
                       headers=auth(client, "asha")).status_code == 200
    assert client.post("/actions/confirm", json={"pending_action_id": pa},
                       headers=auth(client, "asha")).status_code == 404


def test_expired_confirmation(client, reseed):
    pa = _propose(client)["pending_action_id"]
    with db_session() as db:
        db.get(PendingAction, pa).expires_at = datetime.now() - timedelta(seconds=1)
        db.commit()
    r = client.post("/actions/confirm", json={"pending_action_id": pa}, headers=auth(client, "asha"))
    assert r.status_code == 410


def test_slot_taken_race(client, reseed):
    ar = _propose(client)
    with db_session() as db:
        slot = db.query(Slot).filter(Slot.doctor_id == "D01",
                                     Slot.start_time == datetime.fromisoformat(ar["new_start"])).one()
        slot.is_booked = True  # someone else booked it in the meantime
        db.commit()
    r = client.post("/actions/confirm", json={"pending_action_id": ar["pending_action_id"]},
                    headers=auth(client, "asha"))
    assert r.status_code == 409


def test_sidebar_refreshes_after_confirm(client, reseed):
    ar = _propose(client)
    client.post("/actions/confirm", json={"pending_action_id": ar["pending_action_id"]}, headers=auth(client, "asha"))
    appts = client.get("/me/appointments", headers=auth(client, "asha")).json()
    assert next(a for a in appts if a["appointment_id"] == "APT-1042")["start"] == ar["new_start"]
