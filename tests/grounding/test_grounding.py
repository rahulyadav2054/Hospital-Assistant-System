"""Grounding tests: no invented facts, correct citations, not-found (PDF Member 1 Step 10 / Member 3 Step 8)."""
import re

import pytest

from ai.grounding import NOT_FOUND_MSG, split_sentences, verify_grounding
from tests.conftest import ask

SOURCES = [
    {"id": "S1", "text": "ICU visiting hours are 11:00–12:00 and 17:00–18:00 daily.", "title": "Visitor Policy",
     "section": "3.2 ICU Visiting Hours", "ref": "POL-VIS-001::5::0", "date": "2026-01-15"},
    {"id": "S2", "text": "Estimated patient cost: INR 75000 (includes the INR 5000 deductible).", "title": "Coverage",
     "section": None, "ref": "R-G-27447", "date": None},
]


def test_keeps_supported_sentence():
    ans, status = verify_grounding("ICU visiting hours are 11:00–12:00 and 17:00–18:00 daily [S1].", SOURCES)
    assert status == "ok" and "11:00" in ans


def test_drops_untagged_fact():
    ans, status = verify_grounding("ICU hours are 11:00–12:00 [S1]. Parking costs INR 50 per hour.", SOURCES)
    assert status == "ok" and "Parking" not in ans


def test_drops_untagged_fact_without_numbers():
    ans, status = verify_grounding("ICU hours are 11:00–12:00 [S1]. You are covered for everything.", SOURCES)
    assert "covered for everything" not in ans


def test_drops_number_not_in_source():
    ans, status = verify_grounding("ICU visiting hours are 09:00–12:00 daily [S1].", SOURCES)
    assert status == "not_found" and ans == NOT_FOUND_MSG


def test_drops_unknown_tag():
    ans, status = verify_grounding("ICU visiting hours are 11:00–12:00 daily [S9].", SOURCES)
    assert status == "not_found"


def test_number_formatting_is_normalised():
    ans, status = verify_grounding("Your estimated cost is INR 75,000 [S2].", SOURCES)
    assert status == "ok"


def test_tag_after_full_stop_attaches_to_previous_sentence():
    ans, status = verify_grounding("ICU visiting hours are 11:00–12:00 daily. [S1] Thanks!", SOURCES)
    assert status == "ok" and "11:00" in ans


def test_transitions_and_questions_allowed():
    draft = "Here is what I found:\n- ICU visiting hours are 11:00–12:00 [S1].\nIs there anything else I can help with?"
    ans, status = verify_grounding(draft, SOURCES)
    assert ans.startswith("Here is what I found:") and ans.endswith("help with?")


def test_list_markers_are_not_checked_as_numbers():
    ans, status = verify_grounding("1. Visiting hours are 17:00–18:00 [S1].", SOURCES)
    assert status == "ok" and ans.startswith("1. ")


def test_empty_draft_is_not_found():
    assert verify_grounding("", SOURCES) == (NOT_FOUND_MSG, "not_found")


def test_sentence_splitter_handles_abbreviations():
    assert split_sentences("See Dr. Rao at 09:00. Then go home.") == ["See Dr. Rao at 09:00.", "Then go home."]


# ------------------------------------------------------------------ end-to-end grounding checks
@pytest.mark.parametrize("user,question", [
    ("asha", "What are visiting hours for ICU patients?"),
    ("asha", "How do I schedule an MRI scan?"),
    ("asha", "Am I covered for knee replacement?"),
    ("meera", "What is my latest blood sugar reading?"),
    ("rahul", "My doctor recommended surgery. What pre-operative tests are still pending?"),
    ("asha", "What are my upcoming appointments?"),
])
def test_every_citation_tag_resolves(client, user, question):
    r = ask(client, user, question)
    tags = set(re.findall(r"\[(S\d+)\]", r["answer"]))
    assert tags, "answer must carry citations"
    assert tags == {c["id"] for c in r["citations"]}


@pytest.mark.parametrize("question", [
    "Do you have proton beam therapy?",
    "What vaccines are needed for travel to Brazil?",
    "Can I bring my dog to the ward?",
    "Do you offer sleep studies?",
])
def test_unanswerable_questions_are_not_found(client, question):
    r = ask(client, "asha", question)
    assert r["status"] == "not_found" and r["citations"] == [] and r["cards"] == []
