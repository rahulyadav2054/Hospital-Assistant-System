"""Proactive Care Agent.

Runs without being asked: the UI calls it at login (GET /me/notifications) and shows the results in the bell.
It can also be asked in chat ("check my reminders"). It only READS records and suggests next steps; every
suggestion carries a ready-made request that starts the right agent with one click.

  1. upcoming appointments    within 2 days -> reminder (+ 24-hour change rule)
  2. pending tests            not booked -> "Book my <test>"; blood tests -> walk-in
  3. results                  outside reference range -> "what should I do next?" (Lab Follow-up Agent)
  4. insurance policy         expired / expiring within 60 days
  5. surgery preparation      recommended surgery + prior authorization needed -> Surgery Readiness Agent
"""
from datetime import date, timedelta

from ..sources import when
from .base import BOOKABLE_TESTS, BaseAgent, _cite, test_key


class ProactiveCareAgent(BaseAgent):
    NAME = "proactive_care"
    TITLE = "Proactive Care Agent"
    ICON = "🔔"

    def __init__(self, ctx, text: str = ""):
        super().__init__(ctx, text)
        self.notifications: list[dict] = []

    def _notify(self, key, level, title, text, action_label=None, action_prompt=None):
        self.notifications.append({"id": key, "level": level, "title": title, "text": text,
                                   "action_label": action_label, "action_prompt": action_prompt})

    def run(self) -> dict:
        ctx = self.ctx
        today = date.today()

        # 1. Appointments -------------------------------------------------------------------------
        step = self._start("Check upcoming appointments")
        out, ids, _ = ctx.call("get_appointments", {"status": "upcoming"})
        details = []
        for a, sid in zip(out.get("data") or [], ids if out.get("ok") else []):
            d = date.fromisoformat(a["start"][:10])
            if d <= today + timedelta(days=2):
                text = _cite(f"{a['department']} with {a['doctor']} on {when(a['start'])}.", sid)
                details.append(text)
                prompt = "Plan my visit tomorrow" if d == today + timedelta(days=1) else \
                    ("Plan my visit today" if d == today else f"Plan my visit on {d.strftime('%A')}")
                self._notify(f"apt-{a['appointment_id']}", "info", "Appointment soon", text, "Plan my visit", prompt)
        if details:
            rule = self.doc_sentence("rescheduling cancellation 24 hours before the appointment", "policy",
                                     ["24 hours"])
            if rule:
                details.append(_cite(*rule))
        self._finish(step, "done", details or [self._empty(
            ids, "No appointments in the next two days") if not out.get("ok") else
            _cite("No appointments in the next two days.", *ids)])

        # 2. Pending tests ------------------------------------------------------------------------
        step = self._start("Check pending tests")
        out, ids, _ = ctx.call("get_orders", {"status": "pending"})
        details = []
        for o, sid in zip(out.get("data") or [], ids if out.get("ok") else []):
            if o["type"] not in ("pre_op", "lab", "imaging"):
                continue
            if o.get("scheduled_at"):
                details.append(_cite(f"{o['description']} is booked for {when(o['scheduled_at'])}.", sid))
                continue
            text = _cite(f"{o['description']} is still pending.", sid)
            details.append(text)
            if test_key(o["description"]) in BOOKABLE_TESTS:
                self._notify(f"ord-{o['order_id']}", "action", "Test to book", text, "Book it",
                             f"Book my {o['description']}")
            else:
                self._notify(f"ord-{o['order_id']}", "info", "Walk-in test (no booking needed)", text,
                             "Plan my visit", "Plan my next visit")
        self._finish(step, "warning" if details else "done",
                     details or [_cite("You have no pending tests.", *ids[:1])])

        # 3. Results ------------------------------------------------------------------------------
        step = self._start("Check your latest results")
        out, ids, _ = ctx.call("get_lab_results", {"latest_only": True})
        details = []
        for r, sid in zip(out.get("data") or [], ids if out.get("ok") else []):
            if r["flag"] == "normal":
                continue
            text = _cite(f"{r['test']} was {r['value']:g} {r['unit']} on {r['date']}, outside the reference range "
                         f"{r['ref_range']} {r['unit']} (marked {r['flag']}).", sid)
            details.append(text)
            self._notify(f"lab-{r['lab_id']}", "warning", "Result to follow up", text, "Next steps",
                         f"My {r['test']} result is {r['flag']}, what should I do next?")
        self._finish(step, "warning" if details else "done",
                     details or ([_cite("All your latest results are within their reference ranges.", *ids)]
                                 if out.get("ok") else []))

        # 4. Insurance ----------------------------------------------------------------------------
        step = self._start("Check your insurance policy")
        out, ids, _ = ctx.call("get_policy_status", {})
        p, sid = (out["data"], ids[0]) if out.get("ok") and ids else (None, None)
        if p and p["status"] == "expired":
            text = _cite(f"Your {p['plan']} policy expired on {p['coverage_end']}.", sid)
            self._notify("policy", "warning", "Insurance expired - contact the Billing Desk", text)
            self._finish(step, "warning", [text])
        elif p and p["days_left"] <= 60:
            text = _cite(f"Your {p['plan']} policy ends on {p['coverage_end']} ({p['days_left']} days left).", sid)
            self._notify("policy", "warning", "Insurance renewal", text)
            self._finish(step, "warning", [text])
        else:
            self._finish(step, "done", [_cite(f"Your {p['plan']} policy is active until {p['coverage_end']}.", sid)]
                         if p else [])

        # 5. Surgery preparation ------------------------------------------------------------------
        step = self._start("Check surgery preparation")
        out, ids, _ = ctx.call("get_orders", {"order_type": "procedure", "status": "pending"})
        details = []
        if out.get("ok"):
            proc, psid = out["data"][0], ids[0]
            cout, cids, _ = ctx.call("check_coverage", {"procedure_name": proc["linked_procedure"] or
                                                        proc["description"]})
            cov = cout.get("data") if cout.get("ok") else None
            rout, rids, _ = ctx.call("get_prior_auth_requests", {})
            submitted = rout.get("ok") and any(r["procedure_code"] == (cov or {}).get("procedure_code")
                                               for r in rout["data"])
            if cov and cov.get("covered") and cov.get("prior_auth_required") and not submitted:
                text = _cite(f"{proc['description']} is recommended and needs prior authorization, which has not "
                             f"been submitted yet.", psid, cids[0])
                details.append(text)
                self._notify(f"surgery-{proc['order_id']}", "action", "Surgery preparation", text,
                             "Get me ready", "Get me ready for my surgery")
            else:
                details.append(_cite(f"{proc['description']} is recommended; no surgery paperwork is waiting on you.",
                                     psid, *(cids[:1] if cov else [])))
        self._finish(step, "warning" if any("prior authorization" in d for d in details) else "done",
                     details or [self._empty(ids, "No surgery is waiting to be prepared")])

        order = {"warning": 0, "action": 1, "info": 2}
        self.notifications.sort(key=lambda n: order[n["level"]])
        self.cards.append({"type": "notifications", "data": {"items": self.notifications}})
        return self._result()
