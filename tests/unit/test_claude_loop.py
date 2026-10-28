"""The Claude tool-use path, exercised with a fake Anthropic client (no API key or network needed)."""
import re
from datetime import date, timedelta
from types import SimpleNamespace as NS

import pytest

from ai import orchestrator
from backend.app.chat_ctx import ctx_for
from backend.app.tools.registry import execute_tool


def text(t):
    return NS(type="text", text=t)


def tool_use(id_, name, inp):
    return NS(type="tool_use", id=id_, name=name, input=inp)


class FakeClient:
    """Replays scripted responses; records every request so tests can inspect what Claude was sent."""

    def __init__(self, classify_intent, turns):
        self.classify_intent = classify_intent
        self.turns = list(turns)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if kw.get("tool_choice", {}).get("name") == "classify_intent":
            return NS(stop_reason="tool_use", content=[tool_use("c0", "classify_intent",
                                                                {"intent": self.classify_intent,
                                                                 "needs_patient_data": True})])
        turn = self.turns.pop(0)
        if callable(turn):
            turn = turn(kw)
        return turn


@pytest.fixture()
def claude_mode(monkeypatch):
    monkeypatch.setenv("AI_MODE", "claude")

    def install(client):
        monkeypatch.setattr(orchestrator, "_anthropic", lambda: client)
    return install


def _tool_result_text(kw):
    return kw["messages"][-1]["content"][0]["content"]


def _first_source_id(kw):
    return re.search(r"SOURCE \[(S\d+)\]", _tool_result_text(kw)).group(1)


def test_lab_question_end_to_end(claude_mode):
    collected = (date.today() - timedelta(days=8)).isoformat()  # seed: LAB-5531 is 8 days old

    def final(kw):
        sent = _tool_result_text(kw)
        assert "SOURCE [S1]" in sent and "112 mg/dL" in sent
        assert "P003" not in sent  # the model never sees patient ids
        return NS(stop_reason="end_turn", content=[text(
            f"Your latest fasting glucose was 112 mg/dL on {collected} [S1]. It was 250 last week.")])

    fake = FakeClient("lab_result", [
        NS(stop_reason="tool_use", content=[tool_use("t1", "get_lab_results",
                                                     {"test_name": "glucose", "latest_only": True,
                                                      "patient_id": "P002"})]),
        final,
    ])
    claude_mode(fake)
    r = orchestrator.answer_query("What is my latest blood sugar?", ctx_for("meera"), [], execute_tool)
    assert r["mode"] == "claude" and r["intent"] == "lab_result" and r["status"] == "ok"
    assert "112 mg/dL" in r["answer"]
    assert "250" not in r["answer"]  # unsupported sentence removed by the grounding verifier
    assert r["citations"][0]["ref"] == "LAB-5531"
    assert r["cards"][0]["type"] == "lab_result" and r["disclaimer"]
    tools_sent = {t["name"] for t in fake.calls[1]["tools"]}
    assert "check_coverage" in tools_sent and all("patient_id" not in t["input_schema"]["properties"]
                                                  for t in fake.calls[1]["tools"])


def test_reschedule_produces_pending_action(claude_mode, reseed):
    def propose(kw):
        sent = _tool_result_text(kw)
        slot_id = int(sent.split("slot_id=")[1].split(")")[0])
        return NS(stop_reason="tool_use", content=[tool_use("t3", "propose_reschedule",
                                                            {"appointment_id": "APT-1042", "slot_id": slot_id})])

    fake = FakeClient("action", [
        NS(stop_reason="tool_use", content=[tool_use("t1", "get_appointments", {"department": "Cardiology",
                                                                              "status": "upcoming"})]),
        NS(stop_reason="tool_use", content=[tool_use("t2", "get_available_slots", {"appointment_id": "APT-1042"})]),
        propose,
        lambda kw: NS(stop_reason="end_turn", content=[text(
            f"I have prepared the change [{_first_source_id(kw)}]. Please confirm the change in the app.")]),
    ])
    claude_mode(fake)
    r = orchestrator.answer_query("Reschedule my cardiology appointment", ctx_for("asha"), [], execute_tool)
    assert r["status"] == "ok"
    assert r["action_required"]["type"] == "confirm_reschedule"
    assert r["citations"][0]["title"] == "Pending reschedule request"


def test_unsupported_answer_becomes_not_found(claude_mode):
    fake = FakeClient("policy", [
        NS(stop_reason="tool_use", content=[tool_use("t1", "search_hospital_docs",
                                                     {"query": "proton beam therapy"})]),
        NS(stop_reason="end_turn", content=[text("Yes, proton therapy is available on floor 9.")]),
    ])
    claude_mode(fake)
    r = orchestrator.answer_query("Do you offer proton therapy?", ctx_for("asha"), [], execute_tool)
    assert r["status"] == "not_found" and r["citations"] == []


def test_api_failure_falls_back_to_offline(claude_mode):
    class Broken:
        @property
        def messages(self):
            raise RuntimeError("network down")

    claude_mode(Broken())
    r = orchestrator.answer_query("What are visiting hours for ICU patients?", ctx_for("asha"), [], execute_tool)
    assert r["mode"] == "offline" and r["status"] == "ok" and "11:00" in r["answer"]


def test_step_limit(claude_mode):
    loop = NS(stop_reason="tool_use", content=[tool_use("t", "search_hospital_docs", {"query": "icu"})])
    claude_mode(FakeClient("policy", [loop] * 10))
    r = orchestrator.answer_query("What are ICU hours?", ctx_for("asha"), [], execute_tool)
    assert r["status"] == "not_found"
