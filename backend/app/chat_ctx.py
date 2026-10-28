from .db import db_session
from .models import InsurancePlan, Patient, User


def build_user_ctx(db, user: dict) -> dict:
    """Identity from the token, plus display info from the DB. Never from the request body."""
    ctx = dict(user)
    u = db.get(User, user["user_id"])
    ctx["name"] = u.display_name if u else None
    if user.get("patient_id"):
        p = db.get(Patient, user["patient_id"])
        ctx["name"] = p.name
        plan = db.get(InsurancePlan, p.plan_id)
        ctx["plan"] = plan.name if plan else None
    return ctx


def ctx_for(username: str) -> dict:
    """User context for a username - for evaluation scripts and tests (bypasses login)."""
    with db_session() as db:
        u = db.query(User).filter_by(username=username).one()
        return build_user_ctx(db, {"user_id": u.id, "role": u.role, "patient_id": u.patient_id})
