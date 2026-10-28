"""answer_query(): the single entry point of the AI layer.

guardrails -> classify -> (Claude | OpenAI-compatible LLM tool-use loop | offline pipeline) -> grounding verifier
-> response dict
"""
import json
import logging
import re
import time
from datetime import date

from . import config, guardrails, offline
from .agents import surgery_readiness, test_booking
from .classifier import classify, classify_rules, trim_history
from .grounding import verify_grounding
from .prompts import SYSTEM_PROMPT
from .sources import RunContext
from .tool_schemas import TOOL_NAMES, TOOLS, openai_tools_for

log = logging.getLogger("ai")

DISCLAIMER = "This is not medical advice. Please discuss results and treatment with your doctor."
COVERAGE_DISCLAIMER = ("Coverage is checked against your plan rules; final approval and amounts are decided by "
                       "your insurer.")
AGENT_PATIENTS_ONLY_MSG = ("Surgery readiness checks and test bookings work on a patient's own record, so they are "
                           "available to patients when they are logged in.")
NO_RECORDS_MSG = ("I couldn't find any matching records in your file for this request. If you think something is "
                  "missing, please contact the Patient Help Desk (extension 1100).")
STALE_NOTE ="Note: this policy is more than a year old and may have been updated; please confirm with the department."

_client = None


def _anthropic():
    global _client
    if _client is None:
        import anthropic

        _client = anthropic.Anthropic(max_retries=2, timeout=60)
    return _client


def _prompt_vars(user_ctx: dict) -> dict:
    return {"today": date.today().isoformat(), "user_name": user_ctx.get("name") or "the user",
            "role": user_ctx.get("role", "patient")}


def _claude_loop(message: str, history: list[dict], ctx: RunContext) -> str:
    client = _anthropic()
    messages = _clean_history(history, 8) + [{"role": "user", "content": message}]
    system = SYSTEM_PROMPT.format(**_prompt_vars(ctx.user_ctx))
    r = None
    for _ in range(config.MAX_STEPS):
        r = client.messages.create(model=config.model(), max_tokens=1200, system=system, tools=TOOLS,
                                   messages=messages)
        if r.stop_reason != "tool_use":
            break
        messages.append({"role": "assistant", "content": r.content})
        results = []
        for block in r.content:
            if block.type != "tool_use":
                continue
            if block.name not in TOOL_NAMES:
                content, is_error = f"ERROR: unknown tool {block.name}", True
            else:
                out, _, content = ctx.call(block.name, block.input or {})
                is_error = not out.get("ok")
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": content,
                            "is_error": is_error})
        messages.append({"role": "user", "content": results})
    if r is None or r.stop_reason == "tool_use":
        return ""  # ran out of steps -> grounded not-found
    return "".join(b.text for b in r.content if b.type == "text")


_llm_client = None
_llm_cooldown_until = 0.0  # after a rate limit, skip the API until this time (answers stay instant)


def _llm():
    """Any OpenAI-compatible API (Groq by default) via the openai SDK, configured from .env."""
    global _llm_client
    if _llm_client is None:
        from openai import OpenAI

        # No SDK retries: on a rate limit we answer offline immediately instead of making the user wait.
        _llm_client = OpenAI(api_key=config.llm_api_key(), base_url=config.llm_base_url(),
                             max_retries=0, timeout=30)
    return _llm_client


def _retry_after_seconds(e: Exception) -> float:
    """How long the provider asked us to wait after a 429 (header, or 'try again in 12.1s' in the message)."""
    try:
        return float(e.response.headers["retry-after"])
    except Exception:
        m = re.search(r"try again in ([\d.]+)\s*s", str(e))
        return float(m.group(1)) if m else 20.0


_TAG_RE = re.compile(r"\s*\[S\d+\]")


def _clean_history(history: list[dict], n: int) -> list[dict]:
    """Earlier answers' [Sx] tags point at sources from earlier turns. Left in, models copy the pattern and
    'cite' sources that don't exist this turn instead of calling tools - so strip them."""
    return [{"role": m["role"], "content": _TAG_RE.sub("", m["content"])} for m in trim_history(history, n)]


