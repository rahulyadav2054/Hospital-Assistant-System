"""RunContext: executes tools for one request and turns every chunk / record into a numbered SOURCE [Sx].

The LLM (or the offline pipeline) may only state facts that it can tag with one of these sources.
"""
from datetime import datetime

from . import retriever

EMPTY_TEXT = "No matching records were found in the patient's record for this request."


def when(iso: str) -> str:
    """'2026-11-04T10:30' -> 'Wed 04 Nov 2026 at 10:30 (10:30 AM)'. Used in sources AND answers so they match."""
    d = datetime.fromisoformat(iso)
    return f"{d:%a %d %b %Y} at {d:%H:%M} ({d.strftime('%I:%M %p').lstrip('0')})"


def num(v) -> str:
    return f"{v:g}" if isinstance(v, (int, float)) else str(v)


# Human-readable progress labels streamed to the UI while tools run.
TOOL_LABELS = {
    "search_hospital_docs": "Searching hospital documents",
    "get_appointments": "Checking your appointments",
    "get_lab_results": "Reading your lab results",
    "get_orders": "Checking your doctor's orders",
    "check_coverage": "Checking insurance coverage",
    "get_available_slots": "Finding free appointment slots",
    "propose_reschedule": "Preparing the reschedule",
    "find_department": "Looking up departments",
    "get_test_slots": "Finding test slots",
    "get_prior_auth_requests": "Checking prior-authorization requests",
    "propose_care_plan": "Preparing your plan",
    "get_doctors": "Finding doctors",
    "get_policy_status": "Checking your insurance policy",
}


