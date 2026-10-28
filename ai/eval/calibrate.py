"""Calibrate RERANK_THRESHOLD: compare top reranker scores for answerable vs unanswerable questions.

Usage:  python -m ai.eval.calibrate
Pick a threshold between the two distributions, leaning strict (closer to the answerable minimum).
"""
import os

os.environ["RERANK_THRESHOLD"] = "-1000"  # see raw scores

from ai import retriever  # noqa: E402

ANSWERABLE = [
    "What are visiting hours for ICU patients?", "Can children visit the ICU?", "How do I schedule an MRI scan?",
    "What should I do before discharge?", "How long do lab reports take?", "What is the deductible of the Gold plan?",
    "Where is the cardiology department?", "Can I reschedule my appointment?", "What is the no-show policy?",
    "What tests are required before major surgery?", "How do I prepare for an MRI?",
    "Who can see my medical records?", "Do you do organ transplants?", "What time is discharge?",
    "How many visitors are allowed in the general ward?", "How do I get a copy of my medical records?",
    "Is prior authorization needed for knee replacement on Gold?", "When is the laboratory open?",
    "What should I bring to my appointment?", "How do I book a CT scan with contrast?",
]
UNANSWERABLE = [
    "Do you have proton beam therapy?", "What is the cure for Ebola?", "Do you have a helipad?",
    "What is the parking fee?", "Is there a cafeteria and what are the menu prices?",
    "Can I bring my dog to the ward?", "What is the hospital Wi-Fi password?",
    "Do you offer dental implants?", "Who won the cricket match yesterday?", "How do I treat a snake bite at home?",
    "What is the stock price of the hospital?", "Do you offer Ayurvedic massage therapy?",
    "What languages do the nurses speak?", "Is there a gym for patients?", "Do you have a blood bank donor rewards program?",
    "What is the treatment for rare disease X?", "Are there ATMs in the hospital?", "Can I get a tattoo removed here?",
    "Do you offer sleep studies?", "What vaccines are needed for travel to Brazil?",
]


def top_score(q):
    r = retriever.search(q, top_n=1)
    return (r[0]["score"], r[0]["title"], r[0]["section"]) if r else (float("-inf"), "-", "-")


def main():
    a = [(top_score(q), q) for q in ANSWERABLE]
    u = [(top_score(q), q) for q in UNANSWERABLE]
    print("ANSWERABLE (should be high)")
    for (s, t, sec), q in sorted(a):
        print(f"  {s:7.2f}  {q}  ->  {t} / {sec}")
    print("UNANSWERABLE (should be low)")
    for (s, t, sec), q in sorted(u, reverse=True):
        print(f"  {s:7.2f}  {q}  ->  {t} / {sec}")
    lo = min(s for (s, _, _), _ in a)
    hi = max(s for (s, _, _), _ in u)
    print(f"\nmin answerable = {lo:.2f}   max unanswerable = {hi:.2f}")
    print(f"suggested RERANK_THRESHOLD = {(lo + hi) / 2:.2f}" if lo > hi else
          "distributions overlap - inspect the lists above and pick a strict value")


if __name__ == "__main__":
    main()
