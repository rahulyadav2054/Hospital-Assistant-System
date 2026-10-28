"""Rebuild the database from data/seed/*.json.

Usage:  python -m backend.app.seed --reset
All dates in the seed files are relative to today, so the demo data never goes stale.
"""
import argparse
import json
from datetime import date, datetime, time, timedelta

from .auth import hash_password
from .config import ROOT
from .db import Base, SessionLocal, engine
from .models import (Appointment, CoverageRule, Department, DiagnosticSlot, Doctor, InsurancePlan, LabResult,
                     Order, Patient, Procedure, Slot, User)

SEED_DIR = ROOT / "data" / "seed"


def _load(name):
    return json.loads((SEED_DIR / name).read_text(encoding="utf-8"))


def _at(day_offset: int, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime.combine(date.today() + timedelta(days=day_offset), time(h, m))


def _flag(value, low, high):
    if value < low:
        return "low"
    if value > high:
        return "high"
    return "normal"


def seed(reset: bool = True) -> None:
    if reset:
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    ref = _load("reference.json")
    ppl = _load("patients.json")
    today = date.today()
    now = datetime.now()

    with SessionLocal() as db:
        for p in ref["insurance_plans"]:
            db.add(InsurancePlan(**p))
        for d in ref["departments"]:
            db.add(Department(**d, keywords=json.dumps(ref["department_keywords"].get(d["id"], []))))
        for d in ref["doctors"]:
            db.add(Doctor(**d))
        for p in ref["procedures"]:
            db.add(Procedure(code=p["code"], name=p["name"], aliases=json.dumps(p["aliases"]),
                             base_cost=p["base_cost"]))
        for r in ref["coverage_rules"]:
            db.add(CoverageRule(**r))
        db.flush()

        for p in ppl["patients"]:
            db.add(Patient(id=p["id"], name=p["name"], dob=date.fromisoformat(p["dob"]), phone=p["phone"],
                           plan_id=p["plan_id"], plan_member_id=p["plan_member_id"],
                           coverage_start=today + timedelta(days=p["coverage_start_offset"]),
                           coverage_end=today + timedelta(days=p["coverage_end_offset"])))
        db.flush()

        for u in ppl["users"]:
            db.add(User(username=u["username"], password_hash=hash_password(u["password"]), role=u["role"],
                        patient_id=u["patient_id"], display_name=u.get("display_name")))

        doctors = {d["id"]: d for d in ref["doctors"]}
        depts = {d["id"]: d for d in ref["departments"]}
        for a in ppl["appointments"]:
            if "hours_from_now" in a:
                # Floor to the half hour so it is always strictly inside the 24h change window.
                start = now + timedelta(hours=a["hours_from_now"])
                start = start.replace(minute=0 if start.minute < 30 else 30, second=0, microsecond=0)
                if start.date() == today:  # seeded just after midnight: keep it "tomorrow" (still < 24h away)
                    start = datetime.combine(today + timedelta(days=1), time(0, 0))
            else:
                start = _at(a["day_offset"], a["time"])
            doc = doctors[a["doctor_id"]]
            dept = depts[doc["department_id"]]
            db.add(Appointment(id=a["id"], patient_id=a["patient_id"], doctor_id=doc["id"],
                               department_id=dept["id"], start_time=start, end_time=start + timedelta(minutes=30),
                               location=f'{dept["location"]}, {a["room"]}', status=a["status"]))

        for lab in ppl["lab_results"]:
            db.add(LabResult(id=lab["id"], patient_id=lab["patient_id"], test_name=lab["test_name"],
                             value=lab["value"], unit=lab["unit"], ref_low=lab["ref_low"], ref_high=lab["ref_high"],
                             flag=_flag(lab["value"], lab["ref_low"], lab["ref_high"]),
                             collected_at=_at(lab["day_offset"], "08:00")))

        for o in ppl["orders"]:
            db.add(Order(id=o["id"], patient_id=o["patient_id"], order_type=o["order_type"],
                         description=o["description"], status=o["status"], ordered_by=o["ordered_by"],
                         linked_procedure=o["linked_procedure"], created_at=_at(o["day_offset"], "11:30"),
                         completed_at=_at(o["completed_offset"], "09:00") if o["completed_offset"] is not None else None))

        sd = ref["slot_days"]
        for doc_id in doctors:
            for offset in range(sd["from"], sd["to"] + 1):
                if (today + timedelta(days=offset)).weekday() == 6:  # no Sunday OPD
                    continue
                for t in ref["slot_times"]:
                    db.add(Slot(doctor_id=doc_id, start_time=_at(offset, t),
                                is_booked=offset == sd["fully_booked_day"]))

        dd = ref["diagnostic_days"]
        for svc in ref["diagnostic_services"]:
            for offset in range(dd["from"], dd["to"] + 1):
                if (today + timedelta(days=offset)).weekday() == 6:
                    continue
                for t in svc["times"]:
                    db.add(DiagnosticSlot(service=svc["service"], location=svc["location"],
                                          start_time=_at(offset, t), is_booked=False))
        db.commit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the hospital database")
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables")
    args = parser.parse_args()
    seed(reset=args.reset)
    print("Database seeded.")
