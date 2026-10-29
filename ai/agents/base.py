"""Shared building blocks for every agent.

An agent = a goal-driven sequence of steps. Each step calls tools through the RunContext (so the backend still
injects identity, checks roles and audits), makes a decision from the results, and writes short sentences that
are tagged with the sources that support them. Steps are streamed live to the UI. Actions are never executed by
an agent: it collects plan items and proposes ONE care plan that the patient approves.
"""
import re
from datetime import date, timedelta

from ..grounding import split_sentences
from ..sources import RunContext

# ------------------------------------------------------------------ text helpers
_TEST_KEYS = [
    ("cbc", ("complete blood count", "cbc", "blood count")),
    ("ecg", ("electrocardiogram", "ecg")),
    ("xray", ("chest x-ray", "x-ray", "xray")),
    ("hba1c", ("hba1c",)),
    ("coag", ("coagulation", "pt/inr")),
    ("mri", ("mri", "magnetic resonance")),
]
BOOKABLE_TESTS = {"ecg", "xray", "mri"}  # the rest (blood tests) are walk-in at the Laboratory


def test_key(name: str) -> str:
    t = name.lower()
    for key, words in _TEST_KEYS:
        if any(w in t for w in words):
            return key
    return t.strip()


def _sentence(chunks, ids, must):
    """First sentence (with its source id) containing every phrase in `must`."""
    for c, sid in zip(chunks, ids):
        for line in c["text"].splitlines():
            for s in split_sentences(line):
                if all(m.lower() in s.lower() for m in must):
                    return s, sid
    return None


def _cite(sentence: str, *sids: str) -> str:
    s = sentence.rstrip()
    tags = "".join(f"[{x}]" for x in sids if x)
    if s and s[-1] in ".!?":
        return f"{s[:-1]} {tags}{s[-1]}"
    return f"{s} {tags}."


# ------------------------------------------------------------------ date / time understanding
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"], start=1)}
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"


def _date(day: int, month: int, today: date) -> date | None:
    try:
        d = date(today.year, month, day)
    except ValueError:
        return None
    return d if d >= today else date(today.year + 1, month, day)


def parse_range(text: str, today: date | None = None) -> tuple[date, date] | None:
    """'next week', 'this week', 'from 3 to 7 Nov', '3-7 November' -> (start, end)."""
    today = today or date.today()
    t = text.lower()
    if re.search(r"\bnext week\b", t):
        start = today + timedelta(days=7 - today.weekday())
        return start, start + timedelta(days=6)
    if re.search(r"\bthis week\b", t):
        return today, today + timedelta(days=6 - today.weekday())
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s*(?:-|–|to|until|till|and)\s*(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON}", t)
    if m:
        a, b = _date(int(m.group(1)), MONTHS[m.group(3)], today), _date(int(m.group(2)), MONTHS[m.group(3)], today)
        if a and b:
            return (a, b) if a <= b else (b, a)
    d = parse_day(text, today)
    return (d, d) if d else None


def parse_day(text: str, today: date | None = None) -> date | None:
    """'today', 'tomorrow', 'day after tomorrow', 'on friday', '5 nov' / 'nov 5' -> a date."""
    today = today or date.today()
    t = text.lower()
    if re.search(r"\bday after tomorrow\b", t):
        return today + timedelta(days=2)
    if re.search(r"\btomorrow\b", t):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b", t):
        return today
    m = re.search(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+{_MON}\b", t) or re.search(rf"\b{_MON}\s+(\d{{1,2}})\b", t)
    if m:
        groups = m.groups()
        day, mon = (groups[0], groups[1]) if groups[0].isdigit() else (groups[1], groups[0])
        return _date(int(day), MONTHS[mon[:3]], today)
    for i, name in enumerate(WEEKDAYS):
        if re.search(rf"\b{name}\b", t):
            ahead = (i - today.weekday()) % 7 or 7
            return today + timedelta(days=ahead)
    return None


def parse_time_of_day(text: str) -> str | None:
    t = text.lower()
    for name in ("morning", "afternoon", "evening"):
        if re.search(rf"\b{name}s?\b", t):
            return name
    return None


def matches_time_of_day(iso: str, tod: str | None) -> bool:
    if not tod:
        return True
    hour = int(iso[11:13])
    return {"morning": hour < 12, "afternoon": 12 <= hour < 17, "evening": hour >= 17}[tod]


def fmt_day(d: date) -> str:
    return d.strftime("%a %d %b %Y")


# ------------------------------------------------------------------ the agent base class
class BaseAgent:
    NAME = "agent"
    TITLE = "Agent"
    ICON = "🤖"

    def __init__(self, ctx: RunContext, text: str = ""):
        self.ctx = ctx
        self.text = text
        self.steps: list[dict] = []
        self.plan_items: list[dict] = []
        self.record_sids: list[str] = []
        self.cards: list[dict] = []

    # ---- steps (streamed live) ----
    def _start(self, title: str) -> dict:
        step = {"index": len(self.steps) + 1, "title": title, "status": "running", "details": []}
        self.steps.append(step)
        self.ctx.emit({"type": "step", **step})
        return step

    def _finish(self, step: dict, status: str, details: list[str]) -> None:
        step["status"], step["details"] = status, [d for d in details if d]
        self.ctx.emit({"type": "step", **step})

    def _empty(self, ids, text):
        return _cite(text, ids[0]) if ids else ""

    # ---- helpers ----
    def note(self, title: str, text: str) -> str:
        """Record how the agent understood the request as a citable source (transparent, verifiable)."""
        return self.ctx.add_source(f"note:{title}:{text}", source_type="record", title=title, text=text)

    def doc_sentence(self, query: str, doc_type: str, must: list[str]):
        out, ids, _ = self.ctx.call("search_hospital_docs", {"query": query, "doc_type": doc_type})
        return _sentence(out.get("data") or [], ids, must)

    def propose(self, title: str = "Prepare your plan for approval", ready: str | None = None) -> None:
        step = self._start(title)
        if not self.plan_items:
            self._finish(step, "done", [_cite("There is nothing to book or submit right now.", *self.record_sids)])
            return
        out, ids, _ = self.ctx.call("propose_care_plan", {"items": self.plan_items})
        if out.get("ok"):
            self._finish(step, "done", [_cite(ready or "Your plan is ready - nothing is booked or submitted until "
                                                       "you approve it.", ids[0])])
        else:
            self._finish(step, "warning", [_cite(f"I could not prepare the plan: {self.ctx.by_id(ids[0])['text']}.",
                                                 ids[0]) if ids else "I could not prepare the plan."])

    def _result(self) -> dict:
        lines = ["Here is what I found and did:"]
        for s in self.steps:
            lines += [f"- {d}" for d in s["details"]]
        return {"draft": "\n".join(lines), "steps": self.steps, "cards": self.cards}

    def run(self) -> dict:  # pragma: no cover - implemented by each agent
        raise NotImplementedError
