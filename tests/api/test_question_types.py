"""Functional tests: the 8 question types x several cases each (PDF section 9, master test matrix)."""
import re

from tests.conftest import ask, auth, tool_names


def doc_refs(r):
    return [c["ref"] for c in r["citations"] if c["source_type"] == "document"]


# ------------------------------------------------------------------ 1. policy
def test_policy_icu_hours(client):
    r = ask(client, "asha", "What are visiting hours for ICU patients?")
    assert r["status"] == "ok" and r["intent"] == "policy"
    assert "11:00" in r["answer"] and "17:00" in r["answer"]
    assert any(ref.startswith("POL-VIS-001") for ref in doc_refs(r))
    assert any("3.2" in (c["section"] or "") for c in r["citations"])


def test_policy_children_in_icu(client):
    r = ask(client, "asha", "Can children visit the ICU?")
    assert r["status"] == "ok"
    assert "12" in r["answer"]
    assert any(ref.startswith("POL-VIS-001") for ref in doc_refs(r))


def test_policy_general_ward_visitors(client):
    r = ask(client, "rahul", "How many visitors are allowed in the general ward?")
    assert r["status"] == "ok"
    assert "three" in r["answer"].lower()


def test_policy_no_show(client):
    r = ask(client, "meera", "What is the no-show policy?")
    assert r["status"] == "ok"
    assert any(ref.startswith("POL-APT-002") for ref in doc_refs(r))


# ------------------------------------------------------------------ 2. procedure
def test_procedure_mri_steps(client):
    r = ask(client, "asha", "How do I schedule an MRI scan?")
    assert r["status"] == "ok" and r["intent"] == "procedure"
    assert re.search(r"^1\. ", r["answer"], re.M) and re.search(r"^2\. ", r["answer"], re.M)
    assert "3300" in r["answer"]
    assert any(ref.startswith("PRO-RAD-001") for ref in doc_refs(r))


def test_procedure_ct_with_contrast(client):
    r = ask(client, "asha", "How do I book a CT scan with contrast?")
    assert r["status"] == "ok"
    assert "creatinine" in r["answer"].lower()


def test_procedure_discharge(client):
    r = ask(client, "rahul", "What should I do before discharge?")
    assert r["status"] == "ok"
    assert any(ref.startswith("PRO-DIS-001") for ref in doc_refs(r))
    assert "pharmacy" in r["answer"].lower()


# ------------------------------------------------------------------ 3. personal data
def test_personal_upcoming_appointments_only_own(client):
    r = ask(client, "asha", "What are my upcoming appointments?")
    assert r["status"] == "ok" and r["intent"] == "personal_data"
    refs = {c["ref"] for c in r["citations"]}
    assert "APT-1042" in refs and "APT-1043" in refs
    assert not refs & {"APT-2001", "APT-3001", "APT-4001"}  # other patients
    assert any(c["type"] == "appointments" for c in r["cards"])


def test_personal_meera_endocrinology(client):
    r = ask(client, "meera", "When is my next appointment?")
    assert r["status"] == "ok"
    assert "Endocrinology" in r["answer"]


def test_personal_past_appointments(client):
    r = ask(client, "asha", "Show my past appointments")
    assert r["status"] == "ok"
    assert "APT-1040" in {c["ref"] for c in r["citations"]}


# ------------------------------------------------------------------ 4. eligibility
def test_eligibility_is_tool_based(client):
    r = ask(client, "asha", "Am I covered for knee replacement under my insurance plan?")
    assert r["intent"] == "eligibility"
    assert "check_coverage" in tool_names(r)
    assert "80%" in r["answer"] and "prior authorization" in r["answer"].lower()
    card = next(c for c in r["cards"] if c["type"] == "coverage")["data"]
    assert card["covered"] is True and card["coverage_pct"] == 80 and card["rule_id"] == "R-G-27447"
    assert any(ref.startswith("INS-GOLD-001") for ref in doc_refs(r))


def test_eligibility_expired_plan(client):
    r = ask(client, "john", "Am I covered for knee replacement?")
    assert "expired" in r["answer"].lower()
    assert next(c for c in r["cards"] if c["type"] == "coverage")["data"]["covered"] is False


def test_eligibility_cosmetic_excluded(client):
    r = ask(client, "meera", "Is cosmetic surgery covered?")
    assert "not covered" in r["answer"].lower()


def test_eligibility_waiting_period(client):
    r = ask(client, "meera", "Is knee replacement covered for me?")
    assert "waiting period" in r["answer"].lower()


def test_eligibility_basic_plan_gallbladder(client):
    r = ask(client, "rahul", "Is gallbladder surgery covered?")
    assert "50%" in r["answer"]
    assert "15,000" in r["answer"] or "15000" in r["answer"]


