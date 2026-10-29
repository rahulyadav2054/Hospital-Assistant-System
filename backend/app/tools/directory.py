from ..models import Department, Doctor
from .common import NotFound, resolve_department, resolve_departments


def get_doctors(db, patient_id, user_ctx, department=None):
    q = db.query(Doctor)
    if department:
        dept = resolve_department(db, department)
        if dept is None:
            raise ValueError(f"Unknown department '{department}'")
        q = q.filter(Doctor.department_id == dept.id)
    rows = q.order_by(Doctor.id).all()
    if not rows:
        raise NotFound()
    return [{"doctor_id": d.id, "name": d.name, "specialty": d.specialty,
             "department": db.get(Department, d.department_id).name} for d in rows]


def find_department(db, patient_id, user_ctx, symptom_or_specialty):
    hits = resolve_departments(db, symptom_or_specialty)
    if not hits:
        raise NotFound()
    return [{"department": d.name, "location": d.location, "phone": d.phone, "hours": d.hours} for d in hits]
