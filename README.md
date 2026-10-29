# City Care Hospital: AI Patient Services Assistant

An assistant that answers hospital questions and performs **authorized** service actions using hospital
policies, patient records, insurance rules, schedules and lab reports. Every answer is **grounded** (each
fact carries a citation), **explainable** (sources, coverage reasons, debug panel) and **secure** (identity
comes from the token, never from the AI). It never states a medical fact it didn't get from a source.

```
React UI ──JWT──▶ FastAPI ──▶ answer_query()
                     │           guardrails → intent → Claude tool-use loop (or offline pipeline)
                     │           → grounding verifier → response
                     ├─ tool executor (injects patient_id, role checks, audit) ─▶ SQLite
                     └─ /sources ◀── ChromaDB (hospital documents, reranked)
```

## Quick start (Windows / PowerShell)

```powershell
.\run.ps1 setup        # venv + pip + npm, seed DB, build vector store
.\run.ps1 api          # http://127.0.0.1:8000  (Swagger UI at /docs)
.\run.ps1 web          # http://localhost:5173   (in a second terminal)
```

Sign in with a demo account (password `demo123`): `asha`, `rahul`, `meera`, `john` (patients) or `staff1`.

### LLM (Groq free tier), Claude or offline

* With `LLM_API_KEY` set in `.env`, answers come from an **OpenAI-compatible LLM** with tool calling. The default
  is **Groq's free tier** (`qwen/qwen3.8-27b`, key from https://console.groq.com/keys). Change
  `LLM_BASE_URL` / `LLM_MODEL` to use Ollama (local), Gemini, OpenRouter or xAI instead - no code changes.
* With `ANTHROPIC_API_KEY` set instead, answers come from **Claude** (`claude-sonnet-5-5`).
* Without a key, or if the API fails, a **deterministic offline pipeline** answers with the same tools, retrieval,
  citations and grounding verifier. The demo always works.
* `MOCK_AI=true` returns canned responses (for UI work only).

## The 8 question types

| Type | Try (user) | How it is answered |
|---|---|---|
| Policy | "What are visiting hours for ICU patients?" (asha) | RAG over policies + citation |
| Procedure | "How do I schedule an MRI scan?" | RAG, numbered steps |
| Personal data | "What are my upcoming appointments?" | `get_appointments` (scoped to the token) |
| Eligibility | "Am I covered for knee replacement?" (asha / john / meera) | `check_coverage` rules engine + plan clause |
| Lab result | "What is my latest blood sugar reading?" (meera) | `get_lab_results`, no interpretation |
| Multi-step | "My doctor recommended surgery. What pre-op tests are still pending?" (rahul) | orders + protocol (RAG) + status |
| Action | "Reschedule my cardiology appointment" (asha) | slots → pending action → **Confirm** in the UI |
| Not found | "Do you have treatment information for proton beam therapy?" | reranker threshold → grounded not-found |

### AI agents (7)

Patients see an **"Your AI agents"** hub (welcome message + sidebar) and a **🔔 bell**. Every agent plans steps,
uses hospital tools, streams its progress live, cites every fact, and proposes **one plan that the patient approves**.

| Agent | Try (user) | What it does |
|---|---|---|
| 🩺 Surgery Readiness | "Get me ready for my surgery" (rahul) | insurance + prior auth, protocol tests vs record, books tests, submits prior auth |
| 📅 Appointment Booking | "I have thyroid problems, book me a doctor next week in the afternoon" (asha) | symptom → department, no duplicates, doctor continuity, preferred day/time, no clashes |
| 🗺️ Visit Planner | "Plan my visit tomorrow" (asha) | timeline of the day, where to go, what to bring, fasting / walk-in tests, arrival rules |
| 🔔 Proactive Care | runs automatically at login (bell) · "Check my reminders" | appointments soon, tests to book, results to follow up, insurance expiry, surgery paperwork - each with a one-click action |
| 🧪 Lab Follow-up | "My cholesterol report is high, what next?" (john) | no interpretation; right department; existing visit or books a follow-up |
| 💰 Cost Estimate | "How much will my knee replacement cost?" (asha) | your share from the rules engine, plan clauses, prepares pre-approval |
| 🔁 Smart Rescheduling | "I'm travelling next week, move my appointments" (asha) / "Move all my appointments to afternoons" (rahul) | moves every affected appointment, respects the 24-hour rule, one approval |

Agents live in `ai/agents/` (shared base class + `registry.py` with the trigger phrases). Steps run as code; the LLM
only writes the summary, so agents work on the free tier and offline.

### Surgery Readiness Agent

Log in as **rahul** and ask **"Get me ready for my surgery"**. The agent works through 7 steps live on screen:
find the recommended surgery → check insurance and prior authorization → read the pre-operative protocol →
compare required tests with the record (and the 30-day validity rule) → find test slots, preferring one day for
all tests → check for an existing prior-auth request → prepare **one plan** (book ECG, book chest X-ray, submit
prior authorization). Nothing is booked until the patient ticks items and presses **Approve**; then the sidebar
shows the bookings. `asha` shows the "tests not ordered yet - ask your surgeon" branch; `meera` has no surgery.
The steps run as code (reliable, and cheap on Groq's free tier); the LLM only writes the short summary on top.

Answers stream over `POST /chat/stream` (Server-Sent Events): tool calls and agent steps appear as they happen,
and the answer text is shown only after the grounding check.

Safety: emergency phrases show the emergency number, requests for other people's records and prompt injection are refused,
medication or diagnosis questions are redirected to the doctor, and any sentence without a supporting source is removed.

## Project layout (who owns what)

| Folder | Owner | Contents |
|---|---|---|
| `data/docs/` | Member 1 | 12 hospital documents (policies, SOPs, protocol, plans, directory) |
| `ai/` | Member 1 | ingest, retriever (+ rerank + threshold), guardrails, classifier, tool schemas, prompts, orchestrator, offline pipeline, grounding verifier, `eval/` |
| `backend/` | Member 2 | FastAPI app, models, seed, auth (JWT), tools (appointments, labs, orders, eligibility, scheduling, directory), registry, audit, routers |
| `frontend/` | Member 3 | React + Tailwind UI, cards, citation drawer, confirm modal, debug panel (Debug button in the header), Playwright E2E |
| `tests/` | Member 3 (+1, 2) | pytest: question types, security, grounding, unit (eligibility, chunker, guardrails, Claude loop) |
| `CONTRACTS.md` | all | API, tool and seed contracts |

## Quality checks

```powershell
.\run.ps1 test        # pytest - question types, security, grounding, unit
.\run.ps1 e2e         # Playwright in Microsoft Edge (own servers + e2e.db)
.\run.ps1 eval        # 40-case evaluation -> ai/eval/report.md
.\run.ps1 calibrate   # reranker score distributions for the not-found threshold
```

Before a demo, run `.\run.ps1 seed`. Appointment dates are relative to today, so they stay upcoming.

## Security model

* `patient_id` comes only from the signed JWT. The tool executor strips any identity argument the model sends.
* Role checks per tool (staff cannot read lab values). Another patient's resources return 404.
* Write actions are two-phase: `propose_reschedule` stores a pending action; `POST /actions/confirm` (same user,
  within 10 minutes, slot still free, more than 24 hours before the appointment) commits atomically.
* Audit log on every request, tool call and action, with PHI masked (no values, names or free-text queries).
* Rate limits (20 chats/min, 5 logins/min), CORS limited to the UI origin, Pydantic validation, per-user chat history.
