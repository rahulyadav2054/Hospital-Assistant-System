"""Input guardrails - the fast first layer.

Layer 2 is the system prompt; layer 3 (the one that really matters) is backend authorization.
Never rely on the LLM alone for security.
"""
import re

EMERGENCY = ["chest pain", "can't breathe", "cant breathe", "cannot breathe", "not breathing", "unconscious",
             "severe bleeding", "bleeding heavily", "stroke", "suicide", "suicidal", "kill myself", "overdose",
             "seizure", "heart attack", "fainted", "collapsed"]
INJECTION = ["ignore previous", "ignore all", "ignore the above", "ignore your instructions", "system prompt",
             "you are now", "act as", "pretend to be", "all patients", "other patient", "another patient",
             "developer mode", "jailbreak", "reveal your instructions", "database dump", "select * from"]

_EMERGENCY_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in EMERGENCY) + r")", re.I)
_INJECTION_RE = re.compile(r"\b(" + "|".join(re.escape(k) for k in INJECTION) + r")\b", re.I)

EMERGENCY_MSG = ("This may be a medical emergency. Call 108 or the hospital emergency line (extension 911) now, "
                 "or go to the Emergency Department (Block A, Ground Floor), which is open 24 hours.")
UNAUTHORIZED_MSG = ("I can only help with your own records and general hospital information. "
                    "Records of other people can't be shared without their written consent.")
TOO_LONG_MSG = "Your message is too long. Please keep it under 2000 characters."
MEDICAL_ADVICE_MSG = ("I can't give medical advice about diagnoses, treatments or medicines. Please talk to your "
                      "doctor about this. I can help you find the right department or check your appointments.")
DIAGNOSIS_NOTE = ("I can't tell you what these results mean for your health or whether you have a condition. "
                  "Please discuss them with your doctor.")

_DIRECTORY_Q = re.compile(r"^\s*(which|what) (department|doctor|specialist)|who (treats|handles)|department for", re.I)

_RELATIONS = (r"wife|husband|son|daughter|mother|father|mom|mum|dad|brother|sister|friend|neighbou?r|child|kid|"
              r"grandmother|grandfather|grandma|grandpa|partner|uncle|aunt|cousin|colleague|boss")
_RECORD_WORDS = (r"labs?|results?|reports?|records?|appointments?|tests?|insurance|coverage|orders?|"
                 r"readings?|levels?|data|history|details|file|blood|sugar|glucose|hba1c|a1c|cholesterol|cbc|"
                 r"scans?|prescriptions?|medicines?|bills?")
_THIRD_PARTY = [
    re.compile(rf"\b(my\s+)?({_RELATIONS})['’]s\s+(\w+\s+){{0,2}}({_RECORD_WORDS})\b", re.I),
    re.compile(rf"\b(his|her|their)\s+(\w+\s+){{0,1}}({_RECORD_WORDS})\b", re.I),
    re.compile(rf"\b({_RECORD_WORDS})\s+(of|for)\s+my\s+({_RELATIONS})\b", re.I),
]
# Possessive words that are not people (or are relations, which the patterns above handle).
_NOT_PEOPLE = {"it", "what", "that", "there", "here", "he", "she", "who", "let", "where", "how", "today", "tomorrow",
               "yesterday", "doctor", "hospital", "plan", "patient", "icu", "everyone", "one", "someone", "nobody",
               "year", "week", "month", "day", "children", "women", "men", "people", "city", "care", "dr", "world",
               "insurer", "surgeon", "department", "nurse", "lab", "this", "when", "why", "name", "life", "body",
               "heart", "knee", "visitor", "member", "mri", "ct", "ecg", "scan", "test", "report", "result",
               "appointment", "policy", "insurance", "gold", "silver", "basic", "careshield", "ward", "unit",
               "pharmacy", "radiology", "cardiology", "orthopedics", "endocrinology", "surgery", "medicine",
               "laboratory", "emergency", "desk", "office", "child", "baby", "kid"}
_NOT_PEOPLE |= set(re.split(r"\|", _RELATIONS.replace("?", "").replace("neighbour", "neighbour|neighbor")))
_POSSESSIVE = re.compile(r"\b([A-Za-z]+)['’]s\b")
_PATIENT_ID = re.compile(r"\bP\d{3}\b", re.I)

_MEDICAL_ADVICE = [
    re.compile(r"\bshould i (stop|start|take|increase|decrease|reduce|change|skip|double|continue)\b", re.I),
    re.compile(r"\bcan i (stop|skip|double|reduce|increase) (my )?(medicine|medication|dose|tablets?|pills?|insulin)", re.I),
    re.compile(r"\bwhat (medicine|medication|drug|tablet|dose|dosage) should\b", re.I),
    re.compile(r"\bhow (much|many) .{0,40}should i take\b", re.I),
    re.compile(r"\b(cure|remedy|home remedy) for\b", re.I),
    re.compile(r"\bhow (do|can) i (cure|treat) (my|this)\b", re.I),
]
_DIAGNOSIS = [
    re.compile(r"\bdo i have\b", re.I),
    re.compile(r"\bam i (diabetic|sick|ill|healthy|okay|ok|at risk)\b", re.I),
    re.compile(r"\bis (this|it|that|my .{1,30}) (normal|serious|dangerous|bad|good|worrying|concerning)\b", re.I),
    re.compile(r"\bdiagnos", re.I),
    re.compile(r"\bwhat does (this|my|it) .{0,40}mean\b", re.I),
    re.compile(r"\bshould i (be )?worr", re.I),
]


def _own_names(user_ctx: dict) -> set[str]:
    name = (user_ctx or {}).get("name") or ""
    return {p.lower() for p in re.findall(r"[A-Za-z]+", name)}


def _mentions_third_party(msg: str, user_ctx: dict) -> bool:
    if any(p.search(msg) for p in _THIRD_PARTY):
        return True
    own = _own_names(user_ctx)
    for word in _POSSESSIVE.findall(msg):
        w = word.lower()
        if w not in _NOT_PEOPLE and w not in own:
            return True
    for pid in _PATIENT_ID.findall(msg):
        if pid.upper() != ((user_ctx or {}).get("patient_id") or "").upper():
            return True
    return False


def check_input(msg: str, user_ctx: dict | None = None) -> dict | None:
    """Return a short-circuit response dict, or None if the message may proceed."""
    if len(msg) > 2000:
        return {"status": "error", "answer": TOO_LONG_MSG}
    if _EMERGENCY_RE.search(msg) and not _DIRECTORY_Q.search(msg):
        return {"status": "emergency", "answer": EMERGENCY_MSG}
    if _INJECTION_RE.search(msg):
        return {"status": "unauthorized", "answer": UNAUTHORIZED_MSG}
    if _mentions_third_party(msg, user_ctx or {}):
        return {"status": "unauthorized", "answer": UNAUTHORIZED_MSG}
    return None


def is_medical_advice_request(msg: str) -> bool:
    return any(p.search(msg) for p in _MEDICAL_ADVICE)


def asks_for_diagnosis(msg: str) -> bool:
    return any(p.search(msg) for p in _DIAGNOSIS)
