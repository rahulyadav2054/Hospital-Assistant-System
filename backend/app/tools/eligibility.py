"""Deterministic insurance eligibility engine.

Same input -> same output, and every decision carries its reasons and the rule that produced it.
The LLM never decides coverage; it only reports what this function returns.
"""
import json
import re
from datetime import date

from ..models import CoverageRule, InsurancePlan, Patient, Procedure


def resolve_procedure(db, text: str | None) -> Procedure | None:
    """Accepts a CPT-style code, a name/alias, or free text that contains an alias."""
    if not text:
        return None
    t = text.strip().lower()
    procs = db.query(Procedure).all()
    for p in procs:
        if t == p.code or t == p.name.lower():
            return p
    candidates = []
    for p in procs:
        for alias in json.loads(p.aliases) + [p.name.lower()]:
            if re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", t):
                candidates.append((len(alias), p))
    if not candidates:
        return None
    return max(candidates, key=lambda c: c[0])[1]  # most specific alias wins


def decision(covered, reasons, plan, proc, rule=None, est_patient_cost=None):
    return {
        "covered": covered,
        "procedure": proc.name,
        "procedure_code": proc.code,
        "plan": plan.name,
        "coverage_pct": rule.coverage_pct if (rule and covered) else 0,
        "prior_auth_required": bool(rule and covered and rule.prior_auth_required),
        "est_patient_cost": est_patient_cost,
        "deductible": plan.deductible,
        "currency": "INR",
        "reasons": reasons,
        "rule_id": rule.id if rule else None,
        "plan_doc_ref": f"{plan.doc_ref} {rule.section}" if rule else plan.doc_ref,
    }


def get_policy_status(db, patient_id, user_ctx):
    """The patient's own insurance policy: active / expired / not started, and days left."""
    p = db.get(Patient, patient_id)
    plan = db.get(InsurancePlan, p.plan_id)
    today = date.today()
    status = "active" if p.coverage_start <= today <= p.coverage_end else (
        "expired" if today > p.coverage_end else "not started")
    return {"plan": plan.name, "member_id": p.plan_member_id, "status": status,
            "coverage_start": p.coverage_start.isoformat(), "coverage_end": p.coverage_end.isoformat(),
            "days_left": (p.coverage_end - today).days, "plan_doc_ref": plan.doc_ref}


def check_coverage(db, patient_id, user_ctx, procedure_name=None, procedure_code=None):
    patient = db.get(Patient, patient_id)
    plan = db.get(InsurancePlan, patient.plan_id)
    proc = resolve_procedure(db, procedure_code or procedure_name)
    if proc is None:
        return {"covered": None, "procedure": procedure_name or procedure_code, "plan": plan.name,
                "reasons": ["The procedure was not recognised. Please contact the Billing and Insurance Desk "
                            "(ext. 1200) with the procedure name or code."],
                "rule_id": None, "plan_doc_ref": plan.doc_ref, "coverage_pct": 0, "prior_auth_required": False,
                "est_patient_cost": None, "deductible": plan.deductible, "currency": "INR"}

    today = date.today()
    if today > patient.coverage_end:
        return decision(False, [f"Your {plan.name} policy expired on {patient.coverage_end.isoformat()}"], plan, proc)
    if today < patient.coverage_start:
        return decision(False, [f"Your {plan.name} policy starts on {patient.coverage_start.isoformat()}"], plan, proc)

    rule = db.query(CoverageRule).filter_by(plan_id=plan.id, procedure_code=proc.code).first()
    if rule is None:
        return decision(False, [f"{proc.name} is not listed in the {plan.name} plan"], plan, proc)
    if not rule.covered:
        return decision(False, [rule.exclusion_note or f"{proc.name} is not covered under {plan.name}"],
                        plan, proc, rule)

    days_enrolled = (today - patient.coverage_start).days
    if days_enrolled < rule.waiting_period_days:
        left = rule.waiting_period_days - days_enrolled
        return decision(False, [f"{proc.name} has a waiting period of {rule.waiting_period_days} days under "
                                f"{plan.name}; {left} days remain"], plan, proc, rule)

    reasons = [f"{proc.name} is covered at {rule.coverage_pct}% under {plan.name}"]
    if rule.prior_auth_required:
        reasons.append("Prior authorization is required before the procedure")
    est = int(round(proc.base_cost * (100 - rule.coverage_pct) / 100 + plan.deductible))
    reasons.append(f"Estimated patient cost is INR {est:,} (your share of the approved cost of INR "
                   f"{proc.base_cost:,} plus the INR {plan.deductible:,} deductible)")
    return decision(True, reasons, plan, proc, rule, est_patient_cost=est)
