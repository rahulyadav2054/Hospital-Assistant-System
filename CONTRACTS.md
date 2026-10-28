# Shared contracts (Day 0)

These are the agreements between the AI layer (Member 1), the backend (Member 2) and the UI (Member 3).
**Never change a field silently** - announce it and update this file.

## 1. `POST /chat`

```jsonc
// request  (Authorization: Bearer <jwt>)
{ "message": "What is my latest blood sugar?", "session_id": "s-123" }   // session_id: [A-Za-z0-9_-:.]{1,100}

// response
{
  "answer": "- Fasting Glucose: 112 mg/dL on 2026-10-20 (reference range 70-99 mg/dL, marked high) [S1]",
  "status": "ok",            // ok | not_found | emergency | unauthorized | error
  "intent": "lab_result",    // policy | procedure | personal_data | eligibility | lab_result | multi_step | action | agent | out_of_scope
  "citations": [
    { "id": "S1", "source_type": "record",   // record | document
      "title": "Lab result: Fasting Glucose", "section": null, "ref": "LAB-5531", "date": "2026-10-20" }
  ],
  "tool_calls": [ { "name": "get_lab_results", "ok": true } ],
  "cards": [ { "type": "lab_result", "data": { "lab_id": "LAB-5531", "test": "Fasting Glucose", "value": 112,
               "unit": "mg/dL", "ref_range": "70-99", "flag": "high", "date": "2026-10-20" } } ],
  "action_required": null,   // or see section 2
  "disclaimer": "This is not medical advice. Please discuss results and treatment with your doctor.",
  "mode": "offline",         // llm | claude | offline | guardrail | mock | error  (debug panel)
  "fallback_reason": null,   // llm_rate_limited | llm_error | claude_error when an LLM answer fell back to offline
  "latency_ms": 212
}
```

* For document citations, `ref` is the chunk id - the UI opens it with `GET /sources/{ref}`.
* Every `[Sx]` tag in `answer` has a matching entry in `citations`.
* Card types: `lab_result`, `appointments` (`{items:[...]}`), `coverage`, `pending_tests` (`{procedure, items:[{name,status,completed_date}]}`), `department` (`{items:[...]}`).

### 1b. `POST /chat/stream` (what the UI uses)

Same request body. Response is **Server-Sent Events**; the answer text is only sent after the grounding check.

```
event: agent   data: {"type":"agent","name":"surgery_readiness","title":"Surgery Readiness Agent"}   (agent only)
event: tool    data: {"type":"tool","seq":1,"name":"get_orders","label":"Checking your doctor's orders","status":"running|done|failed"}
event: step    data: {"type":"step","index":1,"title":"Find your recommended surgery","status":"running|done|warning|stopped","details":["... [S1]."]}
event: status  data: {"type":"status","text":"Verifying every fact against its source"}
event: final   data: {"type":"final","response":{ ...same JSON as POST /chat... }}
```

### 1c. Surgery Readiness Agent (`intent: "agent"`)

Triggered for patients by goals such as "Get me ready for my surgery" / "Help me prepare for my operation".
The response adds:

```jsonc
"agent": { "name": "surgery_readiness", "title": "Surgery Readiness Agent",
           "steps": [ {"index":1, "title":"...", "status":"done", "details":["... [S1]."]} ],
           "summary": "LLM-written overview (verified) or null", "summary_by": "llm | claude | null" },
"action_required": { "type": "confirm_plan", "pending_action_id": "PA-…", "expires_at": "…",
                     "summary": "…", "items": [ {"index":0, "type":"book_test", "label":"Book Electrocardiogram (ECG)", "detail":"Thu 29 Oct, 09:00 at …"},
                                                {"index":2, "type":"submit_prior_auth", "label":"Submit prior authorization for …", "detail":"…"} ] }
```

## 2. Actions (two-phase commit)

```jsonc
"action_required": {
  "type": "confirm_reschedule",
  "pending_action_id": "PA-1A2B3C4D",
  "summary": "Move Cardiology (Dr. Arjun Rao) from Nov 02, 09:00 to Nov 04, 10:30",
  "expires_at": "2026-10-28T10:40:00",      // hospital local time
  "appointment_id": "APT-1042",
  "new_start": "2026-11-04T10:30"
}
```

