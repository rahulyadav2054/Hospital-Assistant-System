"""Intent classification.

classify()        - Claude with forced structured output (used when an API key is configured).
classify_rules()  - deterministic keyword rules (offline mode, and fallback if the API call fails).
"""
import re

from . import config
from .prompts import CLASSIFIER_PROMPT

INTENTS = ["policy", "procedure", "personal_data", "eligibility", "lab_result", "multi_step", "action",
           "out_of_scope"]

CLASSIFY_TOOL = {
    "name": "classify_intent",
    "description": "Classify the patient's message.",
    "input_schema": {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": INTENTS},
            "entities": {"type": "object", "properties": {
                "department": {"type": "string"}, "test_name": {"type": "string"},
                "procedure": {"type": "string"}}},
            "needs_patient_data": {"type": "boolean"},
        },
        "required": ["intent", "needs_patient_data"],
    },
}


def trim_history(history: list[dict], n: int) -> list[dict]:
    """Last n messages, starting with a user turn (the Messages API requires that)."""
    h = list(history[-n:]) if n else []
    while h and h[0]["role"] != "user":
        h.pop(0)
    return h


def classify(message: str, history: list[dict], client) -> dict:
    r = client.messages.create(
        model=config.model(), max_tokens=300, system=CLASSIFIER_PROMPT,
        tools=[CLASSIFY_TOOL], tool_choice={"type": "tool", "name": "classify_intent"},
        messages=trim_history(history, 4) + [{"role": "user", "content": message}])
    out = next(b.input for b in r.content if b.type == "tool_use")
    if out.get("intent") not in INTENTS:
        out["intent"] = "policy"
    return out


# ---------------------------------------------------------------- deterministic rules
# Goal-style requests handled by the Surgery Readiness Agent (multi-step plan + one approval).
_AGENT = re.compile(r"\b(get|make) me ready\b|\bprepare me\b|\bhelp me (get )?prepare\b"
                    r"|\b(get )?ready for (my |the )?(surgery|operation)\b|\bsurgery readiness\b|\breadiness check\b"
                    r"|\bprepare for (my |the )?(surgery|operation)\b|\bplan (for )?my (surgery|operation)\b", re.I)
# "do the ECG test", "book my chest X-ray tomorrow", "I need an MRI" -> book one test (not "how do I ...").
_BOOK_TEST = re.compile(r"\b(book|schedule|do|get|take|arrange|fix|need|want)\b.{0,40}?"
                        r"\b(ecg|electrocardiogram|x-?ray|xray|mri|blood test|cbc|complete blood count|test)s?\b", re.I)
_NOT_BOOKING = re.compile(r"^\s*(how|where|what|when|which|why|who|is|are|am|does|do i|can i|should i|will)\b"
                          r"|\b(results?|reports?|reading|levels?|covered|coverage|cost)\b", re.I)
_ACTION = re.compile(r"\b(re-?schedul\w*|postpone|move|shift|change|cancel)\b.*\b(appointment|appt|visit|booking|consultation)s?\b"
                     r"|\bre-?schedul\w*\b|\bcancel my\b", re.I)
_MULTI = re.compile(r"\bpre-?op\b|\bpre-?operative\b|\bbefore (my |the )?(surgery|operation)\b|\btests?\b.{0,40}\bpending\b"
                    r"|\bpending\b.{0,40}\btests?\b|\bstill (need|pending|left)\b", re.I)
_ELIG = re.compile(r"\bcover(ed|age|s)?\b|\beligib\w*\b|\bprior auth\w*\b|\binsurance (pay|cover)\b|\bclaim\b"
                   r"|\bhow much will (i|my insurance) pay\b", re.I)
_LAB_WORDS = re.compile(r"\b(blood sugar|sugar|glucose|hba1c|a1c|cholesterol|lipid|ha?emoglobin|cbc|blood count|"
                        r"platelets?|wbc|creatinine)\b", re.I)
_LAB_CTX = re.compile(r"\b(my|latest|last|recent|trend|history|results?|reading|levels?|report|value)\b", re.I)
_MY_LABS = re.compile(r"\bmy (lab|test|blood)\s*(results?|reports?|tests?|work)\b|\blab results\b", re.I)
_PERSONAL = re.compile(r"\bmy\b.{0,30}\b(appointments?|visits?|schedule|bookings?|orders?|doctors?)\b"
                       r"|\bupcoming\b|\bwhen is my\b|\bdo i have (an? |any )?(appointment|visit)", re.I)
_DIRECTORY = re.compile(r"\b(which|what) (department|doctor|specialist|clinic)\b|\bwho (treats|handles)\b"
                        r"|\bspecialist for\b|\bwhere (is|are|do i go|can i find)\b|\bdepartment for\b"
                        r"|\b(phone|extension|contact) (number )?(of|for)\b|\blocated\b", re.I)
_PROCEDURE = re.compile(r"\bhow (do|can|to|should|would)\b|\bsteps?\b|\bprocess\b|\bprocedure for\b|\bprepare\b"
                        r"|\bwhat (should|do) i (bring|need)\b|\bwhat happens\b", re.I)
_OUT_OF_SCOPE = re.compile(r"\b(joke|weather|cricket|football|movie|song|poem|recipe|stock|bitcoin|"
                           r"write (some )?code|python script|homework)\b", re.I)
_FOLLOW_UP = re.compile(r"\b(it|that|there|this|they|them|those)\b", re.I)


def contextual_message(message: str, history: list[dict]) -> str:
    """Short pronoun-only follow-ups ('Where is it?') are merged with the previous user question."""
    prev = [h["content"] for h in history if h["role"] == "user"]
    if prev and len(message.split()) <= 6 and _FOLLOW_UP.search(message):
        return f"{prev[-1]} {message}"
    return message


def classify_rules(message: str, history: list[dict] | None = None) -> dict:
    text = contextual_message(message, history or [])
    route = None
    if _AGENT.search(text):
        intent = "agent"
    elif _OUT_OF_SCOPE.search(text):
        intent = "out_of_scope"
    elif _BOOK_TEST.search(text) and not _NOT_BOOKING.search(text):
        intent, route = "action", "book_test"
    elif _ACTION.search(text):
        intent = "action"
    elif _MULTI.search(text):
        intent = "multi_step"
    elif _ELIG.search(text):
        intent = "eligibility"
    elif (_LAB_WORDS.search(text) and _LAB_CTX.search(text)) or _MY_LABS.search(text):
        intent = "lab_result"
    elif _PERSONAL.search(text):
        intent = "personal_data"
    elif _DIRECTORY.search(text):
        intent, route = "policy", "directory"
    elif _PROCEDURE.search(text):
        intent = "procedure"
    else:
        intent = "policy"
    return {"intent": intent, "route": route, "text": text,
            "needs_patient_data": intent in ("personal_data", "eligibility", "lab_result", "multi_step", "action",
                                             "agent")}
