"""Appointment Booking Agent.

Goal: "I have knee pain, book me a doctor" / "Book a cardiologist next week in the afternoon".

  1. understand the request     find_department (symptom / specialty) + day / time-of-day preferences
  2. check existing visits      get_appointments                         already booked in that department -> stop
  3. choose a doctor            get_doctors (+ past appointments)        named doctor > doctor seen before > first
  4. find a slot                get_available_slots                      matches preferences, no clash with own visits
  5. what to bring              appointment policy (RAG)
  6. one approval               propose_care_plan (book_appointment)

Emergency symptoms never reach this agent: the input guardrail answers them first.
"""
import re

from ..sources import when
from .base import BaseAgent, _cite, fmt_day, matches_time_of_day, parse_day, parse_range, parse_time_of_day


class AppointmentBookingAgent(BaseAgent):
    NAME = "appointment_booking"
    TITLE = "Appointment Booking Agent"
    ICON = "📅"

    def run(self) -> dict:
        ctx, text = self.ctx, self.text
        day = parse_day(text)
        rng = None if day else parse_range(text)
        tod = parse_time_of_day(text)

        # 1. Understand ------------------------------------------------------------------------
        step = self._start("Understand your request")
        out, ids, _ = ctx.call("find_department", {"symptom_or_specialty": text})
        if not out.get("ok"):
            self._finish(step, "stopped", ["Which department or symptom is the appointment for?"])
            return self._result()
        dept, dsid = out["data"][0], ids[0]
        details = [_cite(f"{dept['department']} can help with this: {dept['location']}, phone {dept['phone']}, "
                         f"hours {dept['hours']}.", dsid)]
        pref = []
        if day:
            pref.append(f"on {fmt_day(day)}")
        elif rng:
            pref.append(f"between {fmt_day(rng[0])} and {fmt_day(rng[1])}")
        if tod:
            pref.append(f"in the {tod}")
        if pref:
            nsid = self.note("Your request (as understood)", f"Preferred time: {' '.join(pref)}.")
            details.append(_cite(f"I will look for a slot {' '.join(pref)}.", nsid))
        self._finish(step, "done", details)

        # 2. Existing appointments ----------------------------------------------------------------
        step = self._start("Check your existing appointments")
        aout, aids, _ = ctx.call("get_appointments", {"status": "upcoming", "department": dept["department"]})
        wants_another = bool(re.search(r"\b(another|new|second|additional|extra|earlier)\b", text, re.I))
        if aout.get("ok") and not wants_another:
            a, asid = aout["data"][0], aids[0]
            self._finish(step, "warning", [
                _cite(f"You already have an upcoming {dept['department']} appointment with {a['doctor']} on "
                      f"{when(a['start'])}.", asid),
                "Would you like me to reschedule it instead?"])
            return self._result()
        self._finish(step, "done", [self._empty(
            aids, f"You have no upcoming {dept['department']} appointment, so I will book a new one")
            if not aout.get("ok") else _cite("You asked for another appointment, so I will book a new one.",
                                             aids[0])])

        # 3. Doctor -------------------------------------------------------------------------------
        step = self._start("Choose a doctor")
        dout, dids, _ = ctx.call("get_doctors", {"department": dept["department"]})
        if not dout.get("ok"):
            self._finish(step, "stopped", [self._empty(dids, "No doctors are listed for this department")])
            return self._result()
        doctors = list(zip(dout["data"], dids))
        named = next(((d, s) for d, s in doctors
                      if d["name"].split()[-1].lower() in text.lower()), None)
        pout, pids, _ = ctx.call("get_appointments", {"status": "past", "department": dept["department"]})
        seen = None
        if pout.get("ok"):
            seen_id = pout["data"][-1]["doctor_id"]
            seen = next(((d, s) for d, s in doctors if d["doctor_id"] == seen_id), None)
        if named:
            doc, dsid2 = named
            reason = _cite(f"You asked for {doc['name']} ({doc['specialty']}).", dsid2)
        elif seen:
            doc, dsid2 = seen
            reason = _cite(f"You saw {doc['name']} before, so I kept the same doctor for continuity of care.",
                           dsid2, pids[-1])
        else:
            doc, dsid2 = doctors[0]
            reason = _cite(f"{doc['name']} ({doc['specialty']}) is available in {doc['department']}.", dsid2)
        self._finish(step, "done", [reason])

        # 4. Slot ---------------------------------------------------------------------------------
        step = self._start("Find a slot that fits")
        start = day or (rng[0] if rng else None)
        args = {"doctor_id": doc["doctor_id"], "limit": 10}
        if start:
            args["from_date"] = start.isoformat()
        sout, sids, _ = ctx.call("get_available_slots", args)
        if not sout.get("ok"):
            self._finish(step, "stopped", [self._empty(sids, f"{doc['name']} has no free slots right now")])
            return self._result()
        mine, _, _ = ctx.call("get_appointments", {"status": "upcoming"})
        busy = {a["start"] for a in (mine.get("data") or [])}
        slots = [(s, i) for s, i in zip(sout["data"], sids) if s["start"] not in busy]

        def fits(s):
            d = s["start"][:10]
            in_day = (day is None or d == day.isoformat()) and (
                rng is None or rng[0].isoformat() <= d <= rng[1].isoformat())
            return in_day and matches_time_of_day(s["start"], tod)

        best = [(s, i) for s, i in slots if fits(s)]
        if not slots:
            self._finish(step, "stopped", [_cite("All the free slots clash with your other appointments.",
                                                 *sids[:3])])
            return self._result()
        slot, ssid = (best or slots)[0]
        details = [_cite(f"{doc['name']} is free on {when(slot['start'])}.", ssid)]
        if pref and not best:
            details.append(_cite("No slot matched your preference exactly, so I picked the closest one.", ssid))
        self._finish(step, "done" if best or not pref else "warning", details)

        # 5. What to bring ------------------------------------------------------------------------
        step = self._start("Check what to bring")
        hit = self.doc_sentence("what to bring to every appointment patient ID insurance card", "policy",
                                ["Bring your patient ID"])
        self._finish(step, "done", [_cite(*hit)] if hit else [])

        # 6. One approval -------------------------------------------------------------------------
        self.plan_items.append({"type": "book_appointment", "doctor_id": doc["doctor_id"], "slot_id": slot["slot_id"]})
        self.propose("Prepare your booking for approval",
                     "Your booking is ready - nothing is booked until you approve it.")
        return self._result()
