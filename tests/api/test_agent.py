"""Surgery Readiness Agent: decisions, grounding, one-approval plan, and safety."""
import re

from backend.app.chat_ctx import ctx_for
from backend.app.db import db_session
from backend.app.models import DiagnosticSlot, Order, PriorAuthRequest
from backend.app.tools.registry import execute_tool
from tests.conftest import ask, auth

GOAL = "Get me ready for my surgery"


def steps(r):
    return {s["title"]: s for s in r["agent"]["steps"]}


def test_rahul_full_plan(client, reseed):
    r = ask(client, "rahul", GOAL)
    assert r["intent"] == "agent" and r["status"] == "ok"
    st = steps(r)
    assert st["Find your recommended surgery"]["status"] == "done"
    assert any("Prior authorization is required" in d for d in st["Check insurance coverage"]["details"])
    compare = " ".join(st["Compare required tests with your record"]["details"])
    assert "Complete Blood Count (CBC) was completed" in compare and "30-day validity" in compare
    assert "Electrocardiogram (ECG) is still pending" in compare and "Chest X-ray is still pending" in compare
    plan = r["action_required"]
    assert plan["type"] == "confirm_plan"
    assert [i["type"] for i in plan["items"]] == ["book_test", "book_test", "submit_prior_auth"]
    # both tests on the same day (one visit)
    slot_days = re.findall(r"slot on \w{3} (\d\d \w{3} \d{4})", " ".join(st["Find slots for your pending tests"]["details"]))
    assert len(slot_days) == 2 and slot_days[0] == slot_days[1]
    # every tag in the answer resolves to a citation; the protocol is cited as a document
    assert set(re.findall(r"\[(S\d+)\]", r["answer"])) == {c["id"] for c in r["citations"]}
    assert any(c["source_type"] == "document" and c["ref"].startswith("CLP-SUR-001") for c in r["citations"])


def test_plan_changes_nothing_until_approved(client, reseed):
    ask(client, "rahul", GOAL)
    with db_session() as db:
        assert db.query(DiagnosticSlot).filter_by(is_booked=True).count() == 0
        assert db.query(PriorAuthRequest).count() == 0
        assert db.get(Order, "ORD-503").scheduled_at is None


def test_approve_all_then_rerun_is_idempotent(client, reseed):
    plan = ask(client, "rahul", GOAL)["action_required"]
    res = client.post("/actions/confirm", json={"pending_action_id": plan["pending_action_id"]},
                      headers=auth(client, "rahul"))
    assert res.status_code == 200 and len(res.json()["results"]) == 3
    tests = client.get("/me/pending-tests", headers=auth(client, "rahul")).json()
    assert all(t["scheduled_at"] for t in tests)  # sidebar shows them as booked

    assert steps(ask(client, "rahul", "Help me prepare for my operation"))["Check insurance coverage"]["status"] \
        == "done"  # prior auth already submitted -> nothing left to do on the coverage step
    again = ask(client, "rahul", GOAL)
    st = steps(again)
    assert "already booked" in " ".join(st["Compare required tests with your record"]["details"])
    assert "already submitted" in " ".join(st["Check prior authorization"]["details"])
    assert again["action_required"] is None


def test_partial_approval(client, reseed):
    plan = ask(client, "rahul", GOAL)["action_required"]
    res = client.post("/actions/confirm", json={"pending_action_id": plan["pending_action_id"], "selected": [2]},
                      headers=auth(client, "rahul"))
    assert res.status_code == 200 and [x["type"] for x in res.json()["results"]] == ["submit_prior_auth"]
    with db_session() as db:
        assert db.get(Order, "ORD-503").scheduled_at is None and db.query(PriorAuthRequest).count() == 1


def test_bad_selection_rejected(client, reseed):
    plan = ask(client, "rahul", GOAL)["action_required"]
    for selected in ([], [7]):
        res = client.post("/actions/confirm", json={"pending_action_id": plan["pending_action_id"],
                                                    "selected": selected}, headers=auth(client, "rahul"))
        assert res.status_code == 400


def test_slot_taken_rolls_back_everything(client, reseed):
    plan = ask(client, "rahul", GOAL)["action_required"]
    with db_session() as db:
        db.query(DiagnosticSlot).filter_by(is_booked=False).update({"is_booked": True})  # someone took them
        db.commit()
    res = client.post("/actions/confirm", json={"pending_action_id": plan["pending_action_id"]},
                      headers=auth(client, "rahul"))
    assert res.status_code == 409
    with db_session() as db:
        assert db.query(PriorAuthRequest).count() == 0  # all-or-nothing


def test_other_patient_cannot_approve(client, reseed):
    plan = ask(client, "rahul", GOAL)["action_required"]
    res = client.post("/actions/confirm", json={"pending_action_id": plan["pending_action_id"]},
                      headers=auth(client, "asha"))
    assert res.status_code == 404


def test_cannot_plan_with_someone_elses_order(reseed):
    with db_session() as db:
        slot_id = db.query(DiagnosticSlot).filter_by(service="ECG").first().id
    out = execute_tool("propose_care_plan", {"items": [{"type": "book_test", "order_id": "ORD-503",
                                                        "slot_id": slot_id}]}, ctx_for("asha"))
    assert out == {"ok": False, "error": "not_found"}


def test_wrong_service_slot_rejected(reseed):
    with db_session() as db:
        xray_slot = db.query(DiagnosticSlot).filter_by(service="Chest X-ray").first().id
    out = execute_tool("propose_care_plan", {"items": [{"type": "book_test", "order_id": "ORD-503",
                                                        "slot_id": xray_slot}]}, ctx_for("rahul"))
    assert out["ok"] is False and out["error"].startswith("invalid")


def test_asha_tests_not_ordered(client, reseed):
    r = ask(client, "asha", "Help me prepare for my operation")
    compare = " ".join(steps(r)["Compare required tests with your record"]["details"])
    assert compare.count("has not been ordered yet") == 3 and "Dr. Priya Nair" in compare
    assert [i["type"] for i in r["action_required"]["items"]] == ["submit_prior_auth"]


def test_no_surgery_stops_early(client):
    r = ask(client, "meera", GOAL)
    assert [s["status"] for s in r["agent"]["steps"]] == ["stopped"]
    assert r["action_required"] is None


def test_staff_do_not_trigger_the_agent(client):
    r = ask(client, "staff1", GOAL)
    assert r["intent"] != "agent"
