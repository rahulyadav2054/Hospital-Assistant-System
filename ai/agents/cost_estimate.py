"""Cost Estimate & Pre-Approval Agent.

Goal: "How much will my knee replacement cost?"  The numbers come from the deterministic coverage engine; the plan
document is cited for the clauses; the agent prepares the prior-authorization request when it is needed.

  1. identify the procedure     from the question, else the surgery the doctor recommended
  2. your share                 check_coverage (rules engine)       covered %, deductible, estimate, reasons
  3. plan document              RAG over the patient's own plan     coverage clause, annual limit
  4. prior authorization        get_prior_auth_requests             needed and not yet submitted -> plan item
  5. what to prepare            RAG: insurer approval time at billing, what to bring
  6. one approval               propose_care_plan (submit_prior_auth)
"""
from .base import BaseAgent, _cite, _sentence


class CostEstimateAgent(BaseAgent):
    NAME = "cost_estimate"
    TITLE = "Cost Estimate Agent"
    ICON = "💰"

    def run(self) -> dict:
        ctx = self.ctx

        # 1. Procedure ----------------------------------------------------------------------------
        step = self._start("Identify the procedure")
        out, ids, _ = ctx.call("check_coverage", {"procedure_name": self.text})
        details = []
        if not out.get("ok") or out["data"].get("covered") is None:
            pout, pids, _ = ctx.call("get_orders", {"order_type": "procedure", "status": "pending"})
            if pout.get("ok"):
                proc, psid = pout["data"][0], pids[0]
                details.append(_cite(f"Your doctor recommended {proc['description']}, so I estimated that.", psid))
                out, ids, _ = ctx.call("check_coverage", {"procedure_name": proc["linked_procedure"] or
                                                          proc["description"]})
        cov = out.get("data") if out.get("ok") else None
        if not cov or cov.get("covered") is None:
            self._finish(step, "stopped", ["Which procedure would you like a cost estimate for?"])
            return self._result()
        csid = ids[0]
        self.record_sids = [csid]
        details.append(_cite(f"Estimate for {cov['procedure']} (procedure code {cov['procedure_code']}) under your "
                             f"{cov['plan']} plan.", csid))
        self._finish(step, "done", details)

        # 2. Your share -----------------------------------------------------------------------------
        step = self._start("Calculate your share")
        if cov["covered"]:
            details = [_cite(f"{reason}.", csid) for reason in cov["reasons"]]
            self._finish(step, "done", details)
        else:
            self._finish(step, "warning", [_cite(f"{cov['procedure']} is not covered: {cov['reasons'][0]}.", csid)])

        # 3. Plan document --------------------------------------------------------------------------
        step = self._start("Read your plan document")
        doc_id = (cov.get("plan_doc_ref") or "").split(" ")[0]
        sout, sids, _ = ctx.call("search_hospital_docs", {"query": f"{cov['plan']} {cov['procedure']} coverage "
                                                                   f"annual coverage limit deductible",
                                                          "doc_type": "insurance"})
        mine = [(c, s) for c, s in zip(sout.get("data") or [], sids) if c["doc_id"] == doc_id]
        chunks, cids = [c for c, _ in mine], [s for _, s in mine]
        words = ["cosmetic"] if "cosmetic" in cov["procedure"].lower() else cov["procedure"].lower().split()[-2:]
        reasons = " ".join(cov["reasons"])
        if "expired" in reasons or "starts on" in reasons:
            clause = self.doc_sentence(f"{cov['plan']} coverage applies only while the member's policy is active",
                                       "insurance", ["policy is active"])
            clause = clause if clause and doc_id in (ctx.by_id(clause[1]).get("ref") or "") else None
        elif "waiting period" in reasons:
            clause = _sentence(chunks, cids, words + ["waiting period"])
        elif not cov["covered"]:
            clause = _sentence(chunks, cids, words + ["not covered"])
        else:
            clause = _sentence(chunks, cids, words + ["covered at"])
        details = [_cite(*hit) for hit in (clause, _sentence(chunks, cids, ["annual coverage limit"])) if hit]
        if not any("annual coverage limit" in d for d in details):
            hit = self.doc_sentence(f"{cov['plan']} plan overview annual coverage limit", "insurance",
                                    ["annual coverage limit"])
            if hit and doc_id in (ctx.by_id(hit[1]).get("ref") or ""):
                details.append(_cite(*hit))
        self._finish(step, "done", details)

        # 4. Prior authorization --------------------------------------------------------------------
        if cov["covered"] and cov["prior_auth_required"]:
            step = self._start("Check prior authorization")
            rout, rids, _ = ctx.call("get_prior_auth_requests", {})
            existing = [(r, s) for r, s in zip(rout.get("data") or [], rids if rout.get("ok") else [])
                        if r["procedure_code"] == cov["procedure_code"] and r["status"] in ("submitted", "approved")]
            if existing:
                r, s = existing[0]
                self._finish(step, "done", [_cite(f"Prior-authorization request {r['request_id']} is already "
                                                  f"{r['status']}.", s)])
            else:
                self.plan_items.append({"type": "submit_prior_auth", "procedure_code": cov["procedure_code"]})
                self._finish(step, "warning", [_cite("Prior authorization is required and has not been submitted, "
                                                     "so I prepared the request for the Billing and Insurance Desk.",
                                                     csid, rids[0] if rids and not rout.get("ok") else None)])

        # 5. What to prepare --------------------------------------------------------------------------
        step = self._start("Check what to prepare")
        details = []
        hit = self.doc_sentence("insurance patients wait for insurer final approval billing clearance", "procedure",
                                ["insurer's final approval"])
        if hit:
            details.append(_cite(*hit))
        hit = self.doc_sentence("what to bring insurance card patient ID", "policy", ["insurance card"])
        if hit:
            details.append(_cite(*hit))
        self._finish(step, "done", details)

        # 6. One approval -----------------------------------------------------------------------------
        if self.plan_items:
            self.propose("Prepare the pre-approval request",
                         "The prior-authorization request is ready - nothing is submitted until you approve it.")
        return self._result()
