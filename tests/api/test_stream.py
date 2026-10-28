"""POST /chat/stream: Server-Sent Events with live progress, then the verified final response."""
import json

from tests.conftest import auth


def stream(client, user, message):
    events = []
    with client.stream("POST", "/chat/stream", json={"message": message, "session_id": f"s-{user}"},
                       headers=auth(client, user)) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        etype = None
        for line in r.iter_lines():
            if line.startswith("event:"):
                etype = line[6:].strip()
            elif line.startswith("data:"):
                events.append((etype, json.loads(line[5:].strip())))
    return events


def test_tool_progress_then_final(client):
    events = stream(client, "meera", "What is my latest blood sugar reading?")
    types = [t for t, _ in events]
    assert types[-1] == "final" and types.count("final") == 1
    tools = [e for t, e in events if t == "tool"]
    assert [(e["name"], e["status"]) for e in tools] == [("get_lab_results", "running"), ("get_lab_results", "done")]
    assert any(t == "status" and "Verifying" in e["text"] for t, e in events)
    final = events[-1][1]["response"]
    assert "112" in final["answer"] and final["status"] == "ok"


def test_agent_steps_stream_live(client, reseed):
    events = stream(client, "rahul", "Get me ready for my surgery")
    assert events[0][0] == "agent"
    steps = [e for t, e in events if t == "step"]
    first = steps[0]
    assert first["index"] == 1 and first["status"] == "running"  # shown before it finishes
    finished = {e["index"]: e["status"] for e in steps if e["status"] != "running"}
    assert len(finished) == 7
    final = events[-1][1]["response"]
    assert final["action_required"]["type"] == "confirm_plan"


def test_stream_requires_auth(client):
    r = client.post("/chat/stream", json={"message": "hi", "session_id": "x"})
    assert r.status_code in (401, 403)


def test_guardrail_answers_stream_too(client):
    events = stream(client, "asha", "I have severe chest pain")
    assert events[-1][1]["response"]["status"] == "emergency"
