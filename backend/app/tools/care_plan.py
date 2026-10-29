"""Tools behind the agents: diagnostic test slots, prior-authorization requests, and a multi-item care plan
that follows the same two-phase commit as rescheduling (propose -> patient approves).

Plan item types: book_test, submit_prior_auth, book_appointment, reschedule_appointment."""
import json
import re
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import update

from ..config import settings
from ..models import (Appointment, Department, DiagnosticSlot, Doctor, Order, Patient, PendingAction,
                      PriorAuthRequest, Procedure, Slot)
from .common import ActionError, NotFound, fmt_dt
from .eligibility import check_coverage
from .scheduling import _check_changeable

# Which bookable service a test order needs. Tests not listed here (blood tests) are walk-in.
SERVICE_KEYS = {
    "ECG": ["ecg", "electrocardiogram"],
    "Chest X-ray": ["chest x-ray", "x-ray", "xray"],
    "MRI": ["mri", "magnetic resonance"],
}


def resolve_service(text: str | None) -> str | None:
    t = (text or "").lower()
    for service, keys in SERVICE_KEYS.items():
        if any(re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t) for k in keys):
            return service
    return None


def _readable(d: datetime) -> str:
    return d.strftime("%a %d %b, %H:%M")


# ------------------------------------------------------------------ read tools
def get_test_slots(db, patient_id, user_ctx, test_name, from_date=None, limit=5):
    service = resolve_service(test_name)
    if service is None:
        raise NotFound()  # not a bookable test (e.g. blood tests are walk-in)
    start_from = datetime.now()
    if from_date:
        try:
            start_from = max(start_from, datetime.combine(date.fromisoformat(str(from_date)[:10]),
                                                          datetime.min.time()))
        except ValueError:
            raise ValueError("from_date must be YYYY-MM-DD")
    rows = (db.query(DiagnosticSlot)
            .filter(DiagnosticSlot.service == service, DiagnosticSlot.is_booked.is_(False),
                    DiagnosticSlot.start_time >= start_from)
            .order_by(DiagnosticSlot.start_time).limit(max(1, min(int(limit), 15))).all())
    if not rows:
        raise NotFound()
    return [{"slot_id": s.id, "service": s.service, "location": s.location, "start": fmt_dt(s.start_time)}
            for s in rows]


def get_prior_auth_requests(db, patient_id, user_ctx):
    rows = (db.query(PriorAuthRequest).filter(PriorAuthRequest.patient_id == patient_id)
            .order_by(PriorAuthRequest.created_at).all())
    if not rows:
        raise NotFound()
    return [{"request_id": r.id, "procedure_code": r.procedure_code,
             "procedure": db.get(Procedure, r.procedure_code).name, "status": r.status,
             "submitted_date": r.created_at.date().isoformat()} for r in rows]


# ------------------------------------------------------------------ validation shared by propose + confirm
def _check_book_test(db, patient_id, order_id, slot_id, used_slots: set):
    order = db.get(Order, order_id)
    if not order or order.patient_id != patient_id:
        raise NotFound()
    if order.order_type != "pre_op" or order.status != "pending":
        raise ValueError(f"Order {order_id} is not a pending pre-operative test")
    if order.scheduled_at is not None:
        raise ValueError(f"{order.description} is already booked")
    try:
        slot = db.get(DiagnosticSlot, int(slot_id))
    except (TypeError, ValueError):
        raise ValueError("slot_id must be a number")
    if (not slot or slot.is_booked or slot.start_time <= datetime.now() or slot.id in used_slots
            or slot.service != resolve_service(order.description)):
        raise ValueError(f"The slot for {order.description} is no longer available")
    used_slots.add(slot.id)
    return order, slot


def _check_prior_auth(db, patient_id, user_ctx, procedure_code):
    cov = check_coverage(db, patient_id, user_ctx, procedure_code=str(procedure_code))
    if not (cov.get("covered") and cov.get("prior_auth_required")):
        raise ValueError(f"A prior-authorization request is not needed for {cov.get('procedure')}")
    existing = (db.query(PriorAuthRequest)
                .filter(PriorAuthRequest.patient_id == patient_id,
                        PriorAuthRequest.procedure_code == cov["procedure_code"],
                        PriorAuthRequest.status.in_(("submitted", "approved"))).first())
    if existing:
        raise ValueError(f"A prior-authorization request for {cov['procedure']} already exists ({existing.id})")
    return cov


