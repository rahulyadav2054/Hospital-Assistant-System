"""Tool definitions given to Claude.

NOTE: no tool has a patient_id parameter - the backend executor injects it from the verified token.
"""

TOOLS = [
    {
        "name": "search_hospital_docs",
        "description": "Search official hospital policies, procedures, insurance plan documents, clinical "
                       "protocols and the department directory. Use for any question about rules, steps, hours, "
                       "requirements, preparation or locations. Returns cited text chunks.",
        "input_schema": {"type": "object", "properties": {
            "query": {"type": "string", "description": "A focused search query"},
            "doc_type": {"type": "string",
                         "enum": ["policy", "procedure", "insurance", "directory", "clinical_protocol"]}},
            "required": ["query"]},
    },
    {
        "name": "get_appointments",
        "description": "Get the CURRENT patient's appointments. Never use for other people.",
        "input_schema": {"type": "object", "properties": {
            "status": {"type": "string", "enum": ["upcoming", "past"]},
            "department": {"type": "string", "description": "Department name, e.g. Cardiology"}}},
    },
    {
        "name": "get_lab_results",
        "description": "Get the CURRENT patient's lab results. Never use for other people. "
                       "latest_only=true returns only the most recent result of each test.",
        "input_schema": {"type": "object", "properties": {
            "test_name": {"type": "string", "description": "e.g. 'Fasting Glucose', 'HbA1c', 'CBC'"},
            "latest_only": {"type": "boolean"}}},
    },
    {
        "name": "get_orders",
        "description": "Get the CURRENT patient's doctor orders: recommended procedures/surgeries ('procedure'), "
                       "pre-operative tests ('pre_op'), imaging and lab orders, with status pending/completed.",
        "input_schema": {"type": "object", "properties": {
            "order_type": {"type": "string", "enum": ["procedure", "pre_op", "imaging", "lab"]},
            "status": {"type": "string", "enum": ["pending", "completed"]}}},
    },
    {
        "name": "check_coverage",
        "description": "Deterministically check whether the current patient's insurance covers a procedure. "
                       "ALWAYS use this for coverage questions; never decide coverage yourself.",
        "input_schema": {"type": "object", "properties": {
            "procedure_name": {"type": "string"},
            "procedure_code": {"type": "string"}}},
    },
    {
        "name": "get_available_slots",
        "description": "List free appointment slots. For a reschedule pass appointment_id so slots are with the "
                       "same doctor. from_date is YYYY-MM-DD.",
        "input_schema": {"type": "object", "properties": {
            "appointment_id": {"type": "string"},
            "department": {"type": "string"},
            "doctor_id": {"type": "string"},
            "from_date": {"type": "string"}}},
    },
    {
        "name": "propose_reschedule",
        "description": "Create a PENDING reschedule request for one of the current patient's appointments. "
                       "This does NOT change anything; the patient must press Confirm in the app.",
        "input_schema": {"type": "object", "properties": {
            "appointment_id": {"type": "string"},
            "slot_id": {"type": "integer"}},
            "required": ["appointment_id", "slot_id"]},
    },
    {
        "name": "find_department",
        "description": "Find the hospital department (location, phone, hours) for a symptom, body part or "
                       "specialty, e.g. 'knee pain' or 'cardiology'.",
        "input_schema": {"type": "object", "properties": {
            "symptom_or_specialty": {"type": "string"}},
            "required": ["symptom_or_specialty"]},
    },
]

TOOL_NAMES = {t["name"] for t in TOOLS}

# OpenAI-compatible format (Groq, Ollama, Gemini, OpenRouter, xAI ...): same tools, different wrapper.
OPENAI_TOOLS = [{"type": "function",
                 "function": {"name": t["name"], "description": t["description"],
                              "parameters": t["input_schema"]}} for t in TOOLS]

# Tools each intent can need. Sending only these keeps every request small, which matters on
# free tiers with tokens-per-minute limits (e.g. Groq: 7,000 input tokens/minute).
INTENT_TOOLS = {
    "policy": ["search_hospital_docs", "find_department"],
    "procedure": ["search_hospital_docs"],
    "personal_data": ["get_appointments", "get_orders"],
    "lab_result": ["get_lab_results"],
    "eligibility": ["check_coverage", "search_hospital_docs"],
    "multi_step": ["get_orders", "get_lab_results", "search_hospital_docs"],
    "action": ["get_appointments", "get_available_slots", "propose_reschedule", "search_hospital_docs"],
    "out_of_scope": ["search_hospital_docs", "find_department"],
}


def openai_tools_for(intent: str) -> list[dict]:
    names = set(INTENT_TOOLS.get(intent, TOOL_NAMES))
    return [t for t in OPENAI_TOOLS if t["function"]["name"] in names]

