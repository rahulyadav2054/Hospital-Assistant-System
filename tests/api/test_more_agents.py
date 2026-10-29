"""The six goal agents: routing, decisions, one-approval plans and the proactive notifications."""
from datetime import date, datetime, timedelta

import pytest

from ai.agents.base import parse_range
from ai.classifier import classify_rules
from backend.app.chat_ctx import ctx_for
from backend.app.tools.registry import execute_tool
from tests.conftest import ask, auth


def steps(r):
    return {s["title"]: s for s in r["agent"]["steps"]}


def approve(client, user, r, selected=None):
    body = {"pending_action_id": r["action_required"]["pending_action_id"]}
    if selected is not None:
        body["selected"] = selected
    res = client.post("/actions/confirm", json=body, headers=auth(client, user))
    assert res.status_code == 200, res.text
    return res.json()


# ------------------------------------------------------------------ routing
@pytest.mark.parametrize("q,agent", [
    ("I have thyroid problems, book me a doctor", "appointment_booking"),
    ("Book an appointment with an orthopedic doctor", "appointment_booking"),
    ("Plan my visit tomorrow", "visit_planner"),
    ("Plan my next visit", "visit_planner"),
    ("Check my reminders", "proactive_care"),
    ("My sugar report is high, what should I do next?", "lab_follow_up"),
    ("How much will my knee replacement cost?", "cost_estimate"),
    ("I'm travelling next week, move my appointments", "smart_reschedule"),
    ("Move all my appointments to afternoons", "smart_reschedule"),
    ("Get me ready for my surgery", "surgery_readiness"),
    # ordinary questions must NOT start an agent
    ("When is my next appointment?", None),
    ("How do I schedule an MRI scan?", None),
    ("Reschedule my cardiology appointment", None),
    ("What is my latest blood sugar reading?", None),
    ("Am I covered for knee replacement?", None),
    ("Book me a doctor right away for my knee", "appointment_booking"),
    ("Do I have an appointment with the surgeon?", None),
])
def test_routing(q, agent):
    r = classify_rules(q)
    assert (r["route"] if r["intent"] == "agent" else None) == agent


def test_agent_catalog(client):
    assert len(client.get("/me/agents", headers=auth(client, "asha")).json()) == 7
    assert client.get("/me/agents", headers=auth(client, "staff1")).json() == []


def test_staff_cannot_run_agents(client):
    r = ask(client, "staff1", "Check my reminders")
    assert r["intent"] == "out_of_scope" and "patients" in r["answer"]


# ------------------------------------------------------------------ Appointment Booking Agent
def test_booking_new_department(client, reseed):
    r = ask(client, "asha", "I have thyroid problems, book me a doctor")
    assert r["agent"]["name"] == "appointment_booking"
    item = r["action_required"]["items"][0]
    assert item["type"] == "book_appointment" and "Endocrinology" in item["label"]
    approve(client, "asha", r)
    appts = client.get("/me/appointments", headers=auth(client, "asha")).json()
    assert any(a["department"] == "Endocrinology" for a in appts)


def test_booking_respects_time_preference(client, reseed):
    r = ask(client, "asha", "I have thyroid problems, book me a doctor in the afternoon")
    assert ", 13:" in r["action_required"]["items"][0]["detail"] or ", 14:" in r["action_required"]["items"][0]["detail"]


def test_booking_existing_department_is_not_duplicated(client):
    r = ask(client, "asha", "Book an appointment with an orthopedic doctor")
    st = steps(r)["Check your existing appointments"]
    assert st["status"] == "warning" and "already have" in " ".join(st["details"])
    assert r["action_required"] is None


def test_booking_needs_a_department(client):
    r = ask(client, "asha", "Book me a doctor")
    assert r["agent"]["steps"][0]["status"] == "stopped"
    assert any("Which department" in d for d in r["agent"]["steps"][0]["details"])


# ------------------------------------------------------------------ Visit Planner Agent
def test_visit_planner_tomorrow(client):
    r = ask(client, "asha", "Plan my visit tomorrow")
    card = next(c for c in r["cards"] if c["type"] == "visit_timeline")
    assert card["data"]["date"] == (date.today() + timedelta(days=1)).isoformat()
    assert card["data"]["items"][0]["title"].startswith("General Medicine")
    assert any("Bring your patient ID" in d for d in steps(r)["Check how to prepare"]["details"])
    assert r["action_required"] is None  # read-only


def test_visit_planner_next_visit_includes_walk_in_test(client):
    r = ask(client, "meera", "Plan my next visit")
    assert next(c for c in r["cards"] if c["type"] == "visit_timeline")["data"]["items"][0]["title"] \
        .startswith("Endocrinology")
    assert "HbA1c" in " ".join(steps(r)["Check how to prepare"]["details"])