def _doctor_slot(db, doctor_id, slot_id, used_slots: set) -> Slot:
    try:
        slot = db.get(Slot, int(slot_id))
    except (TypeError, ValueError):
        raise ValueError("slot_id must be a number")
    if (not slot or slot.is_booked or slot.doctor_id != doctor_id or slot.start_time <= datetime.now()
            or slot.id in used_slots):
        raise ValueError("That appointment slot is no longer available")
    used_slots.add(slot.id)
    return slot


def _check_clash(db, patient_id, start: datetime, ignore_appointment: str | None = None) -> None:
    clash = (db.query(Appointment).filter(Appointment.patient_id == patient_id, Appointment.status == "scheduled",
                                          Appointment.start_time == start, Appointment.id != (ignore_appointment or ""))
             .first())
    if clash:
        raise ValueError(f"You already have an appointment at {_readable(start)}")


def _check_book_appointment(db, patient_id, doctor_id, slot_id, used_slots: set):
    doc = db.get(Doctor, doctor_id)
    if not doc:
        raise NotFound()
    slot = _doctor_slot(db, doc.id, slot_id, used_slots)
    _check_clash(db, patient_id, slot.start_time)
    return doc, slot


def _check_reschedule(db, patient_id, appointment_id, slot_id, used_slots: set):
    appt = db.get(Appointment, appointment_id)
    if not appt or appt.patient_id != patient_id:
        raise NotFound()  # never reveal another patient's appointment
    _check_changeable(appt)
    slot = _doctor_slot(db, appt.doctor_id, slot_id, used_slots)  # same doctor (Policy POL-APT-002 §2)
    _check_clash(db, patient_id, slot.start_time, ignore_appointment=appt.id)
    return appt, slot


def _validate(db, patient_id, user_ctx, items) -> list[dict]:
    """Check every item and return display labels. Raises NotFound / ValueError."""
    if not isinstance(items, list) or not items:
        raise ValueError("The plan has no items")
    if len(items) > 10:
        raise ValueError("Too many plan items")
    used_slots: set = set()
    labels = []
    for it in items:
        kind = (it or {}).get("type")
        if kind == "book_test":
            order, slot = _check_book_test(db, patient_id, it.get("order_id"), it.get("slot_id"), used_slots)
            labels.append({"type": kind, "label": f"Book {order.description}",
                           "detail": f"{_readable(slot.start_time)} at {slot.location}"})
        elif kind == "submit_prior_auth":
            cov = _check_prior_auth(db, patient_id, user_ctx, it.get("procedure_code"))
            labels.append({"type": kind, "label": f"Submit prior authorization for {cov['procedure']}",
                           "detail": f"{cov['plan']} - sent to the Billing and Insurance Desk"})
        elif kind == "book_appointment":
            doc, slot = _check_book_appointment(db, patient_id, it.get("doctor_id"), it.get("slot_id"), used_slots)
            dept = db.get(Department, doc.department_id)
            labels.append({"type": kind, "label": f"Book {dept.name} with {doc.name}",
                           "detail": f"{_readable(slot.start_time)} at {dept.location}"})
        elif kind == "reschedule_appointment":
            appt, slot = _check_reschedule(db, patient_id, it.get("appointment_id"), it.get("slot_id"), used_slots)
            dept = db.get(Department, appt.department_id)
            labels.append({"type": kind,
                           "label": f"Move {dept.name} ({db.get(Doctor, appt.doctor_id).name})",
                           "detail": f"from {_readable(appt.start_time)} to {_readable(slot.start_time)}"})
        else:
            raise ValueError(f"Unknown plan item type '{kind}'")
    return labels


# ------------------------------------------------------------------ phase 1: propose
def propose_care_plan(db, patient_id, user_ctx, items):
    labels = _validate(db, patient_id, user_ctx, items)
    clean = []
    for it in items:
        if it["type"] == "book_test":
            clean.append({"type": "book_test", "order_id": it["order_id"], "slot_id": int(it["slot_id"])})
        elif it["type"] == "book_appointment":
            clean.append({"type": "book_appointment", "doctor_id": it["doctor_id"], "slot_id": int(it["slot_id"])})
        elif it["type"] == "reschedule_appointment":
            clean.append({"type": "reschedule_appointment", "appointment_id": it["appointment_id"],
                          "slot_id": int(it["slot_id"])})
        else:
            clean.append({"type": "submit_prior_auth", "procedure_code": str(it["procedure_code"])})
    pa = PendingAction(id=f"PA-{secrets.token_hex(4).upper()}", user_id=user_ctx["user_id"],
                       action_type="care_plan", payload_json=json.dumps({"items": clean}), status="pending",
                       created_at=datetime.now(),
                       expires_at=datetime.now() + timedelta(minutes=settings.PENDING_ACTION_MINUTES))
    db.add(pa)
    db.commit()
    shown = [{"index": i, **lab} for i, lab in enumerate(labels)]
    return {"pending_action_id": pa.id, "items": shown,
            "summary": "; ".join(f"{x['label']} ({x['detail']})" for x in shown),
            "expires_at": pa.expires_at.astimezone().isoformat(timespec="seconds")}  # with UTC offset


