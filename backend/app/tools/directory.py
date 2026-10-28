from .common import NotFound, resolve_departments


def find_department(db, patient_id, user_ctx, symptom_or_specialty):
    hits = resolve_departments(db, symptom_or_specialty)
    if not hits:
        raise NotFound()
    return [{"department": d.name, "location": d.location, "phone": d.phone, "hours": d.hours} for d in hits]