# ------------------------------------------------------------------ Proactive Care Agent
def test_notifications_per_patient(client):
    rahul = client.get("/me/notifications", headers=auth(client, "rahul")).json()
    assert {"Book my Electrocardiogram (ECG)", "Get me ready for my surgery"} <= {n["action_prompt"] for n in rahul}
    john = client.get("/me/notifications", headers=auth(client, "john")).json()
    assert any("expired" in n["text"] for n in john)
    assert all("[S" not in n["text"] for n in john)  # tags stripped for the inbox
    assert client.get("/me/notifications", headers=auth(client, "staff1")).json() == []


def test_notification_actions_start_the_right_agent(client):
    prompts = {n["action_prompt"] for u in ("asha", "rahul", "meera")
               for n in client.get("/me/notifications", headers=auth(client, u)).json() if n["action_prompt"]}
    for p in prompts:
        cls = classify_rules(p)
        assert cls["intent"] == "agent" or cls.get("route") == "book_test", p


def test_reminders_in_chat(client):
    r = ask(client, "meera", "Check my reminders")
    card = next(c for c in r["cards"] if c["type"] == "notifications")
    assert any("Glucose" in n["text"] for n in card["data"]["items"])


# ------------------------------------------------------------------ Lab Follow-up Agent
def test_lab_follow_up_existing_visit(client):
    r = ask(client, "meera", "My sugar report is high, what should I do next?")
    st = steps(r)
    assert "Only your doctor" in " ".join(st["Keep it safe: no interpretation"]["details"])
    assert "take this report" in " ".join(st["Check for an existing follow-up"]["details"])
    assert r["action_required"] is None


def test_lab_follow_up_books_when_missing(client, reseed):
    r = ask(client, "john", "My cholesterol report is high, what next?")
    item = r["action_required"]["items"][0]
    assert item["type"] == "book_appointment" and "General Medicine" in item["label"]
    approve(client, "john", r)
    assert any(a["department"] == "General Medicine"
               for a in client.get("/me/appointments", headers=auth(client, "john")).json())


def test_lab_follow_up_normal_results(client):
    r = ask(client, "rahul", "My CBC results, what should I do next?")
    assert "within their reference ranges" in " ".join(r["agent"]["steps"][0]["details"])
    assert r["action_required"] is None


# ------------------------------------------------------------------ Cost Estimate Agent
def test_cost_estimate_with_pre_approval(client, reseed):
    r = ask(client, "asha", "How much will my knee replacement cost?")
    share = " ".join(steps(r)["Calculate your share"]["details"])
    assert "75,000" in share and "80%" in share
    assert "annual coverage limit" in " ".join(steps(r)["Read your plan document"]["details"])
    assert r["action_required"]["items"][0]["type"] == "submit_prior_auth"
    assert any(c["type"] == "coverage" for c in r["cards"])


def test_cost_estimate_expired_policy(client):
    r = ask(client, "john", "How much will knee replacement cost me?")
    assert steps(r)["Calculate your share"]["status"] == "warning"
    assert "policy is active" in " ".join(steps(r)["Read your plan document"]["details"])
    assert r["action_required"] is None


def test_cost_estimate_uses_recommended_surgery(client):
    r = ask(client, "rahul", "How much will my surgery cost?")
    assert "Laparoscopic Cholecystectomy" in " ".join(steps(r)["Identify the procedure"]["details"])


# ------------------------------------------------------------------ Smart Rescheduling Agent
def test_reschedule_to_afternoons(client, reseed):
    r = ask(client, "rahul", "Move all my appointments to afternoons")
    items = r["action_required"]["items"]
    assert [i["type"] for i in items] == ["reschedule_appointment"]
    approve(client, "rahul", r)
    appt = next(a for a in client.get("/me/appointments", headers=auth(client, "rahul")).json()
                if a["appointment_id"] == "APT-2001")
    assert 12 <= int(appt["start"][11:13]) < 17


def test_reschedule_around_travel(client, reseed):
    start, end = parse_range("next week")
    r = ask(client, "asha", "I'm travelling next week, move my appointments")
    upcoming = client.get("/me/appointments", headers=auth(client, "asha")).json()
    in_range = [a for a in upcoming if start.isoformat() <= a["start"][:10] <= end.isoformat()
                and datetime.fromisoformat(a["start"]) - datetime.now() >= timedelta(hours=24)]
    if not in_range:
        assert r["action_required"] is None
        return
    assert len(r["action_required"]["items"]) == len(in_range)
    approve(client, "asha", r)
    for a in client.get("/me/appointments", headers=auth(client, "asha")).json():
        assert not (start.isoformat() <= a["start"][:10] <= end.isoformat()) or \
            datetime.fromisoformat(a["start"]) - datetime.now() < timedelta(hours=24)


def test_reschedule_needs_constraints(client):
    r = ask(client, "asha", "Move all my appointments")
    assert r["agent"]["steps"][0]["status"] == "stopped"


def test_cannot_reschedule_someone_elses_appointment(reseed):
    out = execute_tool("propose_care_plan", {"items": [{"type": "reschedule_appointment", "appointment_id": "APT-2001",
                                                        "slot_id": 1}]}, ctx_for("asha"))
    assert out == {"ok": False, "error": "not_found"}
