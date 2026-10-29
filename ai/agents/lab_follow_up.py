"""Lab Follow-up Agent.

Goal: "My sugar report is high, what should I do next?"  It never interprets a result medically - it finds the
right follow-up and books it.

  1. read results              get_lab_results (latest)          which values are outside their reference range
  2. no interpretation         lab guide (RAG): only your doctor can interpret
  3. right department          find_department(test name)
  4. existing follow-up?       get_appointments in that department -> take the report there, nothing to book
  5. repeat-test orders        pending orders for that test -> walk-in (blood) or book a slot
  6. book a follow-up          doctor seen before or first doctor, earliest slot -> one approval
"""
import re

from ..offline import LAB_WORDS
from ..sources import when
from .base import BOOKABLE_TESTS, BaseAgent, _cite, test_key


class LabFollowUpAgent(BaseAgent):
    NAME = "lab_follow_up"
    TITLE = "Lab Follow-up Agent"
    ICON = "🧪"

    def run(self) -> dict:
        ctx = self.ctx

        # 1. Results ------------------------------------------------------------------------------
        step = self._start("Read your latest results")
        args = {"latest_only": True}
        m = LAB_WORDS.search(self.text)
        if m:
            args["test_name"] = m.group(0)
        out, ids, _ = ctx.call("get_lab_results", args)
        if not out.get("ok"):
            self._finish(step, "stopped", [self._empty(ids, "I couldn't find matching lab results in your record")])
            return self._result()
        results = list(zip(out["data"], ids))
        flagged = [(r, s) for r, s in results if r["flag"] != "normal"]
        if not flagged:
            self._finish(step, "done", [_cite("Your latest results are all within their reference ranges, so no "
                                              "follow-up is needed for them.", *[s for _, s in results])])
            return self._result()
        self._finish(step, "warning", [
            _cite(f"{r['test']} was {r['value']:g} {r['unit']} on {r['date']}, outside the reference range "
                  f"{r['ref_range']} {r['unit']} (marked {r['flag']}).", s) for r, s in flagged])

        # 2. No interpretation ----------------------------------------------------------------------
        step = self._start("Keep it safe: no interpretation")
        hit = self.doc_sentence("reference ranges only your doctor can interpret results", "procedure",
                                ["Only your doctor"])
        self._finish(step, "done", [_cite(*hit)] if hit else [])

        # 3. Department -----------------------------------------------------------------------------
        step = self._start("Find the right department")
        test = flagged[0][0]["test"]
        dout, dids, _ = ctx.call("find_department", {"symptom_or_specialty": test})
        if not dout.get("ok"):
            dout, dids, _ = ctx.call("find_department", {"symptom_or_specialty": "general medicine"})
        dept, dsid = dout["data"][0], dids[0]
        self._finish(step, "done", [_cite(f"{dept['department']} handles follow-up of this result: "
                                          f"{dept['location']}, phone {dept['phone']}.", dsid)])

        # 4. Existing follow-up ----------------------------------------------------------------------
        step = self._start("Check for an existing follow-up")
        aout, aids, _ = ctx.call("get_appointments", {"status": "upcoming", "department": dept["department"]})
        has_follow_up = aout.get("ok")
        if has_follow_up:
            a, asid = aout["data"][0], aids[0]
            self._finish(step, "done", [_cite(f"You already have {a['department']} with {a['doctor']} on "
                                              f"{when(a['start'])} - take this report to that visit.", asid)])
        else:
            self._finish(step, "warning", [self._empty(
                aids, f"You have no upcoming {dept['department']} appointment to review this result")])

        # 5. Repeat-test orders -----------------------------------------------------------------------
        keys = {test_key(r["test"]) for r, _ in flagged}
        oout, oids, _ = ctx.call("get_orders", {"status": "pending"})
        repeats = [(o, s) for o, s in zip(oout.get("data") or [], oids if oout.get("ok") else [])
                   if o["type"] in ("lab", "pre_op", "imaging") and test_key(o["description"]) in keys]
        if repeats:
            step = self._start("Check repeat-test orders")
            details = []
            for o, s in repeats:
                if o.get("scheduled_at"):
                    details.append(_cite(f"{o['description']} is booked for {when(o['scheduled_at'])}.", s))
                elif test_key(o["description"]) in BOOKABLE_TESTS:
                    sout, sids, _ = ctx.call("get_test_slots", {"test_name": o["description"]})
                    if sout.get("ok"):
                        slot, ssid = sout["data"][0], sids[0]
                        self.plan_items.append({"type": "book_test", "order_id": o["order_id"],
                                                "slot_id": slot["slot_id"]})
                        details.append(_cite(f"{o['description']} is ordered; the earliest slot is "
                                             f"{when(slot['start'])}.", s, ssid))
                else:
                    details.append(_cite(f"{o['description']} is ordered and still pending.", s))
                    hours = self.doc_sentence("laboratory opening hours", "procedure", ["open from"])
                    if hours:
                        details.append(_cite(re.sub(r"\.$", "", hours[0]) + " - no booking is needed.", hours[1]))
            self._finish(step, "done", details)

        # 6. Book a follow-up ------------------------------------------------------------------------
        if not has_follow_up:
            step = self._start("Choose a doctor and slot")
            dout, docids, _ = ctx.call("get_doctors", {"department": dept["department"]})
            if dout.get("ok"):
                doctors = list(zip(dout["data"], docids))
                pout, pids, _ = ctx.call("get_appointments", {"status": "past", "department": dept["department"]})
                seen_id = pout["data"][-1]["doctor_id"] if pout.get("ok") else None
                doc, docsid = next(((d, s) for d, s in doctors if d["doctor_id"] == seen_id), doctors[0])
                sout, sids, _ = ctx.call("get_available_slots", {"doctor_id": doc["doctor_id"]})
                if sout.get("ok"):
                    slot, ssid = sout["data"][0], sids[0]
                    self.plan_items.append({"type": "book_appointment", "doctor_id": doc["doctor_id"],
                                            "slot_id": slot["slot_id"]})
                    self._finish(step, "done", [_cite(f"{doc['name']} ({doc['specialty']}) is free on "
                                                      f"{when(slot['start'])}.", docsid, ssid)])
                else:
                    self._finish(step, "warning", [self._empty(sids, f"{doc['name']} has no free slots right now")])
            else:
                self._finish(step, "warning", [self._empty(docids, "No doctors are listed for this department")])

        self.record_sids = [s for _, s in flagged]
        self.propose("Prepare your follow-up for approval")
        return self._result()