class RunContext:
    def __init__(self, user_ctx: dict, execute_tool, on_event=None):
        self.user_ctx = user_ctx
        self.execute_tool = execute_tool
        self.on_event = on_event
        self._seq = 0
        self.reset()

    def emit(self, event: dict) -> None:
        """Send a progress event to the streaming client (never let a UI problem break the answer)."""
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:
                pass

    def reset(self):
        self.sources: list[dict] = []
        self._by_key: dict[str, str] = {}
        self.tool_log: list[dict] = []
        self.tool_data: dict[str, list] = {}
        self.action_required: dict | None = None

    # ------------------------------------------------------------------ sources
    def add_source(self, key: str, *, source_type: str, title: str, text: str, section=None, ref=None, date=None,
                   doc_type=None, kind="data") -> str:
        if key in self._by_key:
            return self._by_key[key]
        sid = f"S{len(self.sources) + 1}"
        self._by_key[key] = sid
        self.sources.append({"id": sid, "source_type": source_type, "title": title, "section": section, "ref": ref,
                             "date": date, "text": text, "doc_type": doc_type, "kind": kind})
        return sid

    def by_id(self, sid: str) -> dict | None:
        return next((s for s in self.sources if s["id"] == sid), None)

    # ------------------------------------------------------------------ tools
    def call(self, name: str, args: dict | None):
        """Run one tool. Returns (raw_result, [source ids], text block for the LLM)."""
        args = dict(args or {})
        self._seq += 1
        seq, label = self._seq, TOOL_LABELS.get(name, name)
        self.emit({"type": "tool", "seq": seq, "name": name, "label": label, "status": "running"})
        if name == "search_hospital_docs":
            clean = {k: args[k] for k in ("query", "doc_type") if k in args}
            try:
                out = {"ok": True, "data": retriever.search(**clean)}
            except TypeError:
                out = {"ok": False, "error": "invalid: query is required"}
        elif self.execute_tool is None:
            out = {"ok": False, "error": "unavailable"}
        else:
            out = self.execute_tool(name, args, self.user_ctx)
        self.tool_log.append({"name": name, "ok": bool(out.get("ok"))})
        if out.get("ok"):
            self.tool_data.setdefault(name, []).append(out["data"])
        ids, text = self._label(name, args, out)
        if name == "propose_reschedule" and out.get("ok"):
            d = out["data"]
            self.action_required = {"type": "confirm_reschedule", "pending_action_id": d["pending_action_id"],
                                    "summary": d["summary"], "expires_at": d["expires_at"],
                                    "appointment_id": d["appointment_id"], "new_start": d["new_start"]}
        if name == "propose_care_plan" and out.get("ok"):
            d = out["data"]
            self.action_required = {"type": "confirm_plan", "pending_action_id": d["pending_action_id"],
                                    "summary": d["summary"], "items": d["items"], "expires_at": d["expires_at"]}
        self.emit({"type": "tool", "seq": seq, "name": name, "label": label,
                   "status": "done" if out.get("ok") else "failed"})
        return out, ids, text

    def _block(self, sid: str) -> str:
        s = self.by_id(sid)
        meta = ", ".join(str(x) for x in (s["title"], s["section"], s["ref"], s["date"]) if x)
        return f"SOURCE [{sid}] ({s['source_type']}: {meta})\n{s['text']}"

    def _label(self, name: str, args: dict, out: dict):
        if not out.get("ok"):
            err = str(out.get("error", "error"))
            if err.startswith("invalid:"):
                msg = err.split(":", 1)[1].strip()
                sid = self.add_source(f"err:{name}:{msg}", source_type="record", title="Hospital system response",
                                      text=msg, kind="error")
                return [sid], self._block(sid)
            if err == "not_found" and name != "search_hospital_docs":
                sid = self.add_source(f"empty:{name}:{sorted(args.items())}", source_type="record",
                                      title="Patient record search", text=EMPTY_TEXT, kind="empty")
                return [sid], self._block(sid)
            if err == "forbidden":
                return [], "ERROR: forbidden - the current user is not allowed to use this tool."
            return [], f"ERROR: {err}"

        data = out["data"]
        ids: list[str] = []
        if name == "search_hospital_docs":
            if not data:
                return [], "No matching hospital documents were found."
            for c in data:
                ids.append(self.add_source(f"doc:{c['chunk_id']}", source_type="document", title=c["title"],
                                           section=c["section"], ref=c["chunk_id"], date=c["effective_date"],
                                           text=c["text"], doc_type=c["doc_type"]))
        elif name == "get_appointments":
            for a in data:
                loc = f", location {a['location']}" if a.get("location") else ""
                ids.append(self.add_source(
                    f"apt:{a['appointment_id']}:{a['start']}", source_type="record",
                    title=f"Appointment {a['appointment_id']}", ref=a["appointment_id"], date=a["start"][:10],
                    text=(f"Appointment {a['appointment_id']} (appointment_id={a['appointment_id']}): {a['department']} "
                          f"with {a['doctor']} (doctor_id={a['doctor_id']}) on {when(a['start'])}{loc}. "
                          f"Status: {a['status']}.")))
        elif name == "get_lab_results":
            for r in data:
                ids.append(self.add_source(
                    f"lab:{r['lab_id']}", source_type="record", title=f"Lab result: {r['test']}", ref=r["lab_id"],
                    date=r["date"],
                    text=(f"{r['test']}: {num(r['value'])} {r['unit']} (reference range {r['ref_range']} {r['unit']}, "
                          f"flag: {r['flag']}), collected on {r['date']}. Lab ID {r['lab_id']}.")))
        elif name == "get_orders":
            for o in data:
                done = f", completed on {o['completed_date']}" if o.get("completed_date") else ""
                if o.get("scheduled_at"):
                    done += f", booked for {when(o['scheduled_at'])}"
                    if o.get("scheduled_location"):
                        done += f" at {o['scheduled_location']}"
                linked = f" for {o['linked_procedure']}" if o.get("linked_procedure") else ""
                ids.append(self.add_source(
                    f"ord:{o['order_id']}", source_type="record", title=f"Order: {o['description']}",
                    ref=o["order_id"], date=o["ordered_date"],
                    text=(f"Order {o['order_id']} ({o['type']}): {o['description']}{linked}. Status: {o['status']}"
                          f"{done}. Ordered by {o['ordered_by']} on {o['ordered_date']}.")))
        elif name == "check_coverage":
            d = data
            if d.get("covered") is None:
                text = " ".join(d["reasons"])
            else:
                text = (f"Coverage decision for {d['procedure']} (procedure code {d['procedure_code']}) under "
                        f"{d['plan']}: {'COVERED' if d['covered'] else 'NOT COVERED'}. "
                        f"Coverage percentage: {d['coverage_pct']}%. "
                        f"Prior authorization required: {'yes' if d['prior_auth_required'] else 'no'}. "
                        + (f"Estimated patient cost: INR {d['est_patient_cost']} (includes the INR {d['deductible']} "
                           f"deductible). " if d.get("est_patient_cost") is not None else "")
                        + f"Reasons: {'; '.join(d['reasons'])}. Rule {d['rule_id'] or 'n/a'}. "
                        f"Plan document: {d['plan_doc_ref']}.")
            ids.append(self.add_source(f"cov:{d.get('procedure')}:{d.get('rule_id')}", source_type="record",
                                       title=f"Coverage check: {d.get('procedure')} ({d['plan']})",
                                       ref=d.get("rule_id") or d.get("plan_doc_ref"), text=text))
        elif name == "get_available_slots":
            for s in data:
                ids.append(self.add_source(
                    f"slot:{s['slot_id']}", source_type="record", title="Available slot", ref=f"slot {s['slot_id']}",
                    date=s["start"][:10],
                    text=(f"Available slot (slot_id={s['slot_id']}): {s['doctor']} ({s['department']}) on "
                          f"{when(s['start'])}.")))
        elif name == "propose_reschedule":
            d = data
            ids.append(self.add_source(
                f"pa:{d['pending_action_id']}", source_type="record", title="Pending reschedule request",
                ref=d["pending_action_id"],
                text=(f"Pending action {d['pending_action_id']}: {d['summary']} (new time {when(d['new_start'])}). "
                      f"NOT yet confirmed - nothing changes until the patient presses Confirm in the app. "
                      f"The request expires at {d['expires_at'][11:16]}.")))
        elif name == "get_doctors":
            for d in data:
                ids.append(self.add_source(
                    f"dr:{d['doctor_id']}", source_type="record", title=f"Doctor: {d['name']}", ref=d["doctor_id"],
                    text=f"{d['name']} (doctor_id={d['doctor_id']}), {d['specialty']}, {d['department']}."))
        elif name == "get_policy_status":
            p = data
            ids.append(self.add_source(
                f"policy:{p['member_id']}", source_type="record", title=f"Insurance policy: {p['plan']}",
                ref=p["member_id"],
                text=(f"Insurance policy {p['plan']} (member {p['member_id']}): status {p['status']}, valid from "
                      f"{p['coverage_start']} to {p['coverage_end']} ({p['days_left']} days left). "
                      f"Plan document {p['plan_doc_ref']}.")))
        elif name == "get_test_slots":
            for s in data:
                ids.append(self.add_source(
                    f"dslot:{s['slot_id']}", source_type="record", title=f"Available {s['service']} slot",
                    ref=f"test slot {s['slot_id']}", date=s["start"][:10],
                    text=(f"Available {s['service']} slot (slot_id={s['slot_id']}) on {when(s['start'])} "
                          f"at {s['location']}.")))
        elif name == "get_prior_auth_requests":
            for r in data:
                ids.append(self.add_source(
                    f"par:{r['request_id']}", source_type="record", title=f"Prior authorization {r['request_id']}",
                    ref=r["request_id"], date=r["submitted_date"],
                    text=(f"Prior-authorization request {r['request_id']} for {r['procedure']} "
                          f"(procedure code {r['procedure_code']}): status {r['status']}, "
                          f"submitted on {r['submitted_date']}.")))
        elif name == "propose_care_plan":
            d = data
            steps = "; ".join(f"{i + 1}) {x['label']} - {x['detail']}" for i, x in enumerate(d["items"]))
            ids.append(self.add_source(
                f"plan:{d['pending_action_id']}", source_type="record", title="Pending care plan",
                ref=d["pending_action_id"],
                text=(f"Pending care plan {d['pending_action_id']}: {steps}. NOT yet confirmed - nothing is booked "
                      f"or submitted until the patient approves it in the app. Expires at {d['expires_at'][11:16]}.")))
        elif name == "find_department":
            for dep in data:
                ids.append(self.add_source(
                    f"dept:{dep['department']}", source_type="record", title=f"Department: {dep['department']}",
                    ref=dep["department"],
                    text=(f"{dep['department']}: location {dep['location']}, phone {dep['phone']}, "
                          f"hours {dep['hours']}.")))
        return ids, "\n\n".join(self._block(i) for i in ids) or "No data."

    # ------------------------------------------------------------------ output helpers
    def citations(self, answer: str) -> list[dict]:
        import re

        used = sorted({int(n) for n in re.findall(r"\[S(\d+)\]", answer)})
        out = []
        for n in used:
            s = self.by_id(f"S{n}")
            if s:
                out.append({k: s[k] for k in ("id", "source_type", "title", "section", "ref", "date")})
        return out
