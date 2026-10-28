"""The OpenAI-compatible LLM tool-use path (Groq by default), exercised with a fake client (no key or network)."""
import json
import re
from datetime import date, timedelta
from types import SimpleNamespace as NS

import pytest

from ai import orchestrator
from backend.app.chat_ctx import ctx_for
from backend.app.tools.registry import execute_tool


class Msg:
    """Mimics openai's ChatCompletionMessage (content, tool_calls, model_dump)."""

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or None

    def model_dump(self, exclude_none=False):
        d = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [{"id": c.id, "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments}}
                               for c in self.tool_calls]
        return {k: v for k, v in d.items() if v is not None} if exclude_none else d


def call(id_, name, args):
    return NS(id=id_, type="function",
              function=NS(name=name, arguments=args if isinstance(args, str) else json.dumps(args)))


class FakeLLM:
    def __init__(self, turns):
        self.turns = list(turns)
        self.requests = []
        self.chat = NS(completions=self)

    def create(self, **kw):
        self.requests.append(kw)
        turn = self.turns.pop(0)
        msg = turn(kw) if callable(turn) else turn
        return NS(choices=[NS(message=msg)])


@pytest.fixture()
def llm_mode(monkeypatch):
    monkeypatch.setenv("AI_MODE", "llm")

    def install(client):
        monkeypatch.setattr(orchestrator, "_llm", lambda: client)
    return install


def _last_tool_text(kw):
    return kw["messages"][-1]["content"]


def test_mode_selected_by_llm_key(monkeypatch):
    from ai import config
    monkeypatch.setenv("AI_MODE", "auto")
    monkeypatch.setenv("LLM_API_KEY", "gsk-test")
    assert config.ai_mode() == "llm"
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    assert config.ai_mode() == "offline"


def test_lab_question_end_to_end(llm_mode):
    collected = (date.today() - timedelta(days=8)).isoformat()

    def final(kw):
        assert kw["messages"][-1]["role"] == "tool"
        assert set(kw["messages"][-2]) == {"role", "content", "tool_calls"}  # only standard fields echoed back
        assert kw["temperature"] == 0
        sent = _last_tool_text(kw)
        assert "SOURCE [S1]" in sent and "112 mg/dL" in sent and "P003" not in sent
        return Msg(content=f"Your latest fasting glucose was 112 mg/dL on {collected} [S1]. It was 250 last week.")

    fake = FakeLLM([
        Msg(tool_calls=[call("c1", "get_lab_results",
                             {"test_name": "glucose", "latest_only": True, "patient_id": "P002"})]),
        final,
    ])
    llm_mode(fake)
    r = orchestrator.answer_query("What is my latest blood sugar?", ctx_for("meera"), [], execute_tool)
    assert r["mode"] == "llm" and r["intent"] == "lab_result" and r["status"] == "ok"
    assert "112 mg/dL" in r["answer"] and "250" not in r["answer"]  # unsupported sentence removed
    assert r["citations"][0]["ref"] == "LAB-5531"
    first = fake.requests[0]
    assert first["messages"][0]["role"] == "system"
    assert all(t["type"] == "function" and "patient_id" not in t["function"]["parameters"]["properties"]
               for t in first["tools"])


def test_reschedule_produces_pending_action(llm_mode, reseed):
    def propose(kw):
        slot_id = int(_last_tool_text(kw).split("slot_id=")[1].split(")")[0])
        return Msg(tool_calls=[call("c3", "propose_reschedule", {"appointment_id": "APT-1042", "slot_id": slot_id})])

    def final(kw):
        sid = re.search(r"SOURCE \[(S\d+)\]", _last_tool_text(kw)).group(1)
        return Msg(content=f"I have prepared the change [{sid}]. Please confirm the change in the app.")

    llm_mode(FakeLLM([
        Msg(tool_calls=[call("c1", "get_appointments", {"department": "Cardiology", "status": "upcoming"})]),
        Msg(tool_calls=[call("c2", "get_available_slots", {"appointment_id": "APT-1042"})]),
        propose,
        final,
    ]))
    r = orchestrator.answer_query("Reschedule my cardiology appointment", ctx_for("asha"), [], execute_tool)
    assert r["status"] == "ok" and r["action_required"]["type"] == "confirm_reschedule"


def test_bad_tool_arguments_are_rejected(llm_mode):
    fake = FakeLLM([
        Msg(tool_calls=[call("c1", "get_lab_results", "{not json"), call("c2", "drop_tables", {})]),
        Msg(content="Sorry, I could not find that."),
    ])
    llm_mode(fake)
    r = orchestrator.answer_query("What is my latest blood sugar?", ctx_for("meera"), [], execute_tool)
    tool_msgs = [m for m in fake.requests[1]["messages"] if m.get("role") == "tool"]
    assert [m["content"] for m in tool_msgs] == ["ERROR: invalid call to get_lab_results",
                                                 "ERROR: invalid call to drop_tables"]
    assert r["status"] == "not_found" and r["tool_calls"] == []


def test_api_failure_falls_back_to_offline(llm_mode):
    class Broken:
        @property
        def chat(self):
            raise RuntimeError("network down")

    llm_mode(Broken())
    r = orchestrator.answer_query("What are visiting hours for ICU patients?", ctx_for("asha"), [], execute_tool)
    assert r["mode"] == "offline" and r["status"] == "ok" and "11:00" in r["answer"]


def test_first_step_must_use_a_tool_and_history_tags_are_stripped(llm_mode):
    fake = FakeLLM([Msg(content="Sorry.")])
    llm_mode(fake)
    history = [{"role": "user", "content": "ICU hours?"},
               {"role": "assistant", "content": "ICU visiting hours are 11:00–12:00 [S1]."}]
    orchestrator.answer_query("What is my latest blood sugar reading?", ctx_for("meera"), history, execute_tool)
    req = fake.requests[0]
    assert req["tool_choice"] == "required"
    convo = [m for m in req["messages"] if m["role"] != "system"]  # the system prompt explains the tag format
    assert convo[1] == {"role": "assistant", "content": "ICU visiting hours are 11:00–12:00."}


def test_empty_record_lookup_says_no_records(llm_mode):
    """Rahul has no glucose results: the reply must say 'no matching records in your file', not 'not in policies'."""
    llm_mode(FakeLLM([Msg(tool_calls=[call("c1", "get_lab_results", {"test_name": "glucose"})]),
                      Msg(content="Your sugar is fine.")]))
    r = orchestrator.answer_query("What is my latest blood sugar reading?", ctx_for("rahul"), [], execute_tool)
    assert r["status"] == "not_found" and r["answer"] == orchestrator.NO_RECORDS_MSG


def test_only_intent_tools_are_sent(llm_mode):
    fake = FakeLLM([Msg(content="Sorry.")])
    llm_mode(fake)
    orchestrator.answer_query("What is my latest blood sugar reading?", ctx_for("meera"), [], execute_tool)
    assert [t["function"]["name"] for t in fake.requests[0]["tools"]] == ["get_lab_results"]


def test_rate_limit_answers_offline_at_once_and_pauses_llm(llm_mode, monkeypatch):
    class RateLimited(Exception):
        status_code = 429
        response = NS(headers={"retry-after": "30"})

    class Limited:
        calls = 0

        @property
        def chat(self):
            Limited.calls += 1
            raise RateLimited("Rate limit reached ... Please try again in 30s")

    monkeypatch.setattr(orchestrator, "_llm_cooldown_until", 0.0)
    llm_mode(Limited())
    r = orchestrator.answer_query("What are visiting hours for ICU patients?", ctx_for("asha"), [], execute_tool)
    assert r["mode"] == "offline" and r["fallback_reason"] == "llm_rate_limited" and "11:00" in r["answer"]
    r2 = orchestrator.answer_query("Can children visit the ICU?", ctx_for("asha"), [], execute_tool)
    assert r2["fallback_reason"] == "llm_rate_limited" and Limited.calls == 1  # API skipped during the pause


def test_retry_after_parsed_from_message():
    err = Exception("Rate limit reached for model. Please try again in 12.102857142s. Need more tokens?")
    assert round(orchestrator._retry_after_seconds(err), 1) == 12.1


def test_step_limit(llm_mode):
    loop = Msg(tool_calls=[call("c", "search_hospital_docs", {"query": "icu"})])
    llm_mode(FakeLLM([loop] * 10))
    r = orchestrator.answer_query("What are ICU hours?", ctx_for("asha"), [], execute_tool)
    assert r["status"] == "not_found"
