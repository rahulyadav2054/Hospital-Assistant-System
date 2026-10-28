"""Deterministic offline pipeline (used when no ANTHROPIC_API_KEY is configured, or if the API fails).

It uses the SAME retrieval, tools, source labelling and grounding verifier as the Claude path, but writes
answers extractively from templates, so every sentence is tagged with the source it came from.
"""
import re
from datetime import date, timedelta

from .grounding import split_sentences
from .sources import RunContext, num, when

STOP = {"a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "in", "on", "for", "and", "or", "my", "i",
        "me", "do", "does", "what", "how", "can", "you", "your", "it", "at", "with", "this", "that", "there",
        "have", "has", "any", "about", "please", "tell", "show", "which", "when", "where", "who", "will", "should",
        "would", "could", "much", "many", "get", "need", "from", "by", "as", "if", "be", "am", "we", "our"}

DEPT_WORDS = [
    ("General Medicine", ["general medicine", "general physician", "physician", "gp", "follow-up", "follow up"]),
    ("Cardiology", ["cardiology", "cardiac", "cardiologist", "heart"]),
    ("Orthopedics", ["orthopedics", "orthopaedics", "orthopedic", "ortho", "knee", "bone", "joint"]),
    ("Endocrinology", ["endocrinology", "endocrinologist", "diabetes", "thyroid"]),
    ("General Surgery", ["general surgery", "surgery", "surgeon", "surgical"]),
    ("Radiology", ["radiology", "mri", "ct scan", "x-ray", "xray"]),
]
LAB_WORDS = re.compile(r"\b(fasting blood sugar|fasting sugar|fasting glucose|blood sugar|sugar|glucose|hba1c|a1c|"
                       r"cholesterol|lipid|ha?emoglobin|cbc|complete blood count|blood count|platelets?|wbc|"
                       r"creatinine)\b", re.I)


def _stem(w: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if len(w) > 4 and w.endswith(suf):
            return w[: -len(suf)]
    return w


def _terms(t: str) -> set[str]:
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in STOP and len(w) > 1}


def detect_department(text: str) -> str | None:
    t = text.lower()
    for name, words in DEPT_WORDS:
        if any(re.search(rf"\b{re.escape(w)}\b", t) for w in words):
            return name
    return None


