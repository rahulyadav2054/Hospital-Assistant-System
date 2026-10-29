"""Surgery Readiness Agent.

Goal: "get me ready for my surgery". The agent plans and runs a sequence of tool calls with decision points:

  1. find the recommended surgery             (get_orders procedure)        stop if there is none
  2. check insurance coverage                 (check_coverage)              prior auth needed? policy valid?
  3. read the pre-operative protocol          (search_hospital_docs)        which tests, how long they stay valid
  4. compare required tests with the record   (get_orders pre_op)           done+valid / booked / to book / not ordered
  5. find test slots                          (get_test_slots)              earliest day that fits every test; walk-in
  6. check prior authorization                (get_prior_auth_requests)     already submitted?
  7. propose ONE plan for approval            (propose_care_plan)           nothing changes until the patient approves

Every sentence it writes is tagged with the source that supports it, so the normal grounding verifier
checks the agent's output too. The steps run as code (reliable, cheap on rate-limited free tiers);
an LLM, when available, only writes the short summary at the top.
"""
import re
from datetime import date

from ..sources import RunContext, when
from .base import _TEST_KEYS, BaseAgent, _cite, _sentence, test_key  # noqa: F401  (re-exported for test_booking)

NAME = "surgery_readiness"
TITLE = "Surgery Readiness Agent"


