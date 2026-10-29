"""Tool executor: the security boundary between the LLM and patient data.

- Only registered tools can run.
- The caller's role must be allowed for the tool.
- patient_id is injected from the verified token; anything the LLM passes for identity is dropped.
- Every call is audited.
"""
from ..audit import audit
from ..db import db_session
from . import appointments, care_plan, directory, eligibility, labs, orders, scheduling
from .common import NotFound

REGISTRY = {
    "get_appointments": (appointments.get_appointments, {"patient", "staff"}),
    "get_lab_results": (labs.get_lab_results, {"patient"}),
    "get_orders": (orders.get_orders, {"patient"}),
    "check_coverage": (eligibility.check_coverage, {"patient"}),
    "get_available_slots": (scheduling.get_available_slots, {"patient", "staff"}),
    "propose_reschedule": (scheduling.propose_reschedule, {"patient"}),
    "find_department": (directory.find_department, {"patient", "staff"}),
    # Surgery Readiness Agent
    "get_test_slots": (care_plan.get_test_slots, {"patient", "staff"}),
    "get_prior_auth_requests": (care_plan.get_prior_auth_requests, {"patient"}),
    "propose_care_plan": (care_plan.propose_care_plan, {"patient"}),
    # Other agents
    "get_doctors": (directory.get_doctors, {"patient", "staff"}),
    "get_policy_status": (eligibility.get_policy_status, {"patient"}),
}

_RESERVED = {"patient_id", "user_ctx", "db", "user_id", "role"}


def execute_tool(name: str, args: dict | None, user_ctx: dict) -> dict:
    if name not in REGISTRY:
        return {"ok": False, "error": "unknown_tool"}
    fn, roles = REGISTRY[name]
    if user_ctx.get("role") not in roles:
        audit(user_ctx, tool=name, args=args, outcome="forbidden")
        return {"ok": False, "error": "forbidden"}
    if user_ctx.get("role") == "patient" and not user_ctx.get("patient_id"):
        return {"ok": False, "error": "forbidden"}
    args = {k: v for k, v in (args or {}).items() if k not in _RESERVED}
    try:
        with db_session() as db:
            data = fn(db, patient_id=user_ctx.get("patient_id"), user_ctx=user_ctx, **args)
        audit(user_ctx, tool=name, args=args, outcome="ok")
        return {"ok": True, "data": data}
    except NotFound:
        audit(user_ctx, tool=name, args=args, outcome="not_found")
        return {"ok": False, "error": "not_found"}
    except (TypeError, ValueError) as e:
        audit(user_ctx, tool=name, args=args, outcome="invalid")
        return {"ok": False, "error": f"invalid: {e}"}
