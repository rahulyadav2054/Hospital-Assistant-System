from datetime import datetime

from ..models import Appointment, Department, Doctor
from .common import NotFound, fmt_dt, resolve_department


def appointment_dict(db, a: Appointment, include_patient: bool = True) -> dict:
    doc = db.get(Doctor, a.doctor_id)
    dept = db.get(Department, a.department_id)
    d = {"appointment_id": a.id, "department": dept.name, "doctor": doc.name, "doctor_id": doc.id,
         "start": fmt_dt(a.start_time), "end": fmt_dt(a.end_time), "location": a.location, "status": a.status}
    if not include_patient:
        d.pop("location")
    return d


def get_appointments(db, patient_id, user_ctx, status=None, department=None):
    q = db.query(Appointment)
    if user_ctx["role"] == "staff":
        # Staff see the schedule (who is booked when) but not patient identities through this tool.
        q = q.filter(Appointment.status == "scheduled", Appointment.start_time >= datetime.now())
    else:
        q = q.filter(Appointment.patient_id == patient_id)  # ALWAYS scoped to the token's patient
        now = datetime.now()
        if status == "upcoming":
            q = q.filter(Appointment.status == "scheduled", Appointment.start_time >= now)
        elif status == "past":
            q = q.filter((Appointment.start_time < now) | (Appointment.status == "completed"))
    if department:
        dept = resolve_department(db, department)
        if dept is None:
            raise ValueError(f"Unknown department '{department}'")
        q = q.filter(Appointment.department_id == dept.id)
    rows = q.order_by(Appointment.start_time).all()
    if not rows:
        raise NotFound()
    staff = user_ctx["role"] == "staff"
    return [appointment_dict(db, a, include_patient=not staff) for a in rows]