class SurgeryReadinessAgent(BaseAgent):
    NAME = NAME
    TITLE = TITLE
    ICON = "🩺"

    # ------------------------------------------------------------------ the plan
    def run(self) -> dict:
        ctx = self.ctx

        # 1. Recommended surgery ---------------------------------------------------------------
        step = self._start("Find your recommended surgery")
        out, ids, _ = ctx.call("get_orders", {"order_type": "procedure"})
        if not out.get("ok"):
            self._finish(step, "stopped", [self._empty(
                ids, "There is no recommended surgery in your record, so there is nothing to prepare yet")])
            return self._result()
        procs = list(zip(out["data"], ids))
        proc, proc_sid = next(((o, s) for o, s in procs if o["status"] == "pending"), procs[0])
        self._finish(step, "done", [_cite(
            f"Your doctor recommended {proc['description']}, ordered by {proc['ordered_by']} on "
            f"{proc['ordered_date']}.", proc_sid)])

        # 2. Insurance ------------------------------------------------------------------------
        step = cov_step = self._start("Check insurance coverage")
        out, ids, _ = ctx.call("check_coverage", {"procedure_name": proc["linked_procedure"] or proc["description"]})
        cov, cov_sid = (out["data"], ids[0]) if out.get("ok") and ids else (None, None)
        if not cov or cov.get("covered") is None:
            self._finish(step, "warning", [_cite(cov["reasons"][0], cov_sid)] if cov else [
                "I could not check your coverage; please contact the Billing and Insurance Desk."])
        elif cov["covered"]:
            details = [_cite(f"{cov['procedure']} is covered at {cov['coverage_pct']}% under {cov['plan']}.",
                             cov_sid)]
            if cov["prior_auth_required"]:
                details.append(_cite("Prior authorization is required before the procedure.", cov_sid))
            if cov.get("est_patient_cost") is not None:
                details.append(_cite(f"Your estimated cost is INR {cov['est_patient_cost']:,}.", cov_sid))
            self._finish(step, "warning" if cov["prior_auth_required"] else "done", details)
        else:
            self._finish(step, "warning", [_cite(
                f"{cov['procedure']} is not covered under {cov['plan']}: {cov['reasons'][0]}.", cov_sid)])

        # 3. Protocol ---------------------------------------------------------------------------
        step = self._start("Read the pre-operative protocol")
        out, ids, _ = ctx.call("search_hospital_docs", {
            "query": "standard pre-operative panel required tests for major elective surgery",
            "doc_type": "clinical_protocol"})
        chunks = out.get("data") or []
        panel = _sentence(chunks, ids, ["pre-operative panel is"])
        validity = _sentence(chunks, ids, ["valid for"])
        if validity is None:
            vout, vids, _ = ctx.call("search_hospital_docs", {
                "query": "how long pre-operative test results are valid", "doc_type": "clinical_protocol"})
            validity = _sentence(vout.get("data") or [], vids, ["valid for"])
        if panel is None:
            self._finish(step, "warning", ["I could not find the pre-operative protocol; please ask your surgeon "
                                           "which tests you need."])
            return self._result()
        required = [t.strip() for t in re.split(r",\s*|\s+and\s+", panel[0].split(":", 1)[1].rstrip(". "))
                    if t.strip()]
        valid_days = int(re.search(r"valid for (\d+) days", validity[0]).group(1)) if validity else None
        self._finish(step, "done", [_cite(*panel), _cite(*validity) if validity else ""])
        protocol_sid = panel[1]

        # 4. Compare with the record ----------------------------------------------------------
        step = self._start("Compare required tests with your record")
        out, ids, _ = ctx.call("get_orders", {"order_type": "pre_op"})
        orders = [(o, s) for o, s in zip(out.get("data") or [], ids)
                  if o.get("linked_procedure") in (None, proc["linked_procedure"])] if out.get("ok") else []
        by_key = {test_key(o["description"]): (o, s) for o, s in orders}
        self.record_sids = [s for _, s in orders] or ids[:1]
        details, to_book, attention = [], [], False
        for test in required:
            hit = by_key.get(test_key(test))
            if hit is None:
                attention = True
                details.append(_cite(f"{test} has not been ordered yet - please ask {proc['ordered_by']} to order "
                                     f"it.", protocol_sid, ids[0] if not out.get("ok") and ids else None))
                continue
            order, sid = hit
            if order["status"] == "completed":
                age = (date.today() - date.fromisoformat(order["completed_date"])).days
                if valid_days is not None and age > valid_days:
                    attention = True
                    details.append(_cite(f"{order['description']} was done on {order['completed_date']}, which is "
                                         f"older than the {valid_days}-day validity window, so it must be repeated.",
                                         sid, validity[1]))
                else:
                    window = f", within the {valid_days}-day validity window" if valid_days else ""
                    details.append(_cite(f"{order['description']} was completed on {order['completed_date']}"
                                         f"{window}.", sid, validity[1] if valid_days else None))
            elif order.get("scheduled_at"):
                details.append(_cite(f"{order['description']} is already booked for {when(order['scheduled_at'])}.",
                                     sid))
            else:
                to_book.append((order, sid))
                details.append(_cite(f"{order['description']} is still pending.", sid))
        self._finish(step, "warning" if (attention or to_book) else "done", details)

        # 5. Slots for pending tests ------------------------------------------------------------
        if to_book:
            step = self._start("Find slots for your pending tests")
            options, walk_in = [], []
            for order, sid in to_book:
                sout, sids, _ = ctx.call("get_test_slots", {"test_name": order["description"], "limit": 15})
                if sout.get("ok"):
                    options.append((order, list(zip(sout["data"], sids))))
                else:
                    walk_in.append((order, sid))
            details = []
            # Prefer the earliest day on which every bookable test has a free slot (one hospital visit).
            if options:
                days = [{s["start"][:10] for s, _ in slots} for _, slots in options]
                common = sorted(set.intersection(*days))
                picked = []
                for order, slots in options:
                    pick = next(((s, i) for s, i in slots if common and s["start"][:10] == common[0]), slots[0])
                    picked.append(pick[1])
                    self.plan_items.append({"type": "book_test", "order_id": order["order_id"],
                                            "slot_id": pick[0]["slot_id"]})
                    details.append(_cite(f"{order['description']}: {pick[0]['service']} slot on "
                                         f"{when(pick[0]['start'])} at {pick[0]['location']}.", pick[1]))
                if len(options) > 1 and common:
                    details.append(_cite("I picked slots on the same day, so you only need one visit.", *picked))
            if walk_in:
                wout, wids, _ = ctx.call("search_hospital_docs", {
                    "query": "blood tests laboratory without an appointment pre-operative",
                    "doc_type": "clinical_protocol"})
                rule = _sentence(wout.get("data") or [], wids, ["without an appointment"])
                for order, sid in walk_in:
                    details.append(_cite(f"{order['description']} needs no booking.", sid))
                if rule:
                    details.append(_cite(*rule))
            self._finish(step, "done", details)

        # 6. Prior authorization ----------------------------------------------------------------
        if cov and cov.get("covered") and cov.get("prior_auth_required"):
            step = self._start("Check prior authorization")
            out, ids, _ = ctx.call("get_prior_auth_requests", {})
            existing = [(r, s) for r, s in zip(out.get("data") or [], ids)
                        if r["procedure_code"] == cov["procedure_code"] and r["status"] in ("submitted", "approved")]
            if existing:
                r, sid = existing[0]
                self._finish(step, "done", [_cite(
                    f"Prior-authorization request {r['request_id']} is already {r['status']}.", sid)])
                # The coverage step only needed attention because of prior authorization - now handled.
                self._finish(cov_step, "done", cov_step["details"])
            else:
                self.plan_items.append({"type": "submit_prior_auth", "procedure_code": cov["procedure_code"]})
                self._finish(step, "done", [_cite(
                    "No prior-authorization request exists yet, so I will prepare one for the Billing and Insurance "
                    "Desk.", cov_sid, ids[0] if ids and not out.get("ok") else None)])

        # 7. One plan, one approval -------------------------------------------------------------
        step = self._start("Prepare your plan for approval")
        if not self.plan_items:
            self._finish(step, "done", [_cite("There is nothing to book or submit right now.", *self.record_sids)])
            return self._result()
        out, ids, _ = ctx.call("propose_care_plan", {"items": self.plan_items})
        if out.get("ok"):
            self._finish(step, "done", [_cite(
                "Your plan is ready - nothing is booked or submitted until you approve it.", ids[0])])
        else:
            self._finish(step, "warning", [_cite(f"I could not prepare the plan: {ctx.by_id(ids[0])['text']}.",
                                                 ids[0]) if ids else "I could not prepare the plan."])
        return self._result()

    def _result(self) -> dict:
        lines = ["Here is your surgery readiness check:"]
        for s in self.steps:
            lines += [f"- {d}" for d in s["details"]]
        return {"draft": "\n".join(lines), "steps": self.steps, "cards": self.cards}


def run(ctx: RunContext) -> dict:
    return SurgeryReadinessAgent(ctx).run()
