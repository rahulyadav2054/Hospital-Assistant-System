"""Canned /chat responses (MOCK_AI=true). Lets the UI be built and demoed without the AI layer."""

_BASE = {"citations": [], "tool_calls": [], "cards": [], "action_required": None, "disclaimer": None,
         "mode": "mock", "fallback_reason": None, "latency_ms": 0}


def mock_response(message: str) -> dict:
    m = message.lower()
    if "chest pain" in m:
        return {**_BASE, "status": "emergency", "intent": "out_of_scope",
                "answer": "This may be a medical emergency. Call 108 or the hospital emergency line (extension 911) now."}
    if "proton" in m:
        return {**_BASE, "status": "not_found", "intent": "policy",
                "answer": "I couldn't find this in the hospital's records or policies."}
    if "sugar" in m or "glucose" in m:
        return {**_BASE, "status": "ok", "intent": "lab_result",
                "answer": "- Fasting Glucose: 112 mg/dL on 2026-10-20 (reference range 70-99 mg/dL, marked high) [S1]",
                "citations": [{"id": "S1", "source_type": "record", "title": "Lab result: Fasting Glucose",
                               "section": None, "ref": "LAB-5531", "date": "2026-10-20"}],
                "tool_calls": [{"name": "get_lab_results", "ok": True}],
                "cards": [{"type": "lab_result", "data": {"lab_id": "LAB-5531", "test": "Fasting Glucose",
                                                          "value": 112, "unit": "mg/dL", "ref_range": "70-99",
                                                          "flag": "high", "date": "2026-10-20"}}],
                "disclaimer": "This is not medical advice. Please discuss results and treatment with your doctor."}
    if "reschedule" in m:
        return {**_BASE, "status": "ok", "intent": "action",
                "answer": "I have prepared this change, but nothing changes until you confirm it [S1].",
                "citations": [{"id": "S1", "source_type": "record", "title": "Pending reschedule request",
                               "section": None, "ref": "PA-MOCK", "date": None}],
                "action_required": {"type": "confirm_reschedule", "pending_action_id": "PA-MOCK",
                                    "summary": "Move Cardiology (Dr. Arjun Rao) from Nov 02, 09:00 to Nov 04, 10:30",
                                    "expires_at": "2099-01-01T00:00:00"}}
    return {**_BASE, "status": "ok", "intent": "policy",
            "answer": "ICU visiting hours are 11:00–12:00 and 17:00–18:00 daily. [S1]",
            "citations": [{"id": "S1", "source_type": "document", "title": "Visitor Policy",
                           "section": "3.2 ICU Visiting Hours", "ref": "POL-VIS-001::5::0", "date": "2026-01-15"}],
            "tool_calls": [{"name": "search_hospital_docs", "ok": True}]}
