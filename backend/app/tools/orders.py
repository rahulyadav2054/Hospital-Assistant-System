from ..models import DiagnosticSlot, Doctor, Order
from .common import NotFound, fmt_dt

ORDER_TYPES = {"procedure", "pre_op", "imaging", "lab"}


def get_orders(db, patient_id, user_ctx, order_type=None, status=None):
    q = db.query(Order).filter(Order.patient_id == patient_id)  # ALWAYS scoped
    if order_type:
        if order_type not in ORDER_TYPES:
            raise ValueError(f"order_type must be one of {sorted(ORDER_TYPES)}")
        q = q.filter(Order.order_type == order_type)
    if status:
        q = q.filter(Order.status == status)
    rows = q.order_by(Order.created_at, Order.id).all()
    if not rows:
        raise NotFound()
    return [{"order_id": o.id, "type": o.order_type, "description": o.description, "status": o.status,
             "ordered_by": db.get(Doctor, o.ordered_by).name, "linked_procedure": o.linked_procedure,
             "ordered_date": o.created_at.date().isoformat(),
             "completed_date": o.completed_at.date().isoformat() if o.completed_at else None,
             "scheduled_at": fmt_dt(o.scheduled_at) if o.scheduled_at else None,
             "scheduled_location": (db.get(DiagnosticSlot, o.scheduled_slot_id).location
                                    if o.scheduled_slot_id else None)} for o in rows]