# ------------------------------------------------------------------ phase 2: confirm (called from confirm_action)
def confirm_care_plan(db, user_ctx, pa: PendingAction, selected=None) -> dict:
    items = json.loads(pa.payload_json)["items"]
    idx = list(range(len(items))) if selected is None else sorted(set(selected))
    if not idx:
        raise ActionError(400, "Select at least one item")
    if any(not isinstance(i, int) or i < 0 or i >= len(items) for i in idx):
        raise ActionError(400, "Invalid item selection")
    patient_id = user_ctx.get("patient_id")
    chosen = [items[i] for i in idx]
    try:
        _validate(db, patient_id, user_ctx, chosen)  # re-check everything: data may have changed since proposal
    except NotFound:
        raise ActionError(404, "No such pending action")
    except ValueError as e:
        raise ActionError(409, f"{e}. Please ask again for an updated plan.")

    def claim(model, slot_id):
        res = db.execute(update(model).where(model.id == slot_id, model.is_booked.is_(False)).values(is_booked=True))
        if res.rowcount != 1:
            db.rollback()  # all-or-nothing
            raise ActionError(409, "A slot was just taken. Please ask again for an updated plan.")
        return db.get(model, slot_id)

    results = []
    for i, it in zip(idx, chosen):
        if it["type"] == "book_appointment":
            slot = claim(Slot, it["slot_id"])
            doc = db.get(Doctor, it["doctor_id"])
            dept = db.get(Department, doc.department_id)
            appt = Appointment(id=f"APT-{secrets.token_hex(3).upper()}", patient_id=patient_id, doctor_id=doc.id,
                               department_id=dept.id, start_time=slot.start_time,
                               end_time=slot.start_time + timedelta(minutes=30), location=dept.location,
                               status="scheduled")
            db.add(appt)
            results.append({"index": i, "type": "book_appointment", "appointment_id": appt.id,
                            "message": f"{dept.name} with {doc.name} booked for {_readable(slot.start_time)}"})
            continue
        if it["type"] == "reschedule_appointment":
            slot = claim(Slot, it["slot_id"])
            appt = db.get(Appointment, it["appointment_id"])
            old = db.query(Slot).filter_by(doctor_id=appt.doctor_id, start_time=appt.start_time).first()
            if old:
                old.is_booked = False
            duration = appt.end_time - appt.start_time
            appt.start_time, appt.end_time = slot.start_time, slot.start_time + duration
            dept = db.get(Department, appt.department_id)
            results.append({"index": i, "type": "reschedule_appointment", "appointment_id": appt.id,
                            "message": f"{dept.name} moved to {_readable(slot.start_time)}"})
            continue
        if it["type"] == "book_test":
            claimed = db.execute(update(DiagnosticSlot)
                                 .where(DiagnosticSlot.id == it["slot_id"], DiagnosticSlot.is_booked.is_(False))
                                 .values(is_booked=True))
            if claimed.rowcount != 1:
                db.rollback()  # all-or-nothing
                raise ActionError(409, "A test slot was just taken. Please ask again for an updated plan.")
            slot = db.get(DiagnosticSlot, it["slot_id"])
            order = db.get(Order, it["order_id"])
            order.scheduled_at = slot.start_time
            order.scheduled_slot_id = slot.id
            results.append({"index": i, "type": "book_test", "order_id": order.id,
                            "message": f"{order.description} booked for {_readable(slot.start_time)} "
                                       f"at {slot.location}"})
        else:
            cov = check_coverage(db, patient_id, user_ctx, procedure_code=it["procedure_code"])
            req = PriorAuthRequest(id=f"PAR-{secrets.token_hex(3).upper()}", patient_id=patient_id,
                                   procedure_code=it["procedure_code"], plan_id=db.get(Patient, patient_id).plan_id,
                                   status="submitted", created_at=datetime.now())
            db.add(req)
            results.append({"index": i, "type": "submit_prior_auth", "request_id": req.id,
                            "message": f"Prior-authorization request {req.id} submitted for {cov['procedure']}"})
    pa.status = "done"
    db.commit()
    return {"status": "done", "results": results, "message": "; ".join(r["message"] for r in results) + "."}
