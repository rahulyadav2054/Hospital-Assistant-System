import json
import logging
import queue
import threading
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai.orchestrator import answer_query

from .. import sessions
from ..audit import audit
from ..auth import get_current_user
from ..chat_ctx import build_user_ctx
from ..config import settings
from ..db import get_db
from ..limiter import limiter
from ..mock import mock_response
from ..tools.registry import execute_tool

router = APIRouter(tags=["chat"])
log = logging.getLogger("chat")


class ChatIn(BaseModel):
    # The guardrail returns a friendly message above 2000 chars; this hard cap only stops abuse.
    message: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(default="default", min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_\-:.]+$")


def _answer(body: ChatIn, user: dict, ctx: dict, on_event=None) -> dict:
    """Shared by /chat and /chat/stream: answer, remember the turn, audit."""
    t0 = time.time()
    history = sessions.get(user["user_id"], body.session_id)
    if settings.MOCK_AI:
        resp = mock_response(body.message)
    else:
        try:
            resp = answer_query(body.message, ctx, history, execute_tool, on_event=on_event)
        except Exception:
            log.exception("answer_query failed")
            resp = {"answer": "Sorry, something went wrong while answering. Please try again.", "status": "error",
                    "intent": "out_of_scope", "citations": [], "tool_calls": [], "cards": [],
                    "action_required": None, "disclaimer": None, "mode": "error", "fallback_reason": None,
                    "latency_ms": 0}
    sessions.append(user["user_id"], body.session_id, body.message, resp["answer"])
    resp["latency_ms"] = int((time.time() - t0) * 1000)
    audit(user, endpoint="/chat", intent=resp.get("intent"), outcome=resp.get("status"),
          latency_ms=resp["latency_ms"])
    return resp


@router.post("/chat")
@limiter.limit(settings.CHAT_RATE)
def chat(request: Request, body: ChatIn, user=Depends(get_current_user), db=Depends(get_db)):
    return _answer(body, user, build_user_ctx(db, user))


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, default=str)}\n\n"


@router.post("/chat/stream")
@limiter.limit(settings.CHAT_RATE)
def chat_stream(request: Request, body: ChatIn, user=Depends(get_current_user), db=Depends(get_db)):
    """Server-Sent Events: live progress (tool calls, agent steps, status), then one `final` event with the
    verified response. Answer text is only sent after the grounding check - unverified text is never streamed."""
    ctx = build_user_ctx(db, user)
    events: queue.Queue = queue.Queue()

    def worker():
        try:
            resp = _answer(body, user, ctx, on_event=events.put)
            events.put({"type": "final", "response": resp})
        finally:
            events.put(None)

    threading.Thread(target=worker, name="chat-stream", daemon=True).start()

    def stream():
        yield ": stream open\n\n"  # comment line: flushes headers immediately
        while (event := events.get()) is not None:
            yield _sse(event)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
