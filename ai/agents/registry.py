"""Which agent handles which goal. Checked in order; the first trigger that matches wins.

Triggers are deliberately specific so ordinary questions ("How do I schedule an MRI?", "When is my next
appointment?") keep going to the normal question-answering pipeline.
"""
import re

from .appointment_booking import AppointmentBookingAgent
from .cost_estimate import CostEstimateAgent
from .lab_follow_up import LabFollowUpAgent
from .proactive_care import ProactiveCareAgent
from .smart_reschedule import SmartReschedulingAgent
from .surgery_readiness import SurgeryReadinessAgent
from .visit_planner import VisitPlannerAgent

_QUESTION = re.compile(r"^\s*(how|where|what|when|which|why|who|is|are|am|does|do i|can i|should i|will|did)\b", re.I)
_TEST_WORDS = re.compile(r"\b(ecg|electrocardiogram|x-?ray|xray|mri|cbc|blood test|test)s?\b", re.I)

TRIGGERS = [
    (SurgeryReadinessAgent, re.compile(
        r"\b(get|make) me ready\b|\bprepare me\b|\bhelp me (get )?prepare\b"
        r"|\b(get )?ready for (my |the )?(surgery|operation)\b|\bsurgery readiness\b|\breadiness check\b"
        r"|\bprepare for (my |the )?(surgery|operation)\b|\bplan (for )?my (surgery|operation)\b", re.I), None),
    (ProactiveCareAgent, re.compile(
        r"\b(my )?(reminders?|notifications?|alerts?)\b|\bto-?do list\b|\banything (due|pending)\b"
        r"|\bwhat('s| is) (due|pending) for me\b|\bcheck (on )?my (health|care|status)\b|\bhealth check-?in\b"
        r"|\banything i (should|need to) (do|know)\b", re.I), None),
    (VisitPlannerAgent, re.compile(
        r"\bplan (my|our|the) (next )?(visit|day|trip)\b|\bvisit plan\b|\bitinerary\b"
        r"|\b(coming|going) to (the )?hospital\b|\bmy (hospital )?(schedule|plan) for (today|tomorrow)\b", re.I), None),
    (SmartReschedulingAgent, re.compile(
        r"\ball (of )?my appointments\b|\bmy appointments\b.{0,40}\b(to|into) (the )?(mornings?|afternoons?|evenings?)\b"
        r"|\b(i('m| am| will be| would be| shall be)|we('re| are| will be))\s+(travell?ing|away|out of (town|station"
        r"|the city)|not available|unavailable|on leave|on vacation|on holiday)\b", re.I), None),
    (CostEstimateAgent, re.compile(
        r"\b(how much|cost|costs|price|estimate|expenses?|charges?|out of pocket)\b.{0,50}"
        r"\b(surgery|operation|procedure|replacement|cholecystectomy|gallbladder|mri|bypass|cabg|hernia)\b"
        r"|\b(surgery|operation|procedure|replacement|gallbladder|mri)\b.{0,40}\b(cost|price|estimate)\b"
        r"|\bpre-?approval\b|\bcost estimate\b", re.I), None),
    (LabFollowUpAgent, re.compile(
        r"\b(results?|reports?|readings?|levels?|sugar|glucose|hba1c|a1c|cholesterol|ha?emoglobin|creatinine|cbc"
        r"|platelets?|lab)\b.{0,60}\b(what (should i do |do i do |to do )?next|next steps?|follow[- ]?up|what now"
        r"|what should i do)\b|\blab follow[- ]?up\b", re.I), None),
    (AppointmentBookingAgent, re.compile(
        r"\b(book|schedule|make|fix|arrange|need|want|get)\b.{0,40}\b(appointment|consultation|doctor|specialist"
        r"|cardiologist|orthopa?edic\w*|physician|surgeon|endocrinologist|check-?up)\b|\bsee a (doctor|specialist)\b",
        re.I), "booking"),
]

BY_NAME = {cls.NAME: cls for cls, _, _ in TRIGGERS}
CATALOG = [{"name": cls.NAME, "title": cls.TITLE, "icon": cls.ICON} for cls, _, _ in TRIGGERS]


def match(text: str) -> str | None:
    """Name of the agent that should handle this message, or None."""
    for cls, rx, kind in TRIGGERS:
        if not rx.search(text):
            continue
        if kind == "booking" and (_QUESTION.search(text) or re.search(r"\bre-?schedul", text, re.I)
                                  or _TEST_WORDS.search(text)):
            continue
        return cls.NAME
    return None