def extract(text: str, query: str, numbered: bool, max_sentences: int = 3) -> list[str]:
    """Pick the passage sentences that answer the query (extractive = grounded by construction)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    steps = [ln for ln in lines if re.match(r"^\d+\.\s", ln)]
    if numbered and steps:
        return steps
    sents = [s for ln in lines for s in split_sentences(ln)]
    if len(sents) <= 4:
        return sents  # short section: the reranker already judged all of it relevant
    q = _terms(query)
    scored = [(len(q & _terms(s)), i, s) for i, s in enumerate(sents)]
    best = sorted([x for x in scored if x[0] > 0], key=lambda x: (-x[0], x[1]))[:max_sentences]
    if not best:
        return sents[:2]
    return [s for _, _, s in sorted(best, key=lambda x: x[1])]


def best_sentence(chunks: list[dict], ids: list[str], must: list[str]) -> tuple[str, str] | None:
    for c, sid in zip(chunks, ids):
        for ln in c["text"].splitlines():
            for s in split_sentences(ln):
                if all(m.lower() in s.lower() for m in must):
                    return s, sid
    return None


def _cite(sentence: str, sid: str) -> str:
    """'Text.' -> 'Text [S1].'"""
    s = sentence.rstrip()
    if s and s[-1] in ".!?":
        return f"{s[:-1]} [{sid}]{s[-1]}"
    return f"{s} [{sid}]"


def _tag(passage: str, sid: str) -> str:
    """Tag every sentence of an extracted passage with its source."""
    return " ".join(_cite(s, sid) for s in split_sentences(passage))


def _empty(ids: list[str], message: str) -> str:
    return f"{message} [{ids[0]}]." if ids else ""


# ---------------------------------------------------------------------------- handlers
def _docs(ctx: RunContext, query: str, intent: str, doc_type: str | None = None) -> str:
    args = {"query": query}
    if doc_type:
        args["doc_type"] = doc_type
    out, ids, _ = ctx.call("search_hospital_docs", args)
    chunks = out.get("data") or []
    if not chunks:
        return ""
    top, sid = chunks[0], ids[0]
    numbered = intent == "procedure" or bool(re.search(r"\b(steps?|how (do|can|to)|what should i do)\b", query, re.I))
    sents = extract(top["text"], query, numbered)
    if numbered and sents and re.match(r"^\d+\.\s", sents[0]):
        return "Here are the approved steps:\n" + "\n".join(_tag(s, sid) for s in sents)
    return " ".join(_tag(s, sid) for s in sents)


def _directory(ctx: RunContext, text: str) -> str:
    out, ids, _ = ctx.call("find_department", {"symptom_or_specialty": text})
    if not out.get("ok"):
        return _docs(ctx, text, "policy", doc_type="directory")
    lines = ["Here is the department that can help:"]
    for d, sid in zip(out["data"], ids):
        lines.append(f"- {d['department']}: {d['location']}, phone {d['phone']}, hours {d['hours']} [{sid}]")
    return "\n".join(lines)


def _personal(ctx: RunContext, text: str) -> str:
    dept = detect_department(text)
    status = "past" if re.search(r"\b(past|previous|last|earlier|completed)\b", text, re.I) else "upcoming"
    args = {"status": status}
    if dept:
        args["department"] = dept
    out, ids, _ = ctx.call("get_appointments", args)
    if not out.get("ok"):
        return _empty(ids, f"I couldn't find any {status} {dept + ' ' if dept else ''}appointments in your record")
    lines = [f"Here are your {status} appointments:"]
    for a, sid in zip(out["data"], ids):
        loc = f", {a['location']}" if a.get("location") else ""
        lines.append(f"- {a['department']} with {a['doctor']} on {when(a['start'])}{loc} [{sid}]")
    return "\n".join(lines)


def _labs(ctx: RunContext, text: str) -> str:
    m = LAB_WORDS.search(text)
    trend = bool(re.search(r"\b(trend|history|all|over time|previous|past|over the|changed)\b", text, re.I))
    args = {"latest_only": not trend}
    if m:
        args["test_name"] = m.group(0)
    out, ids, _ = ctx.call("get_lab_results", args)
    if not out.get("ok"):
        return _empty(ids, "I couldn't find matching lab results in your record")
    lines = ["Here are your results over time:" if trend else "Here are your latest results:"]
    for r, sid in zip(out["data"], ids):
        lines.append(f"- {r['test']}: {num(r['value'])} {r['unit']} on {r['date']} (reference range "
                     f"{r['ref_range']} {r['unit']}, marked {r['flag']}) [{sid}]")
    return "\n".join(lines)


def _eligibility(ctx: RunContext, text: str) -> str:
    out, ids, _ = ctx.call("check_coverage", {"procedure_name": text})
    if not out.get("ok"):
        return _empty(ids, "I couldn't check your coverage")
    d, sid = out["data"], ids[0]
    if d.get("covered") is None:
        return f"{d['reasons'][0]} [{sid}]"
    if d["covered"]:
        lines = [f"Yes, {d['procedure']} is covered under your {d['plan']} plan at {d['coverage_pct']}% [{sid}]."]
        if d["prior_auth_required"]:
            lines.append(f"Prior authorization is required before the procedure [{sid}].")
        if d.get("est_patient_cost") is not None:
            lines.append(f"Your estimated cost is INR {d['est_patient_cost']:,}, including the INR "
                         f"{d['deductible']:,} deductible [{sid}].")
    else:
        lines = [f"No, {d['procedure']} is not covered under your {d['plan']} plan [{sid}].",
                 f"Reason: {d['reasons'][0]} [{sid}]."]
    # Cite the matching clause of the patient's own plan document.
    doc_id = (d.get("plan_doc_ref") or "").split(" ")[0]
    reasons = " ".join(d["reasons"])
    proc_words = ["cosmetic"] if "cosmetic" in d["procedure"].lower() else d["procedure"].lower().split()[-2:]
    if "expired" in reasons or "starts on" in reasons:
        query, must = "coverage applies only while the member's policy is active", ["policy is active"]
    elif "waiting period" in reasons:
        query, must = f"{d['procedure']} waiting period", proc_words + ["waiting period"]
    elif not d["covered"]:
        query, must = f"{d['procedure']} not covered exclusions", proc_words + ["not covered"]
    else:
        query, must = f"{d['procedure']} covered at", proc_words + ["covered at"]
    sout, sids, _ = ctx.call("search_hospital_docs", {"query": f"{d['plan']} {query}", "doc_type": "insurance"})
    chunks = [(c, i) for c, i in zip(sout.get("data") or [], sids) if c["doc_id"] == doc_id]
    hit = best_sentence([c for c, _ in chunks], [i for _, i in chunks], must) if chunks else None
    if hit:
        lines.append(_cite(f"Your plan document says: {hit[0]}", hit[1]))
    return "\n".join(lines)


def _multi_step(ctx: RunContext, text: str) -> str:
    pout, pids, _ = ctx.call("get_orders", {"order_type": "procedure"})
    if not pout.get("ok"):
        return _empty(pids, "I couldn't find a recommended surgery or procedure in your record")
    procs = list(zip(pout["data"], pids))
    proc, proc_sid = next(((o, s) for o, s in procs if o["status"] == "pending"), procs[0])
    lines = [f"Your doctor has recommended: {proc['description']}, ordered by {proc['ordered_by']} "
             f"on {proc['ordered_date']} [{proc_sid}]."]

    sout, sids, _ = ctx.call("search_hospital_docs", {
        "query": "standard pre-operative panel required tests for major elective surgery",
        "doc_type": "clinical_protocol"})
    chunks = sout.get("data") or []
    hit = best_sentence(chunks, sids, ["pre-operative panel"])
    if hit:
        lines.append(_cite(*hit))

    oout, oids, _ = ctx.call("get_orders", {"order_type": "pre_op"})
    if not oout.get("ok"):
        lines.append(_empty(oids, "No pre-operative test orders are in your record yet"))
    else:
        rel = [(o, s) for o, s in zip(oout["data"], oids) if o["linked_procedure"] == proc["linked_procedure"]]
        rel = rel or list(zip(oout["data"], oids))
        done = [(o, s) for o, s in rel if o["status"] == "completed"]
        pending = [(o, s) for o, s in rel if o["status"] != "completed"]
        if done:
            lines.append("Completed: " + ", ".join(f"{o['description']} on {o['completed_date']} [{s}]"
                                                    for o, s in done) + ".")
        if pending:
            lines.append("Still pending: " + ", ".join(f"{o['description']} [{s}]" for o, s in pending) + ".")
        else:
            lines.append("All pre-operative tests ordered for this procedure are completed "
                         + " ".join(f"[{s}]" for _, s in rel) + ".")

    wout, wids, _ = ctx.call("search_hospital_docs", {
        "query": "where to complete pre-operative ECG chest X-ray blood tests", "doc_type": "clinical_protocol"})
    where = best_sentence(wout.get("data") or [], wids, ["ECG and Chest X-ray are done"])
    if where:
        lines.append(_cite(*where))
    rule = best_sentence(wout.get("data") or [], wids, ["cannot be scheduled"])
    if rule:
        lines.append(_cite(*rule))
    return "\n".join(lines)


def _action(ctx: RunContext, text: str) -> str:
    if re.search(r"\bcancel", text, re.I):
        return _docs(ctx, "rescheduling and cancellation of appointments 24 hours", "policy", doc_type="policy")
    dept = detect_department(text)
    args = {"status": "upcoming"}
    if dept:
        args["department"] = dept
    out, ids, _ = ctx.call("get_appointments", args)
    if not out.get("ok"):
        return _empty(ids, f"I couldn't find an upcoming {dept + ' ' if dept else ''}appointment to reschedule")
    appts = list(zip(out["data"], ids))
    day = None
    if re.search(r"\btomorrow\b", text, re.I):
        day = date.today() + timedelta(days=1)
    elif re.search(r"\btoday\b", text, re.I):
        day = date.today()
    if day:
        appts = [(a, s) for a, s in appts if a["start"][:10] == day.isoformat()] or appts
    if len(appts) > 1:
        lines = ["Which appointment would you like to reschedule?"]
        lines += [f"- {a['department']} with {a['doctor']} on {when(a['start'])} [{s}]" for a, s in appts]
        return "\n".join(lines)

    appt, asid = appts[0]
    lines = [f"I found your {appt['department']} appointment with {appt['doctor']} on {when(appt['start'])} [{asid}]."]
    slot_args = {"appointment_id": appt["appointment_id"]}
    if re.search(r"\bnext week\b", text, re.I):
        today = date.today()
        slot_args["from_date"] = (today + timedelta(days=7 - today.weekday())).isoformat()
    sout, sids, _ = ctx.call("get_available_slots", slot_args)
    if not sout.get("ok"):
        lines.append(_empty(sids, "There are no free slots with this doctor right now"))
        return "\n".join(lines)
    slots = list(zip(sout["data"], sids))
    slot, slot_sid = slots[0]
    pout, pids, _ = ctx.call("propose_reschedule", {"appointment_id": appt["appointment_id"],
                                                    "slot_id": slot["slot_id"]})
    if not pout.get("ok"):
        if pids:
            lines.append(_cite(f"I can't reschedule this appointment: {ctx.by_id(pids[0])['text']}.", pids[0]))
        return "\n".join(lines)
    lines.append(f"The earliest available slot with {slot['doctor']} is {when(slot['start'])} [{slot_sid}].")
    if len(slots) > 1:
        lines.append("Other available slots: " + ", ".join(f"{when(s['start'])} [{sid}]" for s, sid in slots[1:4])
                     + ".")
    lines.append(f"I have prepared this change, but nothing changes until you confirm it [{pids[0]}].")
    lines.append("Please confirm the change in the app.")
    return "\n".join(lines)


def run(cls: dict, ctx: RunContext) -> str:
    """Produce a tagged draft answer for an already-classified message."""
    text, intent = cls["text"], cls["intent"]
    if intent == "out_of_scope":
        return ""
    if cls.get("route") == "directory":
        return _directory(ctx, text)
    if intent == "personal_data":
        return _personal(ctx, text)
    if intent == "lab_result":
        return _labs(ctx, text)
    if intent == "eligibility":
        return _eligibility(ctx, text)
    if intent == "multi_step":
        return _multi_step(ctx, text)
    if intent == "action":
        return _action(ctx, text)
    return _docs(ctx, text, intent)
