"""Smart Rescheduling Agent.

Goal: "I'm travelling next week, move my appointments" / "Move all my appointments to afternoons".
Plans across several appointments at once and asks for ONE approval.

  1. understand constraints     unavailable dates and/or preferred time of day (shown as a citable note)
  2. affected appointments      get_appointments                in the blocked dates / wrong time of day
                                inside the 24-hour window -> cannot move here (policy)
  3. new slots                  get_available_slots (same doctor) outside the blocked dates, preferred time,
                                no clash, and same day as another moved visit when possible (one trip)
  4. one approval               propose_care_plan (reschedule_appointment x N)
"""
from datetime import datetime, timedelta

from ..sources import when
from .base import BaseAgent, _cite, fmt_day, matches_time_of_day, parse_range, parse_time_of_day


class SmartReschedulingAgent(BaseAgent):
    NAME = "smart_reschedule"
    TITLE = "Smart Rescheduling Agent"
    ICON = "🔁"

    def run(self) -> dict:
        ctx = self.ctx
        rng = parse_range(self.text)
        tod = parse_time_of_day(self.text)

        # 1. Constraints ----------------------------------------------------------------------------
        step = self._start("Understand your constraints")
        if not rng and not tod:
            self._finish(step, "stopped", ["When are you unavailable, or which time of day do you prefer?"])
            return self._result()
        parts = []
        if rng:
            parts.append(f"Unavailable from {fmt_day(rng[0])} to {fmt_day(rng[1])}.")
        if tod:
            parts.append(f"Preferred time: {tod}s.")
        nsid = self.note("Your request (as understood)", " ".join(parts))
        self._finish(step, "done", [_cite(p, nsid) for p in parts])

        # 2. Affected appointments ------------------------------------------------------------------
        step = self._start("Find affected appointments")
        out, ids, _ = ctx.call("get_appointments", {"status": "upcoming"})
        appts = list(zip(out.get("data") or [], ids if out.get("ok") else []))
        if rng:
            affected = [(a, s) for a, s in appts if rng[0].isoformat() <= a["start"][:10] <= rng[1].isoformat()]
        else:
            affected = [(a, s) for a, s in appts if not matches_time_of_day(a["start"], tod)]
        too_soon = [(a, s) for a, s in affected
                    if datetime.fromisoformat(a["start"]) - datetime.now() < timedelta(hours=24)]
        movable = [(a, s) for a, s in affected if (a, s) not in too_soon]
        details = [_cite(f"{a['department']} with {a['doctor']} on {when(a['start'])} needs to move.", s)
                   for a, s in movable]
        if too_soon:
            rule = self.doc_sentence("rescheduling cancellation within 24 hours call the department", "policy",
                                     ["24 hours"])
            for a, s in too_soon:
                details.append(_cite(f"{a['department']} on {when(a['start'])} is within 24 hours, so please call "
                                     f"the department to change it.", s, rule[1] if rule else None))
        if not affected:
            self._finish(step, "done", [_cite("None of your upcoming appointments are affected.", *(ids or []))])
            return self._result()
        self._finish(step, "warning" if too_soon else "done", details)
        if not movable:
            return self._result()

        # 3. New slots -------------------------------------------------------------------------------
        step = self._start("Find new slots")
        details = []
        taken = {a["start"] for a, _ in appts}
        chosen_days: set[str] = set()
        after = (rng[1] + timedelta(days=1)).isoformat() if rng else None
        for a, asid in sorted(movable, key=lambda x: x[0]["start"]):
            args = {"appointment_id": a["appointment_id"], "limit": 10}
            if after:
                args["from_date"] = after
            sout, sids, _ = ctx.call("get_available_slots", args)
            slots = [(s, i) for s, i in zip(sout.get("data") or [], sids if sout.get("ok") else [])
                     if s["start"] not in taken and matches_time_of_day(s["start"], tod)
                     and not (rng and rng[0].isoformat() <= s["start"][:10] <= rng[1].isoformat())]
            if not slots:
                details.append(_cite(f"I found no suitable free slot for {a['department']}; please ask again later.",
                                     asid))
                continue
            same_trip = [(s, i) for s, i in slots if s["start"][:10] in chosen_days]
            slot, ssid = (same_trip or slots)[0]
            taken.add(slot["start"])
            chosen_days.add(slot["start"][:10])
            self.plan_items.append({"type": "reschedule_appointment", "appointment_id": a["appointment_id"],
                                    "slot_id": slot["slot_id"]})
            details.append(_cite(f"{a['department']}: move to {when(slot['start'])}"
                                 f"{' (same day as another visit)' if same_trip else ''}.", asid, ssid))
        self._finish(step, "done" if self.plan_items else "warning", details)

        # 4. One approval ----------------------------------------------------------------------------
        self.record_sids = [s for _, s in movable]
        self.propose("Prepare the changes for approval",
                     "Your changes are ready - nothing moves until you approve them.")
        return self._result()
