from fastapi import APIRouter, Depends

from ..auth import get_current_user, public_user
from ..db import get_db
from ..models import InsurancePlan, Patient, User
from ..tools.registry import execute_tool

router = APIRouter(prefix="/me", tags=["me"])


@router.get("/profile")
def profile(user=Depends(get_current_user), db=Depends(get_db)):
    out = public_user(db, db.get(User, user["user_id"]))
    if user.get("patient_id"):
        p = db.get(Patient, user["patient_id"])
        plan = db.get(InsurancePlan, p.plan_id)
        out["plan"] = {"name": plan.name, "member_id": p.plan_member_id,
                       "coverage_end": p.coverage_end.isoformat()}
    return out


@router.get("/appointments")
def my_appointments(user=Depends(get_current_user)):
    if user["role"] != "patient":
        return []
    out = execute_tool("get_appointments", {"status": "upcoming"}, user)
    return out["data"] if out["ok"] else []


@router.get("/pending-tests")
def my_pending_tests(user=Depends(get_current_user)):
    if user["role"] != "patient":
        return []
    out = execute_tool("get_orders", {"status": "pending"}, user)
    if not out["ok"]:
        return []
    return [o for o in out["data"] if o["type"] in ("pre_op", "lab", "imaging")]