# ------------------------------------------------------------------ 5. lab results
def test_lab_latest_blood_sugar(client):
    r = ask(client, "meera", "What is my latest blood sugar reading?")
    assert r["status"] == "ok" and r["intent"] == "lab_result"
    assert "112" in r["answer"] and "mg/dL" in r["answer"]
    assert "70-99" in r["answer"]
    assert r["disclaimer"]
    assert [c["data"]["lab_id"] for c in r["cards"] if c["type"] == "lab_result"] == ["LAB-5531"]


def test_lab_hba1c_trend(client):
    r = ask(client, "meera", "Show my HbA1c trend")
    values = [c["data"]["value"] for c in r["cards"] if c["type"] == "lab_result"]
    assert values == [6.6, 6.9, 7.4]


def test_lab_cbc(client):
    r = ask(client, "rahul", "What were my CBC results?")
    assert "13.8" in r["answer"]


def test_lab_cholesterol_flag(client):
    r = ask(client, "asha", "What is my cholesterol level?")
    assert "212" in r["answer"] and "high" in r["answer"]


# ------------------------------------------------------------------ 6. multi-step
def pending_section(answer: str) -> str:
    m = re.search(r"Still pending:(.*)", answer)
    return m.group(1).lower() if m else ""


def test_multistep_pending_preop(client):
    r = ask(client, "rahul", "My doctor recommended surgery. What pre-operative tests are still pending?")
    assert r["intent"] == "multi_step"
    pending = pending_section(r["answer"])
    assert "ecg" in pending and "x-ray" in pending and "cbc" not in pending
    assert "Completed" in r["answer"] and "CBC" in r["answer"]
    types = {c["source_type"] for c in r["citations"]}
    assert types == {"record", "document"}  # combines records AND the protocol
    assert any(ref.startswith("CLP-SUR-001") for ref in doc_refs(r))
    card = next(c for c in r["cards"] if c["type"] == "pending_tests")["data"]
    assert {i["name"]: i["status"] for i in card["items"]}["Chest X-ray"] == "pending"


def test_multistep_no_preop_orders(client):
    r = ask(client, "asha", "What pre-op tests are pending before my surgery?")
    assert r["status"] == "ok"
    assert "Total Knee Replacement" in r["answer"]
    assert "No pre-operative test orders" in r["answer"]
    assert pending_section(r["answer"]) == ""


# ------------------------------------------------------------------ 7. actions
def _cardiology_start(client, user="asha"):
    appts = client.get("/me/appointments", headers=auth(client, user)).json()
    return next(a["start"] for a in appts if a["appointment_id"] == "APT-1042")


def test_action_requires_confirmation(client, reseed):
    before = _cardiology_start(client)
    r = ask(client, "asha", "Reschedule my cardiology appointment")
    assert r["intent"] == "action"
    ar = r["action_required"]
    assert ar["type"] == "confirm_reschedule" and ar["pending_action_id"].startswith("PA-")
    assert _cardiology_start(client) == before  # unchanged until confirm

    res = client.post("/actions/confirm", json={"pending_action_id": ar["pending_action_id"]},
                      headers=auth(client, "asha"))
    assert res.status_code == 200 and res.json()["status"] == "done"
    assert _cardiology_start(client) == ar["new_start"]


def test_action_within_24h_refused(client, reseed):
    r = ask(client, "asha", "Reschedule my appointment tomorrow")
    assert r["action_required"] is None
    assert "24 hours" in r["answer"]


def test_action_meera_endocrinology(client, reseed):
    r = ask(client, "meera", "Please reschedule my endocrinology appointment")
    assert r["action_required"] and "Endocrinology" in r["action_required"]["summary"]


# ------------------------------------------------------------------ 8. not found
def test_not_found_proton(client):
    r = ask(client, "asha", "Do you have treatment information for proton beam therapy?")
    assert r["status"] == "not_found" and r["citations"] == []


def test_not_found_helipad(client):
    r = ask(client, "asha", "Do you have a helipad?")
    assert r["status"] == "not_found"


def test_not_found_wifi(client):
    r = ask(client, "rahul", "What is the hospital Wi-Fi password?")
    assert r["status"] == "not_found"


# ------------------------------------------------------------------ robustness / follow-ups
def test_typo_tolerance(client):
    r = ask(client, "asha", "wat r icu visitng hrs")
    assert r["status"] == "ok" and "11:00" in r["answer"]


def test_follow_up_uses_history(client):
    ask(client, "asha", "Which department handles knees?", session="follow-up-1")
    r = ask(client, "asha", "Where is it?", session="follow-up-1")
    assert "Orthopedics" in r["answer"] and "Block B" in r["answer"]


def test_staff_can_read_policies(client):
    r = ask(client, "staff1", "What are ICU visiting hours?")
    assert r["status"] == "ok" and "11:00" in r["answer"]
