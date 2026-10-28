"""Book one test the patient asks for: "do the ECG test", "book my chest X-ray tomorrow", "I need an MRI".

order exists? -> already done / already booked? -> walk-in test? -> free slot (on the day asked for) ->
propose a one-item care plan. Nothing is booked until the patient approves it (same two-phase commit as the agent).
"""
import re
from datetime import date, timedelta

from ..sources import RunContext, when
from .surgery_readiness import _TEST_KEYS, _cite, _sentence, test_key

_NAMES = {"cbc": "a Complete Blood Count (CBC)", "ecg": "an Electrocardiogram (ECG)", "xray": "a Chest X-ray",
          "mri": "an MRI scan", "hba1c": "an HbA1c test", "coag": "a coagulation test"}
TEST_ORDER_TYPES = ("pre_op", "imaging", "lab")


def requested_key(text: str) -> str | None:
    t = text.lower()
    for key, words in _TEST_KEYS:
        if any(re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", t) for w in words):
            return key
    return None


def _requested_day(text: str) -> date | None:
    t = text.lower()
    today = date.today()
    if re.search(r"\btomorrow\b", t):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b", t):
        return today
    if re.search(r"\bday after tomorrow\b", t):
        return today + timedelta(days=2)
    return None


def run(ctx: RunContext, text: str) -> str:
    """Returns a tagged draft; sets ctx.action_required when a booking is proposed."""
    key = requested_key(text)
    out, ids, _ = ctx.call("get_orders", {})
    orders = list(zip(out.get("data") or [], ids)) if out.get("ok") else []
    tests = [(o, s) for o, s in orders if o["type"] in TEST_ORDER_TYPES]
    matches = [(o, s) for o, s in tests if key is None or test_key(o["description"]) == key]
    pending = [(o, s) for o, s in matches if o["status"] == "pending"]

    if not pending:
        done = [(o, s) for o, s in matches if o["status"] == "completed"]
        if done and key:
            o, s = done[-1]
            return _cite(f"Your {o['description']} was already completed on {o['completed_date']}, so there is "
                         f"nothing to book.", s)
        name = _NAMES.get(key, "that test")
        evidence = [s for _, s in orders] or ids[:1]  # the record we checked (or "no records found")
        return _cite(f"I couldn't find a pending doctor's order for {name} in your record. A test needs a doctor's "
                     f"order before it can be booked, so please ask your doctor to order it.", *evidence)

    if len(pending) > 1:
        lines = ["Which test would you like to book?"]
        lines += [f"- {_cite(o['description'] + ' (pending).', s)}" for o, s in pending]
        return "\n".join(lines)

    order, osid = pending[0]
    if order.get("scheduled_at"):
        return _cite(f"Your {order['description']} is already booked for {when(order['scheduled_at'])}.", osid)

    lines = [_cite(f"I found your pending order for {order['description']}, ordered by {order['ordered_by']} on "
                   f"{order['ordered_date']}.", osid)]
    sout, sids, _ = ctx.call("get_test_slots", {"test_name": order["description"], "limit": 15})
    if not sout.get("ok"):
        wout, wids, _ = ctx.call("search_hospital_docs", {
            "query": "blood tests laboratory without an appointment", "doc_type": "clinical_protocol"})
        rule = _sentence(wout.get("data") or [], wids, ["without an appointment"])
        if rule:
            lines.append(_cite(*rule))
            lines.append(_cite("This test needs no booking - you can walk in during those hours.", rule[1]))
        return "\n".join(lines)

    slots = list(zip(sout["data"], sids))
    day = _requested_day(text)
    on_day = [(s, i) for s, i in slots if day and s["start"][:10] == day.isoformat()]
    if day and not on_day:
        lines.append(_cite(f"There is no free {slots[0][0]['service']} slot on that day.", *[i for _, i in slots[:3]]))
    slot, slot_sid = (on_day or slots)[0]
    lines.append(_cite(f"The {'first free' if on_day else 'earliest'} {slot['service']} slot is {when(slot['start'])} "
                       f"at {slot['location']}.", slot_sid))
    others = [(s, i) for s, i in slots if s["slot_id"] != slot["slot_id"]][:3]
    if others:
        lines.append("Other free slots: " + ", ".join(_cite(when(s["start"]), i).rstrip(".") for s, i in others) + ".")

    pout, pids, _ = ctx.call("propose_care_plan", {"items": [
        {"type": "book_test", "order_id": order["order_id"], "slot_id": slot["slot_id"]}]})
    if pout.get("ok"):
        lines.append(_cite("Nothing is booked until you approve it below.", pids[0]))
    elif pids:
        lines.append(_cite(f"I could not prepare the booking: {ctx.by_id(pids[0])['text']}.", pids[0]))
    return "\n".join(lines)