| Endpoint | Body | Success | Errors |
|---|---|---|---|
| `POST /actions/confirm` | `{pending_action_id, selected?: [item indexes]}` (`selected` only for care plans; default all) | reschedule: `{status:"done", message, appointment_id, new_start}` - care plan: `{status:"done", message, results:[{index, type, message, ...}]}` | 400 bad selection, 404 not yours / unknown / already used, 409 slot taken or data changed (care plans are all-or-nothing), 410 expired |
| `POST /actions/cancel` | `{pending_action_id}` | `{status:"cancelled"}` | 404 |

## 3. Other endpoints

| Endpoint | Purpose | Response |
|---|---|---|
| `POST /auth/login` | Login (5/min) | `{access_token, token_type, user:{id, username, name, role, patient_id}}` |
| `GET /me/profile` | Header / plan | user + `plan:{name, member_id, coverage_end}` |
| `GET /me/appointments` | Sidebar | upcoming appointments (`[]` for staff) |
| `GET /me/pending-tests` | Sidebar | pending pre_op / lab / imaging orders |
| `GET /sources/{chunk_id}` | Citation drawer | `{chunk_id, doc_id, title, section, doc_type, effective_date, version, text}` |
| `GET /admin/audit?limit=50` | Staff only | masked audit rows |
| `GET /health` | Liveness | `{ok, ai_mode}` |

## 4. Tools

`patient_id` is **never** a parameter the LLM can set - `backend/app/tools/registry.py` injects it from the JWT
and strips any identity arguments. Every tool returns `{"ok": true, "data": ...}` or
`{"ok": false, "error": "not_found" | "forbidden" | "invalid: <reason>" | "unknown_tool"}`.

| Tool | LLM-visible parameters | Roles | Returns |
|---|---|---|---|
| `search_hospital_docs` (AI layer) | query, doc_type? | all | `[{chunk_id, doc_id, title, section, doc_type, effective_date, text, score}]` |
| `get_appointments` | status? (upcoming/past), department? | patient, staff* | `[{appointment_id, department, doctor, doctor_id, start, end, location, status}]` |
| `get_lab_results` | test_name?, latest_only? | patient | `[{lab_id, test, value, unit, ref_range, flag, date}]` |
| `get_orders` | order_type? (procedure/pre_op/imaging/lab), status? | patient | `[{order_id, type, description, status, ordered_by, linked_procedure, ordered_date, completed_date}]` |
| `check_coverage` | procedure_name or procedure_code | patient | `{covered, procedure, procedure_code, plan, coverage_pct, prior_auth_required, est_patient_cost, deductible, currency, reasons[], rule_id, plan_doc_ref}` |
| `get_available_slots` | appointment_id? / doctor_id? / department?, from_date? | patient, staff | `[{slot_id, doctor, doctor_id, department, start}]` |
| `propose_reschedule` | appointment_id, slot_id | patient | `{pending_action_id, summary, appointment_id, old_start, new_start, expires_at}` |
| `find_department` | symptom_or_specialty | patient, staff | `[{department, location, phone, hours}]` |

| `get_test_slots` (agent) | test_name, from_date? | patient, staff | `[{slot_id, service, location, start}]` (blood tests are walk-in: not_found) |
| `get_prior_auth_requests` (agent) | - | patient | `[{request_id, procedure_code, procedure, status, submitted_date}]` |
| `propose_care_plan` (agent) | items: `[{type:"book_test", order_id, slot_id} \| {type:"submit_prior_auth", procedure_code}]` | patient | `{pending_action_id, items, summary, expires_at}` |

\* staff see the schedule without patient locations. The three agent tools are used by the agent's code and are
not offered to the LLM.

**Deviation from the original plan:** insurance validity is stored per member (`patients.coverage_start/coverage_end`)
instead of on `insurance_plans`, because one member's policy can lapse while the plan product is still sold.

## 5. Seed scenarios (password `demo123`)

| Login | Patient | Scenario |
|---|---|---|
| asha | Asha Verma, Gold | Knee replacement covered 80 % with prior auth; cardiology appointment in 5 days to reschedule; a GP appointment inside the 24 h window |
| rahul | Rahul Mehta, Basic | Gallbladder surgery recommended; CBC done, ECG + chest X-ray pending |
| meera | Meera Iyer, Silver | Glucose and HbA1c history; knee replacement blocked by a 730-day waiting period |
| john | John D'Souza, Gold (expired) | Coverage refused: policy expired |
| staff1 | Kavya, front desk | Staff role: policies, departments, slots - no lab values |
