"""Scheduling workflow: read slots, propose a change (no DB change), confirm/cancel (two-phase commit)."""
import json
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy import update

from ..config import settings
from ..models import Appointment, Department, Doctor, PendingAction, Slot
from .common import ActionError, NotFound, fmt_dt, resolve_department


def _readable(d: datetime) -> str:
    return d.strftime("%b %d, %H:%M")


def get_available_slots(db, patient_id, user_ctx, department=None, doctor_id=None, appointment_id=None,
                        from_date=None, limit=5):
    doctor_ids = None
    if appointment_id:
        appt = db.get(Appointment, appointment_id)
        if not appt or (user_ctx["role"] != "staff" and appt.patient_id != patient_id):
            raise NotFound()
        doctor_ids = [appt.doctor_id]  # reschedules stay with the same doctor (Policy POL-APT-002 §2)
    elif doctor_id:
        if not db.get(Doctor, doctor_id):
            raise NotFound()
        doctor_ids = [doctor_id]
    elif department:
        dept = resolve_department(db, department)
        if dept is None:
            raise ValueError(f"Unknown department '{department}'")
        doctor_ids = [d.id for d in db.query(Doctor).filter_by(department_id=dept.id)]
    else:
        raise ValueError("Provide appointment_id, doctor_id or department")

    start_from = datetime.now()
    if from_date:
        try:
            start_from = max(start_from, datetime.combine(date.fromisoformat(str(from_date)[:10]), datetime.min.time()))
        except ValueError:
            raise ValueError("from_date must be YYYY-MM-DD")
    rows = (db.query(Slot).filter(Slot.doctor_id.in_(doctor_ids), Slot.is_booked.is_(False),
                                  Slot.start_time >= start_from)
            .order_by(Slot.start_time).limit(max(1, min(int(limit), 10))).all())
    if not rows:
        raise NotFound()
    out = []
    for s in rows:
        doc = db.get(Doctor, s.doctor_id)
        out.append({"slot_id": s.id, "doctor": doc.name, "doctor_id": doc.id,
                    "department": db.get(Department, doc.department_id).name, "start": fmt_dt(s.start_time)})
    return out


def _check_changeable(appt: Appointment) -> None:
    if appt.status != "scheduled":
        raise ValueError(f"Appointment {appt.id} is {appt.status} and cannot be changed")
    if appt.start_time - datetime.now() < timedelta(hours=settings.CHANGE_WINDOW_HOURS):
        raise ValueError("Appointments can only be rescheduled up to 24 hours before the appointment time; "
                         "please call the department directly (Policy POL-APT-002 §2)")


def propose_reschedule(db, patient_id, user_ctx, appointment_id, slot_id):
    """Phase 1: validate and store a pending action. Nothing about the appointment changes here."""
    appt = db.get(Appointment, appointment_id)
    if not appt or appt.patient_id != patient_id:
        raise NotFound()  # don't reveal that someone else's appointment exists
    _check_changeable(appt)
    try:
        slot = db.get(Slot, int(slot_id))
    except (TypeError, ValueError):
        raise ValueError("slot_id must be a number")
    if not slot or slot.is_booked or slot.doctor_id != appt.doctor_id or slot.start_time <= datetime.now():
        raise ValueError("That slot is unavailable; please pick another available slot with the same doctor")

    pa = PendingAction(id=f"PA-{secrets.token_hex(4).upper()}", user_id=user_ctx["user_id"],
                       action_type="reschedule",
                       payload_json=json.dumps({"appointment_id": appt.id, "slot_id": slot.id}),
                       status="pending", created_at=datetime.now(),
                       expires_at=datetime.now() + timedelta(minutes=settings.PENDING_ACTION_MINUTES))
    db.add(pa)
    db.commit()
    doc = db.get(Doctor, appt.doctor_id)
    dept = db.get(Department, appt.department_id)
    return {"pending_action_id": pa.id,
            "summary": f"Move {dept.name} ({doc.name}) from {_readable(appt.start_time)} to {_readable(slot.start_time)}",
            "appointment_id": appt.id, "old_start": fmt_dt(appt.start_time), "new_start": fmt_dt(slot.start_time),
            # With the UTC offset: a browser in another timezone (or a UTC container) must not misread it.
            "expires_at": pa.expires_at.astimezone().isoformat(timespec="seconds")}


def _load_pending(db, user_ctx, pending_action_id) -> PendingAction:
    pa = db.get(PendingAction, pending_action_id)
    if not pa or pa.user_id != user_ctx["user_id"] or pa.status != "pending":
        raise ActionError(404, "No such pending action")
    return pa


def confirm_action(db, user_ctx, pending_action_id, selected=None) -> dict:
    """Phase 2: re-validate everything, then commit atomically."""
    pa = _load_pending(db, user_ctx, pending_action_id)
    if pa.expires_at < datetime.now():
        pa.status = "expired"
        db.commit()
        raise ActionError(410, "Confirmation expired, please ask again")
    if pa.action_type == "care_plan":
        from .care_plan import confirm_care_plan  # local import: care_plan imports this module

        return confirm_care_plan(db, user_ctx, pa, selected)

    p = json.loads(pa.payload_json)
    appt = db.get(Appointment, p["appointment_id"])
    if not appt or appt.patient_id != user_ctx.get("patient_id"):
        raise ActionError(404, "No such pending action")
    try:
        _check_changeable(appt)
    except ValueError as e:
        raise ActionError(409, str(e))

    # Claim the slot atomically: only succeeds if it is still free.
    claimed = db.execute(update(Slot).where(Slot.id == p["slot_id"], Slot.is_booked.is_(False))
                         .values(is_booked=True))
    if claimed.rowcount != 1:
        db.rollback()
        raise ActionError(409, "Slot was just taken, please choose another slot")
    new_slot = db.get(Slot, p["slot_id"])

    # Free the slot the appointment used to occupy (if it was a bookable slot).
    old = db.query(Slot).filter_by(doctor_id=appt.doctor_id, start_time=appt.start_time).first()
    if old:
        old.is_booked = False
    duration = appt.end_time - appt.start_time
    appt.start_time = new_slot.start_time
    appt.end_time = new_slot.start_time + duration
    pa.status = "done"
    db.commit()
    dept = db.get(Department, appt.department_id)
    return {"status": "done", "appointment_id": appt.id, "new_start": fmt_dt(appt.start_time),
            "message": f"Your {dept.name} appointment is rescheduled to {_readable(appt.start_time)}."}


def cancel_action(db, user_ctx, pending_action_id) -> dict:
    pa = _load_pending(db, user_ctx, pending_action_id)
    pa.status = "cancelled"
    db.commit()
    return {"status": "cancelled"}
