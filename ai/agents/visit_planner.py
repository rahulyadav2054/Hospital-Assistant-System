"""Visit Planner Agent.

Goal: "Plan my visit tomorrow" / "I'm coming to the hospital on Friday".

  1. collect visits          get_appointments + booked tests (get_orders)   the day asked for, or the next visit day
  2. build a timeline        sorted by time, with where to go               -> timeline card
  3. preparation             RAG: what to bring, MRI metal rule, fasting tests, walk-in lab hours
  4. arrival rules           RAG: late-arrival policy
Read-only: it never changes anything, so there is nothing to approve.
"""
from datetime import date

from ..sources import when
from .base import BaseAgent, _cite, fmt_day, parse_day, test_key


class VisitPlannerAgent(BaseAgent):
    NAME = "visit_planner"
    TITLE = "Visit Planner Agent"
    ICON = "🗺️"

    def run(self) -> dict:
        ctx = self.ctx
        day = parse_day(self.text)

        # 1. Collect ------------------------------------------------------------------------------
        step = self._start("Collect your visits")
        aout, aids, _ = ctx.call("get_appointments", {"status": "upcoming"})
        oout, oids, _ = ctx.call("get_orders", {"status": "pending"})
        visits = []
        for a, sid in zip(aout.get("data") or [], aids if aout.get("ok") else []):
            visits.append({"start": a["start"], "kind": "appointment", "title": f"{a['department']} with {a['doctor']}",
                           "location": a.get("location") or "", "sid": sid})
        for o, sid in zip(oout.get("data") or [], oids if oout.get("ok") else []):
            if o.get("scheduled_at"):
                visits.append({"start": o["scheduled_at"], "kind": "test", "title": o["description"],
                               "location": o.get("scheduled_location") or "", "sid": sid})
        evidence = [v["sid"] for v in visits] or (aids[:1] + oids[:1])
        if day is None and visits:
            day = min(date.fromisoformat(v["start"][:10]) for v in visits)
        if day is None:
            self._finish(step, "stopped", [_cite("You have no upcoming appointments or booked tests.", *evidence)])
            return self._result()
        nsid = self.note("Your request (as understood)", f"Plan the hospital visit on {fmt_day(day)}.")
        todays = sorted([v for v in visits if v["start"][:10] == day.isoformat()], key=lambda v: v["start"])
        if not todays:
            self._finish(step, "stopped", [_cite(f"You have no appointments or booked tests on {fmt_day(day)}.",
                                                 nsid, *evidence)])
            return self._result()
        self.record_sids = [v["sid"] for v in todays]
        self._finish(step, "done", [_cite(f"You have visits booked on {fmt_day(day)}.", nsid, *self.record_sids)])

        # 2. Timeline -----------------------------------------------------------------------------
        step = self._start("Build your timeline")
        details = []
        for v in todays:
            where = f" at {v['location']}" if v["location"] else ""
            details.append(_cite(f"{v['title']}: {when(v['start'])}{where}.", v["sid"]))
        self.cards.append({"type": "visit_timeline", "data": {
            "date": day.isoformat(),
            "items": [{"time": v["start"][11:16], "title": v["title"], "location": v["location"], "kind": v["kind"]}
                      for v in todays]}})
        self._finish(step, "done", details)

        # 3. Preparation --------------------------------------------------------------------------
        step = self._start("Check how to prepare")
        details = []
        if any(v["kind"] == "appointment" for v in todays):
            hit = self.doc_sentence("what to bring to every appointment", "policy", ["Bring your patient ID"])
            if hit:
                details.append(_cite(*hit))
        keys = {test_key(v["title"]) for v in todays if v["kind"] == "test"}
        if "mri" in keys:
            hit = self.doc_sentence("MRI preparation remove metal objects", "procedure", ["Remove all metal"])
            if hit:
                details.append(_cite(*hit))
        walk_in = [(o, s) for o, s in zip(oout.get("data") or [], oids if oout.get("ok") else [])
                   if o["type"] in ("pre_op", "lab") and not o.get("scheduled_at")
                   and test_key(o["description"]) not in ("ecg", "xray", "mri")]
        if walk_in:
            hit = self.doc_sentence("laboratory opening hours blood tests", "procedure", ["open from"])
            names = ", ".join(o["description"] for o, _ in walk_in)
            details.append(_cite(f"While you are here, you can also do your pending blood test(s): {names}.",
                                 *[s for _, s in walk_in]))
            if hit:
                details.append(_cite(*hit))
            if any("glucose" in o["description"].lower() or "lipid" in o["description"].lower() for o, _ in walk_in):
                fast = self.doc_sentence("fasting tests hours of fasting", "procedure", ["fasting"])
                if fast:
                    details.append(_cite(*fast))
        self._finish(step, "done", details or [_cite("No special preparation is needed for these visits.",
                                                     *self.record_sids)])

        # 4. Arrival -----------------------------------------------------------------------------
        step = self._start("Check arrival rules")
        late = self.doc_sentence("late arrival more than 15 minutes late", "policy", ["minutes late"])
        self._finish(step, "done", [_cite(*late)] if late else [])
        return self._result()
