from ..models import LabResult
from .common import NotFound, fmt_num, normalize_test


def get_lab_results(db, patient_id, user_ctx, test_name=None, latest_only=False):
    q = db.query(LabResult).filter(LabResult.patient_id == patient_id)  # ALWAYS scoped
    if test_name:
        canonical = normalize_test(test_name) or test_name.strip()
        q = q.filter(LabResult.test_name.ilike(f"%{canonical}%"))
    rows = q.order_by(LabResult.collected_at.desc(), LabResult.test_name).all()
    if latest_only:
        # Keep the most recent result of each distinct test (rows are newest first).
        seen, latest = set(), []
        for r in rows:
            if r.test_name not in seen:
                seen.add(r.test_name)
                latest.append(r)
        rows = latest
    if not rows:
        raise NotFound()
    return [{"lab_id": r.id, "test": r.test_name, "value": r.value, "unit": r.unit,
             "ref_range": f"{fmt_num(r.ref_low)}-{fmt_num(r.ref_high)}", "flag": r.flag,
             "date": r.collected_at.date().isoformat()} for r in rows]