def _llm_loop(message: str, history: list[dict], ctx: RunContext, intent: str) -> str:
    client = _llm()
    system = SYSTEM_PROMPT.format(**_prompt_vars(ctx.user_ctx))
    messages = ([{"role": "system", "content": system}] + _clean_history(history, 8)
                + [{"role": "user", "content": message}])
    tools = openai_tools_for(intent)
    for step in range(config.MAX_STEPS):
        # Step 1 must call a tool: every answer has to come from fresh sources, never from memory.
        r = client.chat.completions.create(model=config.llm_model(), messages=messages, tools=tools,
                                           tool_choice="required" if step == 0 else "auto",
                                           max_tokens=1200, temperature=0)
        msg = r.choices[0].message
        if not msg.tool_calls:
            return msg.content or ""
        # Rebuild the assistant turn with standard fields only: some providers reject extra fields
        # (e.g. "reasoning") if the SDK object is echoed back as-is.
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": c.id, "type": "function",
                                         "function": {"name": c.function.name,
                                                      "arguments": c.function.arguments or "{}"}}
                                        for c in msg.tool_calls]})
        for call in msg.tool_calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = None
            if name not in TOOL_NAMES or not isinstance(args, dict):
                content = f"ERROR: invalid call to {name}"
            else:
                # Same executor as Claude: injects patient_id from the token, checks the role, audits.
                _, _, content = ctx.call(name, args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": content})
    return ""  # ran out of steps -> grounded not-found


AGENT_SUMMARY_PROMPT = (
    "You write a 2-3 sentence overview of a surgery readiness check for the patient. Use ONLY the facts given. "
    "End every sentence with the [Sx] tags of the facts it uses, copied exactly. Copy numbers and dates exactly. "
    "Do not give medical advice. Do not list every detail - the steps are shown separately. "
    "IMPORTANT: nothing in the plan has been booked or submitted yet. Describe slots as 'proposed' and say the "
    "plan is waiting for the patient's approval - never say a test is booked or scheduled unless a fact says "
    "'already booked'.")


def _agent_summary(mode: str, facts: str) -> str:
    """Optional LLM overview for the agent card. Any failure just means 'no summary'."""
    global _llm_cooldown_until
    if mode == "llm" and time.time() >= _llm_cooldown_until:
        try:
            r = _llm().chat.completions.create(
                model=config.llm_model(), max_tokens=250, temperature=0,
                messages=[{"role": "system", "content": AGENT_SUMMARY_PROMPT}, {"role": "user", "content": facts}])
            return r.choices[0].message.content or ""
        except Exception as e:
            if getattr(e, "status_code", None) == 429:
                _llm_cooldown_until = time.time() + _retry_after_seconds(e)
            log.warning("Agent summary skipped (%s)", e)
    elif mode == "claude":
        try:
            r = _anthropic().messages.create(model=config.model(), max_tokens=250, system=AGENT_SUMMARY_PROMPT,
                                             messages=[{"role": "user", "content": facts}])
            return "".join(b.text for b in r.content if b.type == "text")
        except Exception as e:
            log.warning("Agent summary skipped (%s)", e)
    return ""


def _run_agent(user_ctx, execute_tool, on_event, t0, mode) -> dict:
    ctx = RunContext(user_ctx, execute_tool, on_event)
    ctx.emit({"type": "agent", "name": surgery_readiness.NAME, "title": surgery_readiness.TITLE})
    result = surgery_readiness.run(ctx)

    summary = ""
    if mode in ("llm", "claude") and len(result["steps"]) > 1:
        ctx.emit({"type": "status", "text": "Writing a short summary"})
        draft, s_status = verify_grounding(_agent_summary(mode, result["draft"]), ctx.sources)
        summary = draft if s_status == "ok" else ""

    ctx.emit({"type": "status", "text": "Verifying every fact against its source"})
    answer, status = verify_grounding(result["draft"], ctx.sources)
    steps = []
    for s in result["steps"]:
        details = []
        for d in s["details"]:
            checked, ok = verify_grounding(d, ctx.sources)
            if ok == "ok":
                details.append(checked)
        steps.append({**s, "details": details})
    if summary:
        answer = f"{summary}\n\n{answer}"
    resp = _response(answer, status, "agent", ctx, mode="agent", t0=t0)
    resp["agent"] = {"name": surgery_readiness.NAME, "title": surgery_readiness.TITLE, "steps": steps,
                     "summary": summary or None, "summary_by": mode if summary else None}
    return resp


def _build_cards(ctx: RunContext, intent: str) -> list[dict]:
    cards = []
    data = ctx.tool_data
    if intent == "agent":  # the agent card shows the steps; only the coverage card adds something
        cov = (data.get("check_coverage") or [None])[-1]
        return [{"type": "coverage", "data": cov}] if cov and cov.get("covered") is not None else []
    if data.get("get_lab_results"):
        cards += [{"type": "lab_result", "data": r} for r in data["get_lab_results"][-1][:8]]
    if data.get("get_appointments") and intent == "personal_data":
        cards.append({"type": "appointments", "data": {"items": data["get_appointments"][-1]}})
    if data.get("check_coverage") and data["check_coverage"][-1].get("covered") is not None:
        cards.append({"type": "coverage", "data": data["check_coverage"][-1]})
    for orders in data.get("get_orders", []):
        pre = [o for o in orders if o["type"] == "pre_op"]
        if pre:
            cards.append({"type": "pending_tests", "data": {
                "procedure": pre[0]["linked_procedure"],
                "items": [{"name": o["description"], "status": o["status"], "completed_date": o["completed_date"]}
                          for o in pre]}})
    if data.get("find_department"):
        cards.append({"type": "department", "data": {"items": data["find_department"][-1]}})
    return cards


def _response(answer, status, intent, ctx=None, *, mode, t0, diagnosis=False, fallback=None):
    citations = ctx.citations(answer) if ctx and status == "ok" else []
    cited = [ctx.by_id(c["id"]) for c in citations] if ctx else []
    if status == "ok" and cited and all(s["kind"] == "empty" for s in cited):
        status = "not_found"  # the only thing we can cite is "no records found"
    if status == "ok":
        today = date.today()
        for s in cited:
            if s["source_type"] == "document" and s.get("date"):
                try:
                    if (today - date.fromisoformat(s["date"])).days > 365:
                        answer = f"{answer}\n\n{STALE_NOTE}"
                        break
                except ValueError:
                    pass
    if diagnosis and status in ("ok", "not_found"):
        answer = f"{answer}\n\n{guardrails.DIAGNOSIS_NOTE}"

    disclaimer = None
    if intent in ("lab_result", "multi_step") or diagnosis or any(s.get("doc_type") == "clinical_protocol"
                                                                    for s in cited):
        disclaimer = DISCLAIMER
    elif intent == "eligibility" and status == "ok":
        disclaimer = COVERAGE_DISCLAIMER

    ok = status == "ok"
    return {
        "answer": answer,
        "status": status,
        "intent": intent,
        "citations": citations,
        "tool_calls": ctx.tool_log if ctx else [],
        "cards": _build_cards(ctx, intent) if (ctx and ok) else [],
        "action_required": ctx.action_required if (ctx and ok) else None,
        "disclaimer": disclaimer,
        "mode": mode,
        "fallback_reason": fallback,  # why an LLM answer fell back to offline (debug panel), else None
        "latency_ms": int((time.time() - t0) * 1000),
    }


def answer_query(message: str, user_ctx: dict, history: list[dict] | None = None, execute_tool=None,
                 on_event=None) -> dict:
    """execute_tool(name, args, user_ctx) is provided by the backend (it injects patient_id and authorizes).
    on_event(dict), if given, receives live progress events (tool calls, agent steps) for streaming."""
    global _llm_cooldown_until
    t0 = time.time()
    history = history or []
    message = (message or "").strip()

    blocked = guardrails.check_input(message, user_ctx)
    if blocked:
        return _response(blocked["answer"], blocked["status"], "out_of_scope", mode="guardrail", t0=t0)
    if guardrails.is_medical_advice_request(message):
        return _response(guardrails.MEDICAL_ADVICE_MSG, "ok", "out_of_scope", mode="guardrail", t0=t0)
    diagnosis = guardrails.asks_for_diagnosis(message)

    mode = config.ai_mode()
    first = classify_rules(message, history)
    if first["intent"] == "agent" or first.get("route") == "book_test":
        if user_ctx.get("role") != "patient":
            return _response(AGENT_PATIENTS_ONLY_MSG, "ok", "out_of_scope", mode="guardrail", t0=t0)
        if first["intent"] == "agent":
            return _run_agent(user_ctx, execute_tool, on_event, t0, mode)
        # Booking a test runs as a fixed workflow (reliable, no LLM tokens) in every mode.
        ctx = RunContext(user_ctx, execute_tool, on_event)
        draft = test_booking.run(ctx, first["text"])
        ctx.emit({"type": "status", "text": "Verifying every fact against its source"})
        answer, status = verify_grounding(draft, ctx.sources)
        return _response(answer, status, "action", ctx, mode="workflow", t0=t0)

    ctx = RunContext(user_ctx, execute_tool, on_event)
    draft = ""
    fallback = None
    if mode == "claude":
        try:
            intent = classify(message, history, _anthropic())["intent"]
            draft = _claude_loop(message, history, ctx)
        except Exception as e:  # API/network problem -> deterministic fallback, never a crash
            log.warning("Claude unavailable (%s); falling back to offline pipeline", e)
            mode, fallback = "offline", "claude_error"
            ctx.reset()
    if mode == "llm":
        if time.time() < _llm_cooldown_until:
            mode, fallback = "offline", "llm_rate_limited"
        else:
            try:
                intent = classify_rules(message, history)["intent"]  # also picks the tools to send
                draft = _llm_loop(message, history, ctx, intent)
            except Exception as e:  # API/network problem -> deterministic fallback, never a crash
                mode = "offline"
                ctx.reset()
                if getattr(e, "status_code", None) == 429:
                    wait = _retry_after_seconds(e)
                    _llm_cooldown_until = time.time() + wait
                    fallback = "llm_rate_limited"
                    log.warning("LLM rate limit reached; answering offline for the next %.0fs", wait)
                else:
                    fallback = "llm_error"
                    log.warning("LLM %s unavailable (%s); falling back to offline pipeline",
                                config.llm_model(), e)
    if mode == "offline":
        cls = classify_rules(message, history)
        intent = cls["intent"]
        draft = offline.run(cls, ctx)

    ctx.emit({"type": "status", "text": "Verifying every fact against its source"})
    answer, status = verify_grounding(draft, ctx.sources)
    if status == "not_found" and any(s["kind"] == "empty" for s in ctx.sources):
        # A record lookup ran and found nothing - say that, not "not in the hospital's policies".
        answer = NO_RECORDS_MSG
    return _response(answer, status, intent, ctx, mode=mode, t0=t0, diagnosis=diagnosis, fallback=fallback)
